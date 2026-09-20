# -*- coding: utf-8 -*-
"""¿Está el mes listo para repartirse?

Publicar es el último paso y el único que no se deshace del todo: a partir de
ahí la oficina tiene el papel en la mano. Por eso antes se hace una revisión y
se enseña qué se está dando por bueno.

La revisión separa **tres cosas distintas**, y confundirlas fue el error de la
versión anterior:

* lo que **impide publicar** —un hueco de cobertura que este mes sí puede
  arreglar, una pareja en el mismo turno, un festivo trabajado sin su
  compensatorio—;
* lo que se **acepta a sabiendas** —un cambio manual autorizado con su
  justificación, o un día que viene de un mes ya publicado y que este período no
  puede tocar—, que se enseña y pide una confirmación expresa;
* lo que **solo se informa** —alertas de semanas ya cerradas—, que se lista como
  referencia y no bloquea nada.

Las programaciones base —agosto y septiembre de 2026— son un caso aparte: son la
transcripción del horario real que la oficina ya trabajó. Sus diferencias con
las reglas de hoy no se pueden arreglar, porque ya ocurrieron. Se pueden
publicar confirmando expresamente qué se está aceptando, y el resumen lo dice
con el nombre del mes en vez de dar por hecho que siempre es agosto.
"""
from __future__ import annotations

from datetime import date

from gestor.datos import horarios
from gestor.datos.base import abierta, transaccion
from gestor.dominio import calendario, cobertura
from gestor.dominio.codigos import TRABAJADOS
from gestor.servicios import reglas_cobertura


def _dias_por_fecha(fila: dict) -> dict:
    return {str(d['fecha']): d for d in fila.get('dias') or []}


def _fechas_de_semanas_cerradas(anio: int, mes: int) -> set[str]:
    from datetime import timedelta
    with abierta() as conexion:
        lunes = [str(f['lunes']) for f in conexion.execute(
            'SELECT lunes FROM semanas WHERE anio=? AND mes=? AND cerrada=1',
            (int(anio), int(mes)))]
    fechas = set()
    for texto in lunes:
        try:
            inicio = date.fromisoformat(texto)
        except ValueError:
            continue
        fechas.update((inicio + timedelta(days=i)).isoformat() for i in range(7))
    return fechas


def _es_heredado(dia: dict) -> bool:
    return bool(str(dia.get('origen') or '').startswith('base_') or dia.get('heredado'))


def _autorizado_a_mano(dia: dict) -> bool:
    return bool(dia.get('excepcion_forzada') or dia.get('requerimiento_id'))


