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


# ----------------------------------- una corrección que falla no deja rastro

def test_una_corrección_inválida_no_borra_el_cambio_original(con_personal):
    """Antes se deshacía primero y se programaba después.

    Si lo segundo fallaba —un turno de inicio inválido bastaba— el cambio
    original ya se había perdido. El mensaje lo contaba honestamente («quedó
    deshecho y hay que volver a programarlo»), pero el dato no volvía: una
    operación que falla no puede dejar rastro.
    """
    persona = _sin_pareja(con_personal)
    cambios_de_turno.programar(persona['id'], {
        **_otro_turno(persona), 'vigente_desde': '2026-10-05'})
    despues_de_programar = dict(personal.obtener(persona['id']))

    with pytest.raises(ValueError) as fallo:
        cambios_de_turno.corregir(persona['id'], '2026-10-05', {
            'tipo_turno': 'rotativo', 'inicio_rotacion': 'XX',
            'vigente_desde': '2026-10-12'})
    # Y el mensaje dice qué está mal en lo que se pidió, en vez del antiguo
    # «quedó deshecho y hay que volver a programarlo», que describía un
    # destrozo en lugar de un motivo.
    assert 'con qué turno empieza' in str(fallo.value)

    ahora = personal.obtener(persona['id'])
    assert ahora['tipo_turno'] == despues_de_programar['tipo_turno']
    assert ahora['turno_fijo'] == despues_de_programar['turno_fijo']
    mios = [c for c in cambios_de_turno.programados()
            if int(c['empleado_id']) == int(persona['id'])]
    assert [c['vigente_desde'] for c in mios] == ['2026-10-05']


def test_una_corrección_que_no_cambiaría_nada_tampoco_deja_rastro(con_personal):
    """El otro camino: el error no salta al validar el pedido, sino al aplicarlo.

    Corregir un cambio para dejarlo exactamente como estaba la persona antes de
    él es un cambio que no cambia nada, y la aplicación lo rechaza —bien—. Pero
    para entonces ya se ha deshecho: sin la copia de seguridad, el rechazo se
    llevaba por delante lo que había.
    """
    persona = _sin_pareja(con_personal)
    antes = dict(personal.obtener(persona['id']))
    cambios_de_turno.programar(persona['id'], {
        **_otro_turno(persona), 'vigente_desde': '2026-10-05'})

    with pytest.raises(ValueError):
        cambios_de_turno.corregir(persona['id'], '2026-10-05', {
            'tipo_turno': antes['tipo_turno'], 'turno_fijo': antes['turno_fijo'],
            'inicio_rotacion': antes.get('inicio_rotacion'),
            'vigente_desde': '2026-10-12'})

    mios = [c for c in cambios_de_turno.programados()
            if int(c['empleado_id']) == int(persona['id'])]
    assert [c['vigente_desde'] for c in mios] == ['2026-10-05']


# --------------------------------- cancelar uno antiguo no pisa los de después

def test_cancelar_un_cambio_antiguo_respeta_los_posteriores(con_personal):
    """«Deshacer» es «esto no llegó a pasar», no «vuelve a como estabas entonces».

    La diferencia solo se nota cuando hay un cambio posterior programado, y
    entonces se nota mucho: cancelar el de octubre devolvía a la persona a lo
    que tenía en septiembre, mientras el cambio de noviembre seguía guardado y
    seguía apareciendo en la lista sin efecto ninguno.
    """
    persona = _sin_pareja(con_personal)
    cambios_de_turno.programar(persona['id'], {
        **_otro_turno(persona), 'vigente_desde': '2026-10-05'})
    cambios_de_turno.programar(persona['id'], {
        'tipo_turno': 'rotativo', 'inicio_rotacion': 'AM',
        'vigente_desde': '2026-11-02'})

    cambios_de_turno.deshacer(persona['id'], '2026-10-05')

    ahora = personal.obtener(persona['id'])
    assert ahora['tipo_turno'] == 'rotativo', (
        'cancelar el cambio de octubre se llevó por delante el de noviembre')
    mios = [c for c in cambios_de_turno.programados()
            if int(c['empleado_id']) == int(persona['id'])]
    assert [c['vigente_desde'] for c in mios] == ['2026-11-02']


def test_cancelar_el_último_sigue_devolviendo_lo_que_había(con_personal):
    """El caso normal no cambia, y conviene que quede dicho."""
    persona = _sin_pareja(con_personal)
    antes = dict(personal.obtener(persona['id']))
    cambios_de_turno.programar(persona['id'], {
        **_otro_turno(persona), 'vigente_desde': '2026-10-05'})

    cambios_de_turno.deshacer(persona['id'], '2026-10-05')

    ahora = personal.obtener(persona['id'])
    assert ahora['tipo_turno'] == antes['tipo_turno']
    assert ahora['turno_fijo'] == antes['turno_fijo']


def test_la_pareja_que_se_deshace_es_la_que_cambió_aquel_día(con_personal):
    """Y no la de hoy, que puede ser otra.

    Se buscaba a la pareja **actual** con un cambio de la misma fecha. Si la
    pareja había cambiado desde entonces, deshacer le tocaba el turno a alguien
    que nunca estuvo en aquel cambio, y dejaba sin deshacer a quien sí.
    """
    from gestor.datos.base import abierta

    una, otra = _una_pareja(con_personal)
    tercera = next(p for p in personal.listar()
                   if int(p['id']) not in (int(una['id']), int(otra['id']))
                   and p['area'] == una['area'] and p.get('activo', True))

    cambios_de_turno.programar(una['id'], {
        'tipo_turno': 'fijo', 'turno_fijo': 'AM', 'vigente_desde': '2026-10-05'})

    with abierta() as conexion:
        grupos = {int(f['empleado_id']): f['grupo'] for f in conexion.execute(
            'SELECT empleado_id, grupo FROM empleados_historial '
            'WHERE vigente_desde=?', ('2026-10-05',))}
    assert grupos[int(una['id'])], 'el cambio no dejó escrito quién cambió con quién'
    assert grupos[int(una['id'])] == grupos[int(otra['id'])]

    # Y ahora la pareja es otra persona. El cambio de octubre sigue siendo el de
    # las dos de antes.
    personal.emparejar(int(una['id']), int(tercera['id']))

    resultado = cambios_de_turno.deshacer(una['id'], '2026-10-05')
    assert sorted(resultado['deshechos']) == sorted([una['nombre'], otra['nombre']]), (
        f'se deshizo el cambio de {resultado["deshechos"]}')
    assert tercera['nombre'] not in resultado['deshechos'], (
        'se le tocó el turno a alguien que no estuvo en aquel cambio')
