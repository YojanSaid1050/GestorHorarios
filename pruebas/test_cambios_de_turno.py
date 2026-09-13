# -*- coding: utf-8 -*-
"""Cambiar de turno a alguien desde una fecha, y poder deshacerlo.

Un cambio de turno es la única operación de personal que mueve el horario hacia
delante sin tocar el pasado, y la única que arrastra a una segunda persona: las
parejas van siempre en turnos contrarios. Las dos cosas se comprueban aquí.
"""
from __future__ import annotations

from datetime import date

import pytest

from gestor.datos import personal
from gestor.servicios import cambios_de_turno


@pytest.fixture
def con_personal(base):
    from gestor.servicios import siembra
    siembra.sembrar()
    return {p['nombre']: p for p in personal.listar()}


def _una_pareja(con_personal) -> tuple[dict, dict]:
    for persona in con_personal.values():
        if persona.get('pareja_id') and persona['tipo_turno'] == 'rotativo':
            return persona, personal.obtener(int(persona['pareja_id']))
    pytest.skip('la siembra no trae ninguna pareja rotativa')


def _sin_pareja(con_personal) -> dict:
    for persona in con_personal.values():
        if not persona.get('pareja_id') and persona.get('activo', True):
            return persona
    pytest.skip('todo el mundo tiene pareja')


def _otro_turno(persona: dict) -> dict:
    """Un cambio que de verdad cambia algo para esta persona.

    Pedir el turno que ya tiene no es un cambio y la aplicación lo rechaza a
    propósito, así que la prueba tiene que elegir el contrario y no uno fijo.
    """
    contrario = 'PM' if persona.get('turno_fijo') == 'AM' else 'AM'
    return {'tipo_turno': 'fijo', 'turno_fijo': contrario}


# ------------------------------------------------------------- empieza en lunes

def test_la_fecha_se_corre_al_lunes_siguiente(con_personal):
    """El reparto AM/PM se decide una vez por semana.

    Un cambio que arranque un miércoles parte la semana en dos turnos distintos,
    que es justo lo que la programación por semanas completas existe para evitar.
    """
    quien = _sin_pareja(con_personal)
    resultado = cambios_de_turno.programar(
        quien['id'], {'vigente_desde': '2026-11-04', **_otro_turno(quien)})

    assert resultado['vigente_desde'] == '2026-11-09'
    assert resultado['ajustada_a_lunes'] is True
    assert 'lunes' in resultado['mensaje']
    assert date.fromisoformat(resultado['vigente_desde']).weekday() == 0


def test_un_lunes_se_respeta_tal_cual(con_personal):
    quien = _sin_pareja(con_personal)
    resultado = cambios_de_turno.programar(quien['id'], {
        'vigente_desde': '2026-11-09', 'tipo_turno': 'fijo', 'turno_fijo': 'PM'})
    assert resultado['vigente_desde'] == '2026-11-09'
    assert resultado['ajustada_a_lunes'] is False


# --------------------------------------------------------------- la pareja

def test_la_pareja_se_mueve_al_turno_contrario(con_personal):
    """Dos personas emparejadas son la cobertura la una de la otra.

    Cambiar solo a una las dejaría a las dos en el mismo turno, que es
    exactamente el hueco que la pareja existe para tapar.
    """
    uno, otro = _una_pareja(con_personal)
    resultado = cambios_de_turno.programar(uno['id'], {
        'vigente_desde': '2026-11-09', 'tipo_turno': 'fijo', 'turno_fijo': 'AM'})

    assert len(resultado['afectados']) == 2
    assert personal.obtener(uno['id'])['turno_fijo'] == 'AM'
    assert personal.obtener(otro['id'])['turno_fijo'] == 'PM'


def test_se_puede_pedir_que_la_pareja_no_se_mueva(con_personal):
    uno, otro = _una_pareja(con_personal)
    antes = personal.obtener(otro['id'])['tipo_turno']
    cambios_de_turno.programar(uno['id'], {
        'vigente_desde': '2026-11-09', 'tipo_turno': 'fijo', 'turno_fijo': 'AM',
        'aplicar_a_pareja': False})
    assert personal.obtener(otro['id'])['tipo_turno'] == antes


def test_pasar_a_administrativo_no_arrastra_a_la_pareja(con_personal):
    """El administrativo no tiene turno que contrariar: no hay espejo posible."""
    uno, otro = _una_pareja(con_personal)
    antes = personal.obtener(otro['id'])['tipo_turno']
    resultado = cambios_de_turno.programar(uno['id'], {
        'vigente_desde': '2026-11-09', 'tipo_turno': 'administrativo'})
    assert resultado['afectados'] == [uno['nombre']]
    assert personal.obtener(otro['id'])['tipo_turno'] == antes


# ------------------------------------------------------ el pasado no se toca

def test_el_mes_anterior_sigue_leyendo_la_configuración_vieja(con_personal):
    """Es la razón de ser del historial.

    Sin esto, corregir un turno en noviembre reescribía agosto, septiembre y
    octubre, y la oficina veía cómo un horario ya repartido dejaba de coincidir
    con el papel de la pared.
    """
    quien = _sin_pareja(con_personal)
    antes = dict(quien)
    pedido = _otro_turno(quien)
    cambios_de_turno.programar(quien['id'], {'vigente_desde': '2026-11-09', **pedido})

    viejo = personal.configuracion_en(quien['id'], '2026-10-15')
    assert viejo['tipo_turno'] == antes['tipo_turno']
    assert viejo.get('turno_fijo') == antes.get('turno_fijo')
    nuevo = personal.configuracion_en(quien['id'], '2026-11-16')
    assert nuevo['tipo_turno'] == 'fijo'
    assert nuevo['turno_fijo'] == pedido['turno_fijo']