def revisar(guardado: dict) -> dict:
    """Todo lo que hay que saber antes de publicar ese horario."""
    datos = guardado.get('datos') or {}
    horario = list(datos.get('horario') or [])
    anio, mes = int(guardado['anio']), int(guardado['mes'])
    es_base = calendario.es_mes_base(mes, anio)
    cerradas = _fechas_de_semanas_cerradas(anio, mes)

    fechas = sorted({str(d['fecha']) for f in horario for d in f.get('dias') or []})
    huecos, huecos_aceptados, ignorados = [], [], []

    for area in cobertura.AREAS:
        gente = [f for f in horario if f.get('area') == area]
        if not gente:
            continue
        for fecha in fechas:
            regla = reglas_cobertura.regla(area, fecha)
            for fallo in cobertura.incumplimientos(horario, area, fecha, regla):
                item = {'tipo': 'cobertura', 'area': cobertura.NOMBRES_AREA.get(area, area),
                        'fecha': fecha, 'turno': fallo.norma, 'detalle': fallo.mensaje}
                dias = [_dias_por_fecha(f).get(fecha) for f in gente]
                dias = [d for d in dias if d]
                if any(_autorizado_a_mano(d) for d in dias):
                    huecos_aceptados.append(
                        {**item, 'motivo': 'Cambio manual autorizado y justificado'})
                elif fallo.heredado or all(_es_heredado(d) for d in dias):
                    huecos_aceptados.append(
                        {**item, 'motivo': 'Viene de un mes ya publicado'})
                elif fecha in cerradas:
                    ignorados.append(item)
                else:
                    huecos.append(item)

    parejas, parejas_aceptadas = _revisar_parejas(horario, fechas, cerradas, ignorados)
    compensatorios = _revisar_compensatorios(horario)
    errores = [{'tipo': 'error', 'detalle': str(e)} for e in (datos.get('errores') or [])]
    excepciones = _excepciones_manuales(horario)

    aceptadas = huecos_aceptados + parejas_aceptadas
    bloqueantes = huecos + parejas + compensatorios + errores

    resumen = {
        'anio': anio, 'mes': mes,
        'nombre': calendario.nombre_del_periodo(mes, anio),
        'nombre_periodo': calendario.nombre_del_periodo(mes, anio),
        'horario_id': guardado.get('id'),
        'oficial': bool(guardado.get('oficial')),
        'publicado': bool(guardado.get('publicado')),
        'es_agosto_historico': es_base,
        'es_programacion_base': es_base,
        'cobertura_sin_am_pm': huecos,
        'conflictos_pareja': parejas,
        'compensatorios_pendientes': compensatorios,
        'errores_bloqueantes': errores,
        'excepciones_manuales': excepciones,
        'problemas_agosto_publicables': aceptadas if es_base else [],
        'incidencias_aceptadas': aceptadas,
        'problemas_ignorados_semanas_bloqueadas': ignorados,
        'conteos': {
            'dias_sin_cobertura': len(huecos),
            'conflictos_pc': len(parejas),
            'compensatorios_pendientes': len(compensatorios),
            'errores_bloqueantes': len(errores),
        },
    }
    # Un mes base se puede publicar con lo que trae: lo que hay que decidir no
    # es si está bien, sino si se acepta tal como se trabajó.
    resumen['listo'] = not bloqueantes and not aceptadas and not excepciones
    resumen['requiere_confirmacion'] = bool(
        (es_base and aceptadas) or aceptadas or excepciones)
    resumen['bloqueado'] = bool(bloqueantes) and not es_base
    return resumen


def _revisar_parejas(horario, fechas, cerradas, ignorados) -> tuple[list, list]:
    por_id = {int(f['empleado_id']): f for f in horario}
    vistas, choques, aceptados = set(), [], []
    for fila in horario:
        pareja_id = fila.get('pareja_id')
        if not pareja_id or int(pareja_id) not in por_id:
            continue
        clave = tuple(sorted((int(fila['empleado_id']), int(pareja_id))))
        if clave in vistas:
            continue
        vistas.add(clave)
        otra = por_id[int(pareja_id)]
        unos, otros = _dias_por_fecha(fila), _dias_por_fecha(otra)
        for fecha in fechas:
            a, b = unos.get(fecha), otros.get(fecha)
            if not a or not b:
                continue
            if a.get('turno') not in ('AM', 'PM') or a.get('turno') != b.get('turno'):
                continue
            item = {'tipo': 'pc', 'fecha': fecha, 'turno': a['turno'],
                    'personas': [fila['nombre'], otra['nombre']],
                    'detalle': (f'{fila["nombre"]} y {otra["nombre"]} coinciden en '
                                f'{a["turno"]} el {fecha}.')}
            if _autorizado_a_mano(a) or _autorizado_a_mano(b):
                aceptados.append({**item, 'motivo': 'Asignación directa o cambio autorizado'})
            elif _es_heredado(a) and _es_heredado(b):
                aceptados.append({**item, 'motivo': 'Viene de un mes ya publicado'})
            elif fecha in cerradas:
                ignorados.append(item)
            else:
                choques.append(item)
    return choques, aceptados


