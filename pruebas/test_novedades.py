# -*- coding: utf-8 -*-
"""Solicitudes y asignaciones: lo que aparta a alguien del horario normal.

El caso que hay que tener siempre delante al leer esto es el del **período que
se solapa**. Una novedad del 1 de octubre pertenece a dos meses a la vez, y
buscarla por mes natural hacía que septiembre siguiera dando por bueno un
horario que ya no coincidía con lo aprobado.
"""
from __future__ import annotations

import pytest

from gestor.datos import novedades


@pytest.fixture
def con_personal(base):
    from gestor.servicios import siembra
    siembra.sembrar()
    from gestor.datos import personal
    return {p['nombre']: p['id'] for p in personal.listar()}


def _alguien(con_personal):
    return next(iter(con_personal.values()))


# ------------------------------------------------------------- solicitudes

def test_una_solicitud_nace_pendiente(con_personal):
    """Pendiente no es aprobada. Lo pendiente todavía no es una decisión."""
    sid = novedades.crear_solicitud({
        'empleado_id': _alguien(con_personal), 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-05', 'fecha_fin': '2026-10-09'})
    solicitud = novedades.listar_solicitudes()[0]
    assert solicitud['id'] == sid
    assert solicitud['estado'] == 'pendiente'
    assert novedades.solicitudes_para_el_motor(10, 2026) == []


def test_solo_lo_aprobado_llega_al_motor(con_personal):
    quien = _alguien(con_personal)
    aprobada = novedades.crear_solicitud({
        'empleado_id': quien, 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-05', 'fecha_fin': '2026-10-09'})
    novedades.crear_solicitud({
        'empleado_id': quien, 'tipo': 'permiso',
        'fecha_inicio': '2026-10-20', 'fecha_fin': '2026-10-20'})
    novedades.resolver_solicitud(aprobada, 'aprobada')

    para_el_motor = novedades.solicitudes_para_el_motor(10, 2026)
    assert [s['id'] for s in para_el_motor] == [aprobada]


def test_una_novedad_del_1_de_octubre_la_ven_los_dos_meses(con_personal):
    """El atajo que ya costó caro.

    El 1 de octubre está en el período de septiembre —que llega hasta el
    domingo 4— y en el de octubre. Las dos programaciones tienen que enterarse.
    """
    sid = novedades.crear_solicitud({
        'empleado_id': _alguien(con_personal), 'tipo': 'permiso',
        'fecha_inicio': '2026-10-01', 'fecha_fin': '2026-10-01'})
    novedades.resolver_solicitud(sid, 'aprobada')

    for mes, anio in ((9, 2026), (10, 2026)):
        ids = [s['id'] for s in novedades.solicitudes_para_el_motor(mes, anio)]
        assert sid in ids, f'{anio}-{mes:02d} no ve la novedad del 1 de octubre'


def test_una_novedad_de_otro_mes_no_se_cuela(con_personal):
    sid = novedades.crear_solicitud({
        'empleado_id': _alguien(con_personal), 'tipo': 'permiso',
        'fecha_inicio': '2026-12-15', 'fecha_fin': '2026-12-15'})
    novedades.resolver_solicitud(sid, 'aprobada')
    assert novedades.solicitudes_para_el_motor(10, 2026) == []


def test_una_novedad_semanal_sin_final_llega_hasta_el_fin_del_periodo(con_personal):
    """«Los martes libra», hasta nuevo aviso.

    Sin esto valía solo la semana en que se pidió, y había que volver a pedirla
    cada lunes.
    """
    sid = novedades.crear_solicitud({
        'empleado_id': _alguien(con_personal), 'tipo': 'descanso',
        'fecha_inicio': '2026-10-06', 'fecha_fin': '2026-10-06',
        'sin_fecha_fin': True, 'modo_periodo': 'semanal',
        'dia_semana_recurrente': 1})
    novedades.resolver_solicitud(sid, 'aprobada')

    encontradas = novedades.solicitudes_para_el_motor(10, 2026)
    assert encontradas, 'la novedad recurrente no llegó al motor'
    assert encontradas[0]['fecha_fin'] == '2026-11-01', (
        'una novedad sin final tiene que llegar hasta el último día del período')


def test_dos_novedades_aprobadas_sobre_el_mismo_dia_se_detectan(con_personal):
    """Aprobar dos cosas para el mismo día es una contradicción sin solución.

    La aplicación no puede decidir cuál vale, así que lo detecta antes de
    aprobar y lo explica en vez de aplicar la última en llegar.
    """
    quien = _alguien(con_personal)
    primera = novedades.crear_solicitud({
        'empleado_id': quien, 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-05', 'fecha_fin': '2026-10-09'})
    novedades.resolver_solicitud(primera, 'aprobada')

    choques = novedades.solapadas(quien, '2026-10-07', '2026-10-07')
    assert [c['id'] for c in choques] == [primera]

    assert not novedades.solapadas(quien, '2026-10-20', '2026-10-21')


def test_borrar_una_solicitud_la_quita_de_verdad(con_personal):
    sid = novedades.crear_solicitud({
        'empleado_id': _alguien(con_personal), 'tipo': 'permiso',
        'fecha_inicio': '2026-10-05', 'fecha_fin': '2026-10-05'})
    novedades.borrar_solicitud(sid)
    assert novedades.listar_solicitudes() == []


def test_una_novedad_no_puede_terminar_antes_de_empezar(con_personal):
    """El fallo que encontró el recorrido de formularios de `qa/interfaz.py`.

    Unas vacaciones «del 20 al 13» se guardaban sin una palabra, se dejaban
    aprobar y al generar el mes no producían ni un solo día, porque el rango
    estaba vacío. Lo que veía la oficina era una novedad aprobada que no salía
    en el horario: parecía un fallo del reparto, y por eso podía durar meses.
    """
    with pytest.raises(ValueError) as fallo:
        novedades.crear_solicitud({
            'empleado_id': _alguien(con_personal), 'tipo': 'vacaciones',
            'fecha_inicio': '2026-10-20', 'fecha_fin': '2026-10-13'})
    assert '2026-10-13' in str(fallo.value) and '2026-10-20' in str(fallo.value)
    assert novedades.listar_solicitudes() == []


def test_corregir_una_novedad_tampoco_deja_invertir_las_fechas(con_personal):
    """Se comprueba también al editar: es donde más se cometen estos errores.

    Al dar de alta se escriben las dos fechas seguidas y se ven juntas. Al
    corregir se toca una sola, muchas veces sin mirar la otra, que es cuando el
    rango se da la vuelta sin que nadie lo note.
    """
    sid = novedades.crear_solicitud({
        'empleado_id': _alguien(con_personal), 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-13', 'fecha_fin': '2026-10-20'})
    with pytest.raises(ValueError):
        novedades.actualizar_solicitud(sid, {'fecha_inicio': '2026-10-13',
                                             'fecha_fin': '2026-10-01'})
    assert novedades.listar_solicitudes()[0]['fecha_fin'] == '2026-10-20', (
        'el rechazo tiene que dejar la solicitud como estaba')


def test_un_solo_día_sigue_valiendo(con_personal):
    """El caso corriente: un permiso de una jornada, con las dos fechas iguales.

    Se escribe porque la comprobación anterior se podría haber escrito con un
    «>» en vez de un «>=», y entonces el permiso de un día —que es el más
    frecuente de todos— habría dejado de poder guardarse.
    """
    sid = novedades.crear_solicitud({
        'empleado_id': _alguien(con_personal), 'tipo': 'permiso',
        'fecha_inicio': '2026-10-14', 'fecha_fin': '2026-10-14'})
    assert novedades.listar_solicitudes()[0]['id'] == sid


def test_sin_fecha_de_fin_no_se_reprocha_nada(con_personal):
    """Una incapacidad sin alta todavía: la fecha de fin llega vacía."""
    sid = novedades.crear_solicitud({
        'empleado_id': _alguien(con_personal), 'tipo': 'incapacidad',
        'fecha_inicio': '2026-10-14', 'fecha_fin': None, 'sin_fecha_fin': True})
    assert novedades.listar_solicitudes()[0]['id'] == sid


def test_un_tipo_inventado_se_rechaza(con_personal):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        novedades.crear_solicitud({
            'empleado_id': _alguien(con_personal), 'tipo': 'lo_que_sea',
            'fecha_inicio': '2026-10-05', 'fecha_fin': '2026-10-05'})


# ------------------------------------------------------------ asignaciones

def test_una_asignacion_con_fechas_solo_toca_su_periodo(con_personal):
    quien = _alguien(con_personal)
    novedades.crear_asignacion({
        'empleado_id': quien, 'tipo': 'descanso_extra',
        'fechas': ['2026-10-14'], 'descripcion': 'Día de la familia'})

    assert len(novedades.asignaciones_para_el_motor(10, 2026)) == 1
    assert novedades.asignaciones_para_el_motor(12, 2026) == []


def test_una_asignacion_recurrente_se_despliega_en_dias_concretos(con_personal):
    """El motor trabaja con fechas, no con «todos los miércoles»."""
    novedades.crear_asignacion({
        'empleado_id': _alguien(con_personal), 'tipo': 'asignacion_administrativa',
        'recurrente_indefinido': True, 'dias_semana': [2],
        'horario_administrativo': 'ADM-GS'})

    desplegada = novedades.asignaciones_para_el_motor(10, 2026)[0]
    fechas = desplegada['fechas']
    assert len(fechas) == 5, 'octubre de 2026 tiene cinco miércoles en su período'
    from datetime import date
    assert all(date.fromisoformat(f).weekday() == 2 for f in fechas)


def test_liberar_la_cobertura_llega_al_motor_con_el_nombre_que_entiende(con_personal):
    """Cuando alguien pasa a jornada administrativa y hay que relevarle."""
    novedades.crear_asignacion({
        'empleado_id': _alguien(con_personal), 'tipo': 'asignacion_administrativa',
        'fechas': ['2026-10-14'], 'horario_administrativo': 'ADM-GS',
        'libera_cobertura': True})
    assert novedades.asignaciones_para_el_motor(10, 2026)[0]['cubrir_pm'] is True


def test_borrar_a_una_persona_se_lleva_sus_novedades(con_personal):
    from gestor.datos.base import transaccion
    quien = _alguien(con_personal)
    novedades.crear_solicitud({
        'empleado_id': quien, 'tipo': 'permiso',
        'fecha_inicio': '2026-10-05', 'fecha_fin': '2026-10-05'})
    novedades.crear_asignacion({
        'empleado_id': quien, 'tipo': 'descanso_extra', 'fechas': ['2026-10-14']})

    with transaccion() as conexion:
        conexion.execute('DELETE FROM empleados WHERE id=?', (quien,))

    assert novedades.listar_solicitudes() == []
    assert novedades.listar_asignaciones() == []