# ------------------------------------------------------------------ deshacer

def test_deshacer_devuelve_a_los_dos_a_lo_que_tenían(con_personal):
    uno, otro = _una_pareja(con_personal)
    antes_uno = personal.obtener(uno['id'])
    antes_otro = personal.obtener(otro['id'])

    cambios_de_turno.programar(uno['id'], {
        'vigente_desde': '2026-11-09', 'tipo_turno': 'fijo', 'turno_fijo': 'AM'})
    resultado = cambios_de_turno.deshacer(uno['id'], '2026-11-09')

    assert sorted(resultado['deshechos']) == sorted([uno['nombre'], otro['nombre']])
    for antes in (antes_uno, antes_otro):
        ahora = personal.obtener(antes['id'])
        for campo in ('tipo_turno', 'turno_fijo', 'inicio_rotacion'):
            assert ahora[campo] == antes[campo], f'{antes["nombre"]}: {campo}'
    assert cambios_de_turno.programados() == []


def test_deshacer_algo_que_no_existe_lo_dice(con_personal):
    quien = _sin_pareja(con_personal)
    with pytest.raises(ValueError, match='No hay ningún cambio'):
        cambios_de_turno.deshacer(quien['id'], '2026-11-09')


def test_corregir_cambia_la_fecha_sin_dejar_dos(con_personal):
    quien = _sin_pareja(con_personal)
    pedido = _otro_turno(quien)
    cambios_de_turno.programar(quien['id'], {'vigente_desde': '2026-11-09', **pedido})
    cambios_de_turno.corregir(quien['id'], '2026-11-09',
                              {'vigente_desde': '2026-11-16', **pedido})

    lista = [c for c in cambios_de_turno.programados() if c['empleado_id'] == quien['id']]
    assert [c['vigente_desde'] for c in lista] == ['2026-11-16']


# --------------------------------------------------------------- la lista

def test_la_lista_dice_lo_de_antes_y_lo_de_después(con_personal):
    quien = _sin_pareja(con_personal)
    cambios_de_turno.programar(quien['id'], {
        'vigente_desde': '2026-11-09', 'tipo_turno': 'fijo', 'turno_fijo': 'PM'})

    cambio = next(c for c in cambios_de_turno.programados()
                  if c['empleado_id'] == quien['id'])
    assert cambio['despues'] == 'Turno fijo PM'
    assert cambio['antes'] != cambio['despues']
    assert cambio['empleado_nombre'] == quien['nombre']
    # La pantalla vuelve a abrir el formulario con estos valores para corregir.
    assert cambio['tipo_turno'] == 'fijo' and cambio['turno_fijo'] == 'PM'


# --------------------------------------------------------- lo que no se deja

def test_no_se_admite_un_cambio_que_no_cambia_nada(con_personal):
    """Un cambio que deja todo igual solo ensucia la lista de cambios.

    Y peor: marca meses como desactualizados y hace volver a generarlos para
    obtener exactamente el mismo horario.
    """
    quien = next((p for p in con_personal.values() if p['tipo_turno'] == 'fijo'), None)
    if quien is None:
        pytest.skip('la siembra no trae a nadie con turno fijo')
    with pytest.raises(ValueError, match='ya está así'):
        cambios_de_turno.programar(quien['id'], {
            'vigente_desde': '2026-11-09', 'tipo_turno': 'fijo',
            'turno_fijo': quien['turno_fijo']})


def test_un_cambio_a_fijo_sin_turno_se_explica(con_personal):
    quien = _sin_pareja(con_personal)
    with pytest.raises(ValueError, match='mañana o de tarde'):
        cambios_de_turno.programar(quien['id'], {
            'vigente_desde': '2026-11-09', 'tipo_turno': 'fijo'})


def test_no_se_puede_empezar_antes_del_alta(con_personal):
    quien = _sin_pareja(con_personal)
    personal.actualizar(quien['id'], {'alta_desde': '2026-12-07'})
    with pytest.raises(ValueError, match='en la plantilla'):
        cambios_de_turno.programar(quien['id'], {
            'vigente_desde': '2026-11-09', 'tipo_turno': 'fijo', 'turno_fijo': 'AM'})


# ------------------------------------------------------ borrar de verdad

def test_no_se_borra_a_quien_aparece_en_un_horario(con_personal, base):
    """Retirar es lo correcto para quien sí trabajó."""
    import json
    quien = _sin_pareja(con_personal)
    with base.transaccion() as conexion:
        conexion.execute(
            'INSERT INTO horarios(anio, mes, datos_json, valido, oficial) VALUES(?,?,?,1,1)',
            (2026, 10, json.dumps({'horario': [{'empleado_id': quien['id'], 'dias': []}]})))
    with pytest.raises(ValueError, match='Usa Retirar'):
        cambios_de_turno.borrar_definitivo(quien['id'])


def test_un_alta_recién_creada_sí_se_puede_borrar(con_personal):
    nuevo = personal.crear({'nombre': 'Prueba Borrable', 'area': 'comunicaciones',
                            'tipo_turno': 'fijo', 'turno_fijo': 'AM'})
    resultado = cambios_de_turno.borrar_definitivo(nuevo)
    assert 'no se pierde nada' in resultado['mensaje']
    assert personal.obtener(nuevo) is None
