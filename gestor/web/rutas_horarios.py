# -*- coding: utf-8 -*-
"""Armar el mes, comparar las propuestas, elegir una y publicarla.

El ciclo entero de la aplicación pasa por aquí y tiene cuatro pasos, en este
orden y sin saltarse ninguno:

1. **generar** — salen cinco propuestas del mismo mes;
2. **comparar** — se miran y se ve cuál cumple y cuál no;
3. **oficializar** — se elige una; es la que hereda el mes siguiente;
4. **publicar** — se entrega al equipo.

Que sean pasos separados es a propósito. Generar no elige, elegir no publica, y
publicar no vuelve a generar. Encadenarlos automáticamente ahorraría dos clics y
quitaría el único momento en que alguien mira el mes antes de repartirlo.

Además del mes completo se puede rehacer **una parte**: unas semanas, un área,
una persona, o un solo día. Todo eso pasa por el mismo sitio —el servicio de
edición— porque en el fondo es la misma operación: congelar lo que nadie ha
pedido cambiar y dejar que el motor decida sobre el resto.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gestor.datos import ajustes as datos_ajustes
from gestor.datos import horarios
from gestor.dominio import calendario
from gestor.dominio.cobertura import AREAS, NOMBRES_AREA
from gestor.servicios import edicion, generacion, historial

router = APIRouter(prefix='/api/horarios', tags=['horarios'])


class Periodo(BaseModel):
    mes: int
    anio: int
    horario_id: Optional[int] = None


class PorAreas(BaseModel):
    mes: int
    anio: int
    horario_id: Optional[int] = None
    areas: list[str] = []


class Parcial(BaseModel):
    mes: int
    anio: int
    horario_id: Optional[int] = None
    semana_inicio: Optional[str] = None
    semana_fin: Optional[str] = None
    empleado_id: Optional[int] = None
    areas: list[str] = []
    ajustes_manuales: list[dict] = []
    reestructurar_otros: bool = True
    permitir_excepciones_manuales: bool = False
    motivo_excepcion_manual: str = ''
    solo_este_dia: bool = False


def _resumen(propuesta: dict) -> dict:
    """Lo que la pantalla necesita de cada propuesta para poder compararlas.

    Esta lista **es un contrato**, y `pruebas/test_contrato.py` lo comprueba
    campo a campo contra lo que el JavaScript lee de verdad.

    Hace falta que lo compruebe alguien porque olvidarse de un campo aquí no
    rompe nada: la pantalla lo lee con `|| 0` o `?? '—'` y enseña un cero o un
    guion **con la misma pinta que un dato de verdad**. Así estuvo la columna de
    horas del horario, marcando «0 h» y «0 de —» para toda la oficina, mes tras
    mes, con las estadísticas bien calculadas y guardadas a un palmo de aquí.
    """
    return {
        'horario_id': propuesta.get('horario_id') or propuesta.get('id'),
        'alternativa': propuesta.get('alternativa'),
        'valido': bool(propuesta.get('valido')),
        'errores': propuesta.get('errores') or [],
        'advertencias': propuesta.get('advertencias') or [],
        'oficial': bool(propuesta.get('oficial')),
        'publicado': bool(propuesta.get('publicado')),
        'horario': propuesta.get('horario') or [],
        'excepciones_manuales': propuesta.get('excepciones_manuales') or [],
        'reprogramacion_parcial': propuesta.get('reprogramacion_parcial'),
        # Las cinco columnas de la derecha del horario: horas del período, horas
        # del mes, domingos, festivos y especiales.
        'estadisticas': propuesta.get('estadisticas') or [],
        # Lo que Validación necesita para decir de qué tipo es cada aviso y qué
        # hacer con él. Sin esto, cada tarjeta caía en «Regla general».
        'validaciones': propuesta.get('validaciones') or [],
        'resumen_validacion': propuesta.get('resumen_validacion') or {},
        # El tope de jornadas seguidas y los domingos del mes rigen lo que se
        # enseña, y son configurables: viajan con el horario para que la
        # pantalla no los escriba a mano.
        'reglas': propuesta.get('reglas') or {},
        'nota_horas': propuesta.get('nota_horas'),
        'cambios_aplicados': propuesta.get('cambios_aplicados') or [],
    }


def _aviso(mensaje: str):
    """Un 409 con el texto escrito: no es un fallo del programa, falta algo.

    La pantalla lo enseña tal cual, así que el texto tiene que servir para que
    alguien sepa qué hacer, no para que un programador sepa dónde mirar.
    """
    return HTTPException(409, mensaje)


@router.post('/generar')
def generar(periodo: Periodo):
    if not 1 <= int(periodo.mes) <= 12:
        raise ValueError('El mes tiene que estar entre 1 y 12.')
    try:
        resultado = generacion.generar(periodo.mes, periodo.anio)
    except generacion.NoSePuedeGenerar as aviso:
        raise _aviso(str(aviso)) from None
    historial.anotar('generar_horario', 'horario', {
        'periodo': f'{resultado.anio}-{resultado.mes:02d}',
        'propuestas': len(resultado.propuestas)})
    alternativas = [_resumen(p) for p in resultado.propuestas]
    return {
        'ok': True, 'mes': resultado.mes, 'anio': resultado.anio,
        'nombre_periodo': calendario.nombre_del_periodo(resultado.mes, resultado.anio),
        'grupo_id': resultado.grupo_id,
        'cantidad': len(alternativas),
        'alternativas': alternativas,
        'completo': all(a['valido'] for a in alternativas),
        'mensaje': (
            f'Se armaron {len(alternativas)} propuestas de '
            f'{calendario.nombre_del_periodo(resultado.mes, resultado.anio)}. '
            'Compáralas y marca como oficial la que quieras usar.'),
    }


@router.post('/generar-areas')
def generar_solo_estas_areas(peticion: PorAreas):
    """Rehace solo las áreas marcadas. Las demás se copian tal cual.

    Es lo que evita que un permiso de una persona de Comunicaciones mueva los
    turnos de Gestión Social y de Atención al Ciudadano.
    """
    if not peticion.areas:
        raise ValueError('Marca al menos un área para actualizar.')
    return _reprogramar(edicion.Peticion(
        mes=peticion.mes, anio=peticion.anio, horario_id=peticion.horario_id,
        areas=list(peticion.areas)), etiqueta=', '.join(
            NOMBRES_AREA.get(a, a) for a in peticion.areas))


@router.post('/generar-area/{area}')
def generar_solo_un_area(area: str, peticion: Periodo):
    if area not in AREAS:
        raise ValueError(f'El área tiene que ser una de: {", ".join(AREAS)}.')
    return _reprogramar(edicion.Peticion(
        mes=peticion.mes, anio=peticion.anio, horario_id=peticion.horario_id,
        areas=[area]), etiqueta=NOMBRES_AREA.get(area, area))


@router.post('/reprogramar-parcial')
def reprogramar_parcial(peticion: Parcial):
    """Rehace unas semanas, un área, una persona o un solo día."""
    return _reprogramar(edicion.Peticion(**peticion.model_dump()))


def _turnos_por_dia(horario: list) -> dict:
    """`(persona, fecha) -> turno`, para poder comparar dos horarios."""
    return {(f.get('empleado_id'), d.get('fecha')): d.get('turno')
            for f in (horario or []) for d in (f.get('dias') or [])}


def _no_tocó_a_los_demás(areas, base: dict, propuesta: dict) -> bool:
    """¿La propuesta dejó intactas las áreas que no se pidió rehacer?

    La pantalla decía «Las otras dos áreas se conservaron sin cambios» y **nadie
    lo había comprobado**: leía un campo, `independencia_verificada`, que no
    existía en ninguna parte del programa, así que `undefined !== false` salía
    cierto y el mensaje se daba por bueno siempre. Es el peor sentido posible
    para un valor que falta: afirmar en positivo.

    Se compara turno a turno, que es lo que de verdad significa «sin cambios».
    """
    if not areas:
        return True
    otras = {(f.get('empleado_id'))
             for f in (base.get('horario') or [])
             if f.get('area') not in set(areas)}
    antes = _turnos_por_dia(base.get('horario'))
    despues = _turnos_por_dia(propuesta.get('horario'))
    llaves = {k for k in (set(antes) | set(despues)) if k[0] in otras}
    return all(antes.get(k) == despues.get(k) for k in llaves)


def _reprogramar(peticion: edicion.Peticion, etiqueta: str = '') -> dict:
    try:
        resultado = edicion.reprogramar(peticion)
    except edicion.NoSePudoReprogramar as aviso:
        raise _aviso(str(aviso)) from None
    partida = (horarios.obtener(int(peticion.horario_id)) if peticion.horario_id
               else horarios.oficial(peticion.anio, peticion.mes)) or {}
    alternativas = [
        {**_resumen(a),
         'independencia_verificada': _no_tocó_a_los_demás(peticion.areas, partida, a)}
        for a in resultado['alternativas']]
    historial.anotar('reprogramacion_parcial', 'horario', {
        'periodo': f'{peticion.anio}-{int(peticion.mes):02d}',
        'areas': peticion.areas, 'empleado_id': peticion.empleado_id,
        'cambios_manuales': len(peticion.ajustes_manuales)})
    cuantos = len(alternativas)
    return {
        'ok': True, 'mes': int(peticion.mes), 'anio': int(peticion.anio),
        'grupo_id': resultado['grupo_id'],
        'cantidad': cuantos,
        'alternativas': alternativas,
        'completo': resultado['completo'],
        'parcial_automatico': True,
        'diagnostico': resultado['diagnostico'],
        'diagnostico_ajustes_manuales': resultado['diagnostico_ajustes_manuales'],
        'mensaje': (
            f'Se armaron {cuantos} alternativa(s)'
            + (f' de {etiqueta}' if etiqueta else ' del rango elegido')
            + '. Lo que no entraba en la selección quedó exactamente igual.'),
    }


@router.delete('/ajuste-manual/{empleado_id}/{fecha}')
def quitar_cambio_manual(empleado_id: int, fecha: str):
    """Devuelve ese día a automático.

    No borra el rastro: deja de aplicarse. Así se puede seguir respondiendo
    «aquí hubo un cambio manual y se retiró tal día».
    """
    if not datos_ajustes.retirar(empleado_id, fecha):
        raise _aviso('No existe un cambio manual activo para esa persona y esa fecha.')
    historial.anotar('quitar_cambio_manual', 'horario',
                     {'empleado_id': empleado_id, 'fecha': fecha})
    return {'ok': True, 'mensaje': (
        f'El {fecha} vuelve a calcularse solo. Genera el mes otra vez para verlo.')}


@router.get('/ajustes-manuales/{anio}/{mes}')
def ver_cambios_manuales(anio: int, mes: int):
    return {'ok': True, 'ajustes': datos_ajustes.listar(mes, anio)}


@router.get('/opciones/{anio}/{mes}')
def opciones(anio: int, mes: int):
    """Las propuestas guardadas del mes, y cuál es la que rige.

    La pantalla repinta **siempre** desde aquí, incluso justo después de
    generar, así que lo que falte en esta respuesta no se ve en ninguna parte
    de la aplicación aunque la generación lo haya devuelto un segundo antes.

    Por eso el horario que rige viaja aparte de la lista de alternativas: la
    pantalla solo enseña las cinco primeras, y en un mes con seis propuestas la
    oficial podía quedarse fuera. Entonces la tarjeta «Horario actual» y el
    botón de Modificar que lo carga desaparecían, sin decir por qué.
    """
    guardadas = horarios.propuestas(anio, mes)
    oficial_guardado = next((p for p in guardadas if p['oficial']), None)
    publicado_guardado = next((p for p in guardadas if p['publicado']), None)
    en_pantalla = guardadas[:5]
    return {
        'ok': True,
        'cantidad': len(guardadas),
        'alternativas': [_resumen({**p, 'horario_id': p['id']}) for p in guardadas],
        'oficial_id': oficial_guardado['id'] if oficial_guardado else None,
        'publicado': bool(oficial_guardado and oficial_guardado['publicado']),
        'publicado_id': publicado_guardado['id'] if publicado_guardado else None,
        'grupo_id': guardadas[0]['grupo_id'] if guardadas else None,
        'horario_actual': (_resumen({**oficial_guardado,
                                     'horario_id': oficial_guardado['id']})
                           if oficial_guardado else None),
        'horario_publicado': (_resumen({**publicado_guardado,
                                        'horario_id': publicado_guardado['id']})
                              if publicado_guardado else None),
        # ¿Hay algo que comparar, o lo único guardado es lo que ya rige? De eso
        # depende que la pantalla invite a comparar o se limite a enseñar el mes.
        'hay_opciones_pendientes': any(
            not p['oficial'] and not p['publicado'] for p in en_pantalla),
    }


@router.get('/oficial/{anio}/{mes}')
def oficial(anio: int, mes: int):
    """El horario del mes, o nada si todavía no se ha elegido.

    Devuelve un objeto y no una lista. La versión anterior lo leía en la
    pantalla como si fuera una lista y siempre concluía que no había horario:
    con septiembre publicado, la aplicación decía que no se podía crear octubre
    y desactivaba el botón. El servidor estaba bien y todo salía en verde,
    porque ninguna comprobación llegaba a pulsar nada.
    """
    elegido = horarios.oficial(anio, mes)
    return {'ok': True, 'horario': elegido, 'hay_oficial': elegido is not None}


@router.patch('/{horario_id}/oficial')
def marcar_oficial(horario_id: int):
    resultado = generacion.marcar_oficial(horario_id)
    historial.anotar('marcar_oficial', 'horario', {
        'horario_id': horario_id,
        'periodo': f'{resultado["horario"]["anio"]}-{resultado["horario"]["mes"]:02d}'})
    return resultado


@router.delete('/{horario_id}/oficial')
def deshacer_oficial(horario_id: int):
    """Deja el mes sin elegir, para poder escoger otra propuesta de cero."""
    guardado = horarios.obtener(horario_id)
    if guardado is None:
        raise _aviso('No se encuentra esa programación.')
    # Lo que impide deshacerlo —publicado, o mes base— lo comprueba
    # `quitar_oficial`, que es por donde pasan los dos caminos. Estaba escrito
    # aquí y no en el otro, así que por el otro se colaba.
    anio, mes = int(guardado['anio']), int(guardado['mes'])
    horarios.quitar_oficial(anio, mes)
    historial.anotar('deshacer_oficial', 'horario', {'periodo': f'{anio}-{mes:02d}'})
    return {'ok': True, 'mensaje': (
        f'{calendario.nombre_del_periodo(mes, anio)} vuelve a estar sin horario oficial. '
        'Elige otra propuesta cuando quieras.')}


@router.delete('/oficial/{anio}/{mes}')
def deshacer_oficial_del_mes(anio: int, mes: int):
    horarios.quitar_oficial(anio, mes)
    historial.anotar('deshacer_oficial', 'horario', {'periodo': f'{anio}-{mes:02d}'})
    return {'ok': True, 'mensaje': (
        f'{calendario.nombre_del_periodo(mes, anio)} vuelve a estar sin horario oficial.')}
