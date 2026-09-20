# -*- coding: utf-8 -*-
"""Modificar un horario ya armado sin rehacer el mes entero.

Es la pantalla que más se usa cuando el mes ya está montado, y la que más daño
hace si se equivoca: reorganizar por completo un mes para mover un turno movería
los descansos de dieciocho personas por una petición de una.

La idea, entera, cabe en una frase: **lo que no se ha pedido cambiar se congela**.
Antes de volver a llamar al motor se le entrega, casilla a casilla, todo lo que
tiene que dejar exactamente como está —las semanas cerradas, las áreas que nadie
ha marcado, las personas que no se están tocando— y se le deja decidir solo
sobre el resto. Así el motor sigue siendo el único que reparte turnos, y esta
pantalla no tiene que saber repartir nada.

Hay tres alcances y se combinan con la selección de semanas:

* **todo** — se recalcula el rango de semanas elegido, para todo el mundo;
* **áreas** — solo las áreas marcadas; las otras dos se copian tal cual;
* **persona** — solo esa persona, y se decide aparte si el resto de su área
  puede reajustarse para acomodar el cambio o si también se congela.

Y encima de eso van los **cambios manuales**: «este día, esta persona, este
turno». Si el cambio cabe dentro de las reglas, se aplica y ya. Si no cabe, no
se aplica en silencio: se dice qué regla lo impide, y solo se aplica igualmente
si alguien lo autoriza expresamente y escribe por qué.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from gestor.datos import ajustes as datos_ajustes
from gestor.datos import horarios, novedades, personal
from gestor.dominio import calendario, cobertura
from gestor.motor.decisiones import NO_SE_PISAN_NI_FORZANDO
from gestor.registro import obtener
from gestor.servicios import cierres, continuidad, periodos

#: Cuántas alternativas se ofrecen y cuántas variantes se prueban para lograrlas.
ALTERNATIVAS = 5
VARIANTES = 12

#: Lo único que un cambio manual puede poner. Una ausencia —vacaciones, una
#: incapacidad— no se pone aquí: se registra como novedad, que es donde se
#: aprueba y donde queda con su fecha y su motivo.
TURNOS_MANUALES = ('AM', 'PM', 'D', 'ADM-GS', 'ADM-AC')


class NoSePudoReprogramar(Exception):
    """No hay salida para lo que se ha pedido, y el mensaje dice por qué."""


@dataclass
class Peticion:
    mes: int
    anio: int
    horario_id: Optional[int] = None
    semana_inicio: Optional[str] = None
    semana_fin: Optional[str] = None
    empleado_id: Optional[int] = None
    areas: list[str] = field(default_factory=list)
    ajustes_manuales: list[dict] = field(default_factory=list)
    reestructurar_otros: bool = True
    permitir_excepciones_manuales: bool = False
    motivo_excepcion_manual: str = ''
    solo_este_dia: bool = False


# ------------------------------------------------------------- el recorte

def _rango_editable(peticion: Peticion) -> set[str]:
    """Las fechas que el motor puede tocar. Todo lo demás se congela.

    Una semana cerrada nunca entra, aunque caiga dentro del rango elegido: es lo
    que significa cerrarla, y confiar en que el usuario no la seleccione sería
    poner la protección en el sitio equivocado.

    Con «solo este día» entra **la semana entera de esa fecha**, y es a
    propósito aunque sorprenda. El turno se decide por semanas y el descanso
    semanal es uno: poner AM en el día libre de alguien obliga a mover ese
    descanso a otro día de la misma semana, y sin esos seis días el cambio
    sencillamente no cabría y se rechazaría sin poder explicar por qué. Lo que
    se estrecha es **quién** se mueve: solo esa persona (ver
    `_quien_se_puede_mover`). Los días de su semana que acaben cambiando se
    devuelven uno a uno en `cambios_automaticos` del diagnóstico, porque es la
    pregunta inmediata: «vale, ¿y qué más ha cambiado por esto?».
    """
    semanas = calendario.semanas(peticion.mes, peticion.anio)
    lunes_del_mes = [inicio.isoformat() for inicio, _ in semanas]
    cerradas = cierres.semanas_cerradas(peticion.anio, peticion.mes)

    if peticion.solo_este_dia and peticion.ajustes_manuales:
        fecha = str(peticion.ajustes_manuales[0]['fecha'])[:10]
        lunes = calendario.lunes_de(date.fromisoformat(fecha)).isoformat()
        elegidos = [lunes] if lunes in lunes_del_mes else []
    else:
        desde = str(peticion.semana_inicio or lunes_del_mes[0])[:10]
        hasta = str(peticion.semana_fin or lunes_del_mes[-1])[:10]
        if desde > hasta:
            desde, hasta = hasta, desde
        elegidos = [lunes for lunes in lunes_del_mes if desde <= lunes <= hasta]

    editables: set[str] = set()
    for lunes in elegidos:
        if lunes in cerradas:
            continue
        editables.update(cierres.fechas_de(lunes))
    return editables


def _quien_se_puede_mover(peticion: Peticion, plantilla: list[dict]) -> set[int]:
    """Las personas cuyo horario el motor puede rehacer."""
    if peticion.solo_este_dia and peticion.ajustes_manuales:
        return {int(peticion.ajustes_manuales[0]['empleado_id'])}
    if peticion.areas:
        return {int(p['id']) for p in plantilla if p.get('area') in set(peticion.areas)}
    if peticion.empleado_id:
        elegido = next((p for p in plantilla
                        if int(p['id']) == int(peticion.empleado_id)), None)
        if elegido is None:
            raise NoSePudoReprogramar('Esa persona ya no está en la plantilla.')
        if not peticion.reestructurar_otros:
            return {int(elegido['id'])}
        # Con reajuste, el área entera puede moverse para acomodar el cambio:
        # cubrir el turno que deja libre es cosa de sus compañeros, no suya.
        return {int(p['id']) for p in plantilla if p.get('area') == elegido.get('area')}
    return {int(p['id']) for p in plantilla}


def _congelar(base: dict, editables: set[str], movibles: set[int]) -> list[dict]:
    """Entrega al motor, casilla a casilla, todo lo que no puede tocar."""
    congelados = []
    for fila in base.get('horario') or []:
        empleado_id = int(fila.get('empleado_id') or 0)
        mueve = empleado_id in movibles
        for dia in fila.get('dias') or []:
            fecha = str(dia.get('fecha'))
            if mueve and fecha in editables:
                continue
            congelados.append({
                'empleado_id': empleado_id, 'fecha': fecha,
                'turno': dia.get('turno'), 'preservar': True,
                'origen': dia.get('origen'),
                'observacion': dia.get('observacion', ''),
                'solicitud_id': dia.get('solicitud_id'),
                'requerimiento_id': dia.get('requerimiento_id'),
                'festivo_origen': dia.get('festivo_origen'),
                'capacitacion_horas': dia.get('capacitacion_horas') or 0.0,
                'cobertura_operativa': dia.get('cobertura_operativa'),
                'turno_operativo_origen': dia.get('turno_operativo_origen'),
            })
    return congelados


# ------------------------------------------------------ los cambios a mano

def _validar_manuales(peticion: Peticion, base: dict,
                      editables: set[str]) -> list[dict]:
    """Los cambios pedidos a mano, o el motivo por el que no se pueden pedir.

    `editables` no es decoración. Los manuales se le entregan al motor
    **después** de las casillas congeladas, así que uno que cayera fuera del
    rango —o dentro de una semana cerrada— pisaba lo congelado y salía aplicado.
    Cerrar una semana dejaba de significar nada en cuanto alguien marcaba la
    casilla de forzar: por ahí se podía cambiar un día que la oficina ya tenía
    impreso.
    """
    heredados = {
        (int(f.get('empleado_id') or 0), str(d.get('fecha')))
        for f in base.get('horario') or [] for d in f.get('dias') or []
        if d.get('heredado') or str(d.get('origen') or '').startswith('base_')}

    limpios = []
    for crudo in peticion.ajustes_manuales:
        empleado_id = int(crudo['empleado_id'])
        fecha = str(crudo['fecha'])[:10]
        turno = str(crudo.get('turno') or '')
        if turno not in TURNOS_MANUALES:
            raise NoSePudoReprogramar(
                f'Un cambio manual solo puede poner {", ".join(TURNOS_MANUALES)}. '
                'Unas vacaciones o una incapacidad se registran como novedad, que es '
                'donde se aprueban y quedan con su motivo.')
        if (empleado_id, fecha) in heredados:
            raise NoSePudoReprogramar(
                f'El {fecha} pertenece a un mes ya publicado y no se puede cambiar '
                'desde aquí. Cámbialo en ese mes y este volverá a leerlo.')
        if fecha not in editables:
            cerrada = fecha in cierres.fechas_cerradas(peticion.anio, peticion.mes)
            raise NoSePudoReprogramar(
                f'El {fecha} está en una semana cerrada y no se puede cambiar. '
                'Ábrela primero si de verdad hay que tocarla, y quedará registrado.'
                if cerrada else
                f'El {fecha} queda fuera de las semanas que has elegido. Amplía la '
                'selección hasta esa fecha o quita el cambio.')
        limpios.append({
            'empleado_id': empleado_id, 'fecha': fecha, 'turno': turno,
            'forzar_total': bool(peticion.permitir_excepciones_manuales),
            'justificacion': str(peticion.motivo_excepcion_manual or '').strip(),
        })
    if (limpios and peticion.permitir_excepciones_manuales
            and len(str(peticion.motivo_excepcion_manual or '').strip()) < 5):
        raise NoSePudoReprogramar(
            'Para saltarse una regla hace falta escribir el motivo. Sin él, dentro '
            'de tres meses nadie podrá explicar por qué ese día está así.')
    return limpios


def _turno_en(resultado: dict, empleado_id: int, fecha: str) -> Optional[dict]:
    for fila in resultado.get('horario') or []:
        if int(fila.get('empleado_id') or 0) != int(empleado_id):
            continue
        for dia in fila.get('dias') or []:
            if str(dia.get('fecha')) == fecha:
                return dia
    return None


def _diagnostico(resultado: dict, base: dict, manuales: list[dict],
                 nombres: dict[int, str]) -> list[dict]:
    """Qué pasó con cada cambio pedido, en una frase que se pueda leer.

    Que un cambio no se pueda aplicar no es un error del programa: es una regla
    haciendo su trabajo. Lo que sí sería un error es no decirlo y dejar que la
    persona crea que su cambio quedó puesto.
    """
    salida = []
    for item in manuales:
        antes = _turno_en(base, item['empleado_id'], item['fecha'])
        despues = _turno_en(resultado, item['empleado_id'], item['fecha'])
        puesto = despues and despues.get('turno') == item['turno']
        forzado = bool(despues and despues.get('excepcion_forzada'))
        if not despues:
            estado, mensaje = 'no_aplicado', (
                'Esa fecha no está en el período que se ha reprogramado.')
        elif puesto and forzado:
            estado, mensaje = 'forzado', (
                'Quedó puesto como excepción autorizada, con el motivo registrado.')
        elif puesto:
            estado, mensaje = 'aplicado', 'Quedó puesto sin saltarse ninguna regla.'
        elif despues.get('turno') in NO_SE_PISAN_NI_FORZANDO:
            # Aquí no hay nada que autorizar desde esta pantalla, y decir
            # «autoriza la excepción» mandaría a marcar una casilla que no va a
            # servir. Lo que hay que cambiar está en otro sitio.
            estado, mensaje = 'no_aplicado', (
                f'Ese día tiene {despues.get("turno")} por una novedad aprobada. '
                'Forzar no lo cambia: el horario refleja esa decisión, no la '
                'toma. Si ya no vale, rectifícala en Solicitudes y el horario la '
                'seguirá.')
        else:
            estado, mensaje = 'no_aplicado', (
                f'No se pudo poner {item["turno"]}: quedó {despues.get("turno")}. '
                'Mira Validación para ver qué regla lo impide, o autoriza la '
                'excepción explicando el motivo.')
        salida.append({
            'empleado_id': item['empleado_id'],
            'empleado_nombre': nombres.get(item['empleado_id'], '—'),
            'fecha': item['fecha'],
            'turno': item['turno'],
            'turno_anterior': antes.get('turno') if antes else None,
            'estado': estado, 'mensaje': mensaje,
            'detalles': list(resultado.get('excepciones_manuales') or []) if forzado else [],
            'cambios_automaticos': _reajustes(base, resultado, item),
            'sugerencias': [],
        })
    return salida


def _reajustes(base: dict, resultado: dict, item: dict) -> list[dict]:
    """Lo que se movió en la misma semana para que ese cambio cupiera.

    Se enseña porque es la pregunta inmediata: «vale, ¿y a quién le ha cambiado
    el descanso por esto?».
    """
    lunes = calendario.lunes_de(date.fromisoformat(item['fecha']))
    semana = {(lunes + timedelta(days=i)).isoformat() for i in range(7)}
    antes = {(int(f.get('empleado_id') or 0), str(d.get('fecha'))): d.get('turno')
             for f in base.get('horario') or [] for d in f.get('dias') or []}
    nombres = {int(f.get('empleado_id') or 0): f.get('nombre')
               for f in resultado.get('horario') or []}
    movidos = []
    for fila in resultado.get('horario') or []:
        empleado_id = int(fila.get('empleado_id') or 0)
        for dia in fila.get('dias') or []:
            fecha = str(dia.get('fecha'))
            if fecha not in semana:
                continue
            if (empleado_id, fecha) == (item['empleado_id'], item['fecha']):
                continue
            previo = antes.get((empleado_id, fecha))
            if previo is not None and previo != dia.get('turno'):
                movidos.append({
                    'empleado_id': empleado_id, 'nombre': nombres.get(empleado_id),
                    'fecha': fecha, 'antes': previo, 'despues': dia.get('turno'),
                    'motivo': dia.get('observacion') or 'Reajuste automático'})
    return movidos[:20]


# ------------------------------------------------------------- reprogramar

def _base(peticion: Peticion) -> dict:
    guardado = (horarios.obtener(int(peticion.horario_id))
                if peticion.horario_id else horarios.oficial(peticion.anio, peticion.mes))
    if guardado is None:
        raise NoSePudoReprogramar(
            f'{calendario.nombre_del_periodo(peticion.mes, peticion.anio)} todavía no '
            'tiene ningún horario del que partir. Genera el mes completo primero.')
    return dict(guardado['datos'] or {})


def _firma(resultado: dict) -> tuple:
    return tuple((f['empleado_id'], tuple(d['turno'] for d in f['dias']))
                 for f in resultado.get('horario') or ())


def reprogramar(peticion: Peticion) -> dict:
    """Vuelve a armar solo lo pedido y devuelve alternativas para comparar."""
    from gestor.motor.orquestacion import generar_horario_completo

    base = _base(peticion)
    inicio, fin = calendario.rango(int(peticion.mes), int(peticion.anio))
    plantilla = personal.para_periodo(inicio.isoformat(), fin.isoformat())
    if not plantilla:
        raise NoSePudoReprogramar('No hay nadie en la plantilla.')
    nombres = {int(p['id']): p['nombre'] for p in plantilla}

    for area in peticion.areas:
        if area not in cobertura.AREAS:
            raise NoSePudoReprogramar(
                f'«{area}» no es un área. Tiene que ser una de: '
                f'{", ".join(cobertura.AREAS)}.')

    editables = _rango_editable(peticion)
    if not editables:
        raise NoSePudoReprogramar(
            'No queda ninguna semana editable en la selección: las que has elegido '
            'están cerradas. Ábrelas primero si de verdad quieres cambiarlas.')

    manuales = _validar_manuales(peticion, base, editables)
    movibles = _quien_se_puede_mover(peticion, plantilla)
    congelados = _congelar(base, editables, movibles)

    # Los cambios ya guardados de otras fechas siguen valiendo: el editor no es
    # una hoja en blanco cada vez que se abre.
    guardados = [a for a in datos_ajustes.para_el_motor(peticion.mes, peticion.anio)
                 if (int(a['empleado_id']), a['fecha']) not in
                 {(m['empleado_id'], m['fecha']) for m in manuales}]

    solicitudes = novedades.solicitudes_para_el_motor(peticion.mes, peticion.anio)
    asignaciones = novedades.asignaciones_para_el_motor(peticion.mes, peticion.anio)
    contexto = continuidad.todo(peticion.mes, peticion.anio)
    # Igual que al generar el mes entero: lo que estas alternativas incorporan
    # queda escrito con ellas, y es lo único que se dará por resuelto si se
    # elige una. Con las áreas pedidas, solo los avisos de esas áreas.
    avisos = ([a for area in peticion.areas
               for a in periodos.pendientes(peticion.mes, peticion.anio, area=area)]
              if peticion.areas else
              periodos.pendientes(peticion.mes, peticion.anio))

    vistas, alternativas = set(), []
    for variante in range(VARIANTES):
        if len(alternativas) >= ALTERNATIVAS:
            break
        try:
            resultado = generar_horario_completo(
                plantilla, solicitudes, int(peticion.mes), int(peticion.anio),
                variante=variante, requerimientos=asignaciones,
                ajustes_manuales=congelados + guardados + manuales,
                permitir_excepciones_cobertura_manual=bool(
                    peticion.permitir_excepciones_manuales),
                **contexto)
        except Exception:                                          # noqa: BLE001
            obtener().exception('la variante %s de la reprogramación no salió', variante)
            continue
        firma = _firma(resultado)
        if firma in vistas:
            continue
        vistas.add(firma)
        resultado['reprogramacion_parcial'] = {
            'semana_inicio': peticion.semana_inicio, 'semana_fin': peticion.semana_fin,
            'areas': list(peticion.areas), 'empleado_id': peticion.empleado_id,
            'solo_este_dia': peticion.solo_este_dia,
            'ajustes_manuales': manuales,
            'permitir_excepciones_manuales': peticion.permitir_excepciones_manuales,
            'motivo_excepcion_manual': peticion.motivo_excepcion_manual,
        }
        resultado['avisos_incorporados'] = list(avisos)
        alternativas.append(resultado)

    if not alternativas:
        raise NoSePudoReprogramar(
            'No se encontró ninguna alternativa válida para lo que se ha pedido. '
            'Revisa Validación: el rango elegido o los cambios manuales pueden ser '
            'incompatibles con la cobertura, los descansos o las parejas.')

    grupo = f'{peticion.anio}-{int(peticion.mes):02d}-{uuid.uuid4().hex[:8]}'
    ids = horarios.guardar_propuestas(peticion.anio, peticion.mes, grupo, alternativas)
    for alternativa, identificador in zip(alternativas, ids, strict=True):
        alternativa['horario_id'] = identificador

    # Los cambios pedidos se guardan solo si de verdad quedaron puestos: guardar
    # uno que la regla rechazó dejaba un ajuste que reaparecía en cada
    # generación sin llegar a aplicarse nunca.
    diagnostico = _diagnostico(alternativas[0], base, manuales, nombres)
    for parte in diagnostico:
        if parte['estado'] in ('aplicado', 'forzado'):
            datos_ajustes.guardar(
                parte['empleado_id'], parte['fecha'], parte['turno'],
                forzado=parte['estado'] == 'forzado',
                justificacion=peticion.motivo_excepcion_manual,
                reglas=alternativas[0].get('excepciones_manuales') or [])

    # Tampoco aquí se quita el aviso: esto son alternativas para comparar, no el
    # horario del mes. Y se quitaba entero, sin área, así que reprogramar
    # Gestión Social borraba también el pendiente de Comunicaciones. Se quita al
    # elegir una, y solo para las áreas que esa propuesta rehizo de verdad.
    return {
        'alternativas': alternativas,
        'grupo_id': grupo,
        'diagnostico_ajustes_manuales': diagnostico,
        'diagnostico': {
            'errores': list(alternativas[0].get('errores') or []),
            'advertencias': list(alternativas[0].get('advertencias') or []),
        },
        'completo': all(a.get('valido') for a in alternativas),
        'parcial_automatico': len(editables) < len(
            [d for f in base.get('horario') or [] for d in f.get('dias') or []]
        ) // max(len(base.get('horario') or [1]), 1),
    }