def _revisar_compensatorios(horario) -> list[dict]:
    """Quien trabaja un festivo tiene después un día de descanso.

    Solo se exige por los festivos **de este mes**. El festivo que cae en la
    última semana del período ya pertenece al mes siguiente y su compensatorio
    se reparte allí: exigirlo aquí dejaba diciembre sin poder publicarse por el
    1 de enero.
    """
    pendientes = []
    for fila in horario:
        dias = fila.get('dias') or []
        for dia in dias:
            if not dia.get('es_festivo') or not dia.get('mes_propio', True):
                continue
            if dia.get('turno') not in TRABAJADOS:
                continue
            fecha = str(dia['fecha'])
            tiene = any(x.get('turno') == 'D'
                        and str(x.get('origen') or '') == 'compensatorio_festivo'
                        and x.get('festivo_origen') == fecha for x in dias)
            if not tiene:
                pendientes.append({
                    'tipo': 'compensatorio', 'empleado': fila['nombre'],
                    'festivo': fecha,
                    'detalle': (f'{fila["nombre"]} trabajó el festivo {fecha} y no tiene '
                                'su día de descanso compensatorio.')})
    return pendientes


def _excepciones_manuales(horario) -> list[str]:
    salida = []
    for fila in horario:
        for dia in fila.get('dias') or []:
            if dia.get('excepcion_forzada'):
                motivo = str(dia.get('justificacion') or dia.get('observacion') or '').strip()
                salida.append(f'{fila["nombre"]} · {dia["fecha"]} · {dia.get("turno")}'
                              + (f' · {motivo}' if motivo else ''))
    return salida


def resumen(horario_id: int) -> dict:
    guardado = horarios.obtener(horario_id)
    if guardado is None:
        raise ValueError('No se encuentra esa programación.')
    return revisar(guardado)


def publicar(horario_id: int, confirmar_excepciones: bool = False) -> dict:
    """Deja el horario publicado, si está listo o si se confirma lo que trae."""
    guardado = horarios.obtener(horario_id)
    if guardado is None:
        raise ValueError('No se encuentra esa programación.')
    if not guardado.get('oficial'):
        raise ValueError(
            'Primero marca esta propuesta como el horario oficial del mes. '
            'Publicar una propuesta que todavía no es la buena repartiría un papel '
            'que no coincide con lo que la aplicación acabará diciendo.')

    revision = revisar(guardado)
    if revision['bloqueado']:
        raise ValueError(
            f'{revision["nombre"]} tiene {sum(revision["conteos"].values())} cosa(s) que '
            'resolver antes de publicarlo. Míralas en el resumen de publicación.')
    if revision['requiere_confirmacion'] and not confirmar_excepciones:
        cuantas = len(revision['incidencias_aceptadas']) + len(revision['excepciones_manuales'])
        raise ValueError(
            (f'{revision["nombre"]} es un horario que ya se trabajó y tiene '
             f'{cuantas} diferencia(s) con las reglas de hoy. Míralas en el resumen y '
             'acéptalas expresamente si quieres publicarlo tal como está.')
            if revision['es_agosto_historico'] else
            (f'{revision["nombre"]} tiene {cuantas} cosa(s) que hay que aceptar a '
             'sabiendas: días que vienen de un mes ya publicado, o cambios autorizados '
             'a mano. Míralas en el resumen y acéptalas expresamente para publicar.'))

    anio, mes = int(guardado['anio']), int(guardado['mes'])
    with transaccion() as conexion:
        conexion.execute(
            'UPDATE horarios SET publicado=0, publicado_en=NULL WHERE anio=? AND mes=?',
            (anio, mes))
        conexion.execute(
            "UPDATE horarios SET publicado=1, publicado_en=datetime('now') WHERE id=?",
            (int(horario_id),))
    # Publicar no incorpora nada: reparte lo que ya estaba elegido. Borrar aquí
    # el aviso era la otra forma de hacerlo desaparecer sin resolver nada —basta
    # con volver a publicar el oficial de siempre— y dejaba el mes repartido con
    # novedades aprobadas fuera y sin rastro de que lo estuvieran.
    return {
        'anio': anio, 'mes': mes,
        'resumen': revisar(horarios.obtener(horario_id)),
        'mensaje': (
            f'{revision["nombre"]} queda publicado con las incidencias aceptadas. '
            'Ya se puede repartir.' if revision['requiere_confirmacion'] else
            f'{revision["nombre"]} queda publicado. Ya se puede repartir.'),
    }
