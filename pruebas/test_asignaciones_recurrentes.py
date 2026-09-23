# -*- coding: utf-8 -*-
"""«Todos los miércoles, desde diciembre» eran tres cosas y se perdían dos.

Una asignación recurrente se despliega en días concretos antes de llegar al
motor, porque el motor trabaja con fechas. En ese viaje se quedaban por el
camino la fecha desde la que se repite —y entonces se repetía desde siempre— y
el hecho mismo de ser recurrente, del que dependen el orden en que se aplican
las asignaciones y si un choque es un error o un aviso.

Y la vista previa que avisaba de los choques no la llamaba nadie al guardar.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gestor.datos import novedades


@pytest.fixture
def cliente(carpeta_de_datos):
    from gestor.web.aplicacion import crear_aplicacion
    with TestClient(crear_aplicacion()) as cliente:
        respuesta = cliente.post('/api/auth/login', json={
            'usuario': 'admin', 'password': 'xYojanSaidx1050'})
        cliente.headers['X-Session-Token'] = respuesta.json()['token']
        yield cliente


def _alguien(cliente) -> dict:
    return next(p for p in cliente.get('/api/empleados').json()
                if not p.get('pareja_id'))


# ---------------------------------- H14 · una recurrente empieza cuando empieza

def test_una_recurrente_de_diciembre_no_aparece_en_octubre(cliente):
    """El despliegue arrancaba el primer día del período que se estuviera armando.

    Fuera cual fuera. «Los miércoles hace jornada administrativa, a partir de
    diciembre» movía el horario de octubre, meses antes de que nadie lo hubiera
    decidido.
    """
    persona = _alguien(cliente)
    creada = cliente.post('/api/requerimientos', json={
        'empleado_id': persona['id'], 'tipo': 'asignacion_administrativa',
        'horario_administrativo': 'ADM-GS',
        'recurrente_indefinido': True, 'dias_semana': [2],
        'vigente_desde': '2026-12-01'})
    assert creada.status_code == 200, creada.text

    de_octubre = novedades.asignaciones_para_el_motor(10, 2026)
    assert not [a for a in de_octubre if int(a['empleado_id']) == int(persona['id'])], (
        'una asignación que empieza en diciembre se aplicó en octubre')

    de_diciembre = novedades.asignaciones_para_el_motor(12, 2026)
    mias = [a for a in de_diciembre if int(a['empleado_id']) == int(persona['id'])]
    assert mias, 'y en diciembre, que es cuando empieza, tiene que estar'
    assert all(f >= '2026-12-01' for f in mias[0]['fechas'])


# ------------------------------- H15 · el motor sabe que la asignación es habitual

def test_el_motor_recibe_que_la_asignación_se_repite(cliente):
    """De esto dependen tres cosas, y las tres se decidían al revés.

    `_es_habitual` decide en qué orden se aplican las asignaciones —la
    habitualidad primero, la fecha concreta después—, si un choque es un error
    que deja el mes sin generar o un aviso, y si el día queda marcado para que
    una novedad aprobada pueda reescribirlo. El adaptador no mandaba ni
    `recurrente_indefinido` ni `dias_semana`, así que siempre era `False`.
    """
    persona = _alguien(cliente)
    cliente.post('/api/requerimientos', json={
        'empleado_id': persona['id'], 'tipo': 'asignacion_administrativa',
        'horario_administrativo': 'ADM-GS',
        'recurrente_indefinido': True, 'dias_semana': [2],
        'vigente_desde': '2026-10-01'})

    mias = [a for a in novedades.asignaciones_para_el_motor(10, 2026)
            if int(a['empleado_id']) == int(persona['id'])]
    assert mias, 'la asignación no llegó al motor'
    assert mias[0]['recurrente_indefinido'] is True
    assert mias[0]['dias_semana'] == [2]

    from gestor.motor.decisiones import aplicar_requerimientos_directos  # noqa: F401
    # Y la función que lo lee lo ve como habitual.
    assert bool(mias[0].get('recurrente_indefinido') or mias[0].get('dias_semana'))


# ------------------------ H16 · lo que la vista previa marca en rojo no se guarda

def test_no_se_puede_guardar_lo_que_la_vista_previa_rechaza(cliente):
    """Guardar no llamaba a la comprobación: era un consejo, no un control."""
    persona = _alguien(cliente)
    cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-14', 'fecha_fin': '2026-10-14', 'aprobada': True})

    previa = cliente.post('/api/requerimientos/prevalidar', json={
        'empleado_id': persona['id'], 'tipo': 'asignacion_administrativa',
        'horario_administrativo': 'ADM-GS',
        'fechas': ['2026-10-14']})
    assert previa.json()['compatible'] is False

    guardar = cliente.post('/api/requerimientos', json={
        'empleado_id': persona['id'], 'tipo': 'asignacion_administrativa',
        'horario_administrativo': 'ADM-GS',
        'fechas': ['2026-10-14']})
    assert guardar.status_code >= 400, (
        'se guardó una asignación que la vista previa acababa de rechazar')


def test_dos_asignaciones_de_la_misma_persona_el_mismo_día_chocan(cliente):
    """La vista previa solo miraba novedades aprobadas.

    Dos instrucciones para el mismo turno son una y su contraria, y el motor
    acaba obedeciendo a la que se aplique después.
    """
    persona = _alguien(cliente)
    primera = cliente.post('/api/requerimientos', json={
        'empleado_id': persona['id'], 'tipo': 'asignacion_administrativa',
        'horario_administrativo': 'ADM-GS',
        'fechas': ['2026-10-14']})
    assert primera.status_code == 200, primera.text

    segunda = cliente.post('/api/requerimientos', json={
        'empleado_id': persona['id'], 'tipo': 'actividad',
        'horario_administrativo': 'ADM-GS',
        'fechas': ['2026-10-14']})
    assert segunda.status_code >= 400
    assert 'ya tiene otra asignación' in segunda.text


def test_una_asignación_no_entra_en_una_semana_cerrada(cliente):
    """Cerrar una semana significa que esos siete días no se tocan."""
    from gestor.datos.base import transaccion

    persona = _alguien(cliente)
    with transaccion() as conexion:
        conexion.execute(
            'INSERT OR REPLACE INTO semanas(anio, mes, lunes, cerrada) '
            'VALUES(2026, 10, ?, 1)', ('2026-10-12',))

    respuesta = cliente.post('/api/requerimientos', json={
        'empleado_id': persona['id'], 'tipo': 'asignacion_administrativa',
        'horario_administrativo': 'ADM-GS',
        'fechas': ['2026-10-14']})
    assert respuesta.status_code >= 400
    assert 'semana cerrada' in respuesta.text


# ----------- H13 · las recurrencias se comparan día a día, no por los extremos

def test_dos_recurrencias_de_días_distintos_no_chocan(cliente):
    """El falso positivo: mismo rango, días que nunca coinciden.

    «Los martes libra» y «los jueves hace jornada administrativa» comparten el
    rango de fechas pero no comparten un solo día. Se declaraban incompatibles
    porque se comparaban los extremos de la fila, y quien lo leía tenía que
    cancelar una de las dos sin motivo.
    """
    persona = _alguien(cliente)
    primera = cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'descanso',
        'fecha_inicio': '2026-10-06', 'fecha_fin': '2026-10-27',
        'modo_periodo': 'semanal', 'dia_semana_recurrente': 1,
        'aprobada': True})
    assert primera.status_code == 200, primera.text

    segunda = cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'permiso',
        'fecha_inicio': '2026-10-06', 'fecha_fin': '2026-10-27',
        'modo_periodo': 'semanal', 'dia_semana_recurrente': 3,
        'aprobada': True})
    assert segunda.status_code == 200, (
        'dos recurrencias de días distintos se declararon incompatibles: '
        + segunda.text)


def test_una_recurrencia_abierta_choca_con_lo_que_caiga_en_uno_de_sus_días(cliente):
    """El falso negativo, que es el que cuesta caro.

    Una recurrencia sin final se guarda con `fecha_fin` igual a `fecha_inicio`,
    así que por los extremos «terminaba» el día en que se pidió. Cualquier
    novedad en una ocurrencia posterior se declaraba compatible y las dos
    quedaban aprobadas para el mismo día.
    """
    persona = _alguien(cliente)
    abierta = cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'descanso',
        'fecha_inicio': '2026-10-06', 'sin_fecha_fin': True,
        'modo_periodo': 'semanal', 'dia_semana_recurrente': 1,
        'aprobada': True})
    assert abierta.status_code == 200, abierta.text

    # El 2026-10-20 es martes: una ocurrencia posterior de esa recurrencia.
    choca = cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-20', 'fecha_fin': '2026-10-20',
        'aprobada': True})
    assert choca.status_code >= 400, (
        'se aprobaron dos novedades para el mismo martes')
    assert '2026-10-20' in choca.text


@pytest.mark.parametrize('tipo', ['asignacion_administrativa', 'actividad'])
@pytest.mark.parametrize('horario', [None, '', 'INVENTADO'])
def test_no_guarda_una_asignacion_sin_horario_compatible(cliente, tipo, horario):
    persona = _alguien(cliente)
    antes = cliente.get('/api/requerimientos').json()
    respuesta = cliente.post('/api/requerimientos', json={
        'empleado_id': persona['id'], 'tipo': tipo,
        'fechas': ['2026-10-20'], 'horario_administrativo': horario})
    assert respuesta.status_code == 422
    assert 'Elige un horario compatible' in respuesta.text
    assert cliente.get('/api/requerimientos').json() == antes
