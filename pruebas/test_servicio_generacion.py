# -*- coding: utf-8 -*-
"""Armar el mes: las cinco propuestas, elegir una y lo que eso arrastra.

Este servicio no decide turnos; decide **qué se le da al motor** y qué se hace
con lo que devuelve. Las cosas que se comprueban aquí son las que, cuando
faltan, dejan al usuario delante de un botón que no hace nada o con cinco
propuestas que en realidad son la misma.
"""
from __future__ import annotations

import pytest

from gestor.datos import horarios, novedades, personal
from gestor.servicios import generacion

pytestmark = pytest.mark.lenta


@pytest.fixture
def instalacion(base):
    from gestor.servicios import reglas_cobertura, reglas_operacion, siembra
    reglas_cobertura.olvidar_lo_leido()
    reglas_operacion.invalidar_cache()
    return siembra.sembrar()


# ------------------------------------------------------- las cinco propuestas

def test_se_ofrecen_cinco_propuestas_distintas(instalacion):
    """Un horario correcto no es único, y poder comparar es lo que hace útil esto.

    Se comprueba que sean **distintas**: enseñar cinco opciones que en realidad
    son la misma sería peor que enseñar una, porque quien elige creería estar
    decidiendo algo.
    """
    resultado = generacion.generar(10, 2026)
    assert len(resultado.propuestas) == 5

    firmas = {tuple((f['empleado_id'], tuple(d['turno'] for d in f['dias']))
                    for f in p['horario'])
              for p in resultado.propuestas}
    assert len(firmas) == 5, 'hay propuestas repetidas entre las cinco'


def test_las_propuestas_quedan_guardadas_y_se_pueden_recuperar(instalacion):
    resultado = generacion.generar(10, 2026)
    guardadas = horarios.propuestas(2026, 10)
    assert len(guardadas) == 5
    assert {p['horario_id'] for p in resultado.propuestas} == {g['id'] for g in guardadas}


def test_cada_propuesta_dice_si_cumple_y_por_que_no(instalacion):
    """Una propuesta que no cumple se enseña igual, con lo que le falta escrito.

    Ocultarlas dejaría al usuario con menos donde elegir y sin saber por qué.
    """
    resultado = generacion.generar(10, 2026)
    assert any(p['valido'] for p in resultado.propuestas), (
        'ninguna de las cinco cumple: algo va mal en el motor')
    for propuesta in resultado.propuestas:
        if not propuesta['valido']:
            assert propuesta['errores'], 'una propuesta inválida sin motivo escrito'


def test_volver_a_generar_reemplaza_las_propuestas_pero_no_la_oficial(instalacion):
    """La oficial es la que la oficina tiene en la mano: no se pisa."""
    primera = generacion.generar(10, 2026)
    elegida = primera.propuestas[0]['horario_id']
    generacion.marcar_oficial(elegida)

    generacion.generar(10, 2026)
    oficial = horarios.oficial(2026, 10)
    assert oficial is not None and oficial['id'] == elegida, (
        'volver a generar se llevó por delante el horario oficial')


# --------------------------------------------------------- elegir la oficial

def test_marcar_una_oficial_desmarca_a_sus_hermanas(instalacion):
    resultado = generacion.generar(10, 2026)
    generacion.marcar_oficial(resultado.propuestas[0]['horario_id'])
    generacion.marcar_oficial(resultado.propuestas[1]['horario_id'])

    oficiales = [p for p in horarios.propuestas(2026, 10) if p['oficial']]
    assert len(oficiales) == 1
    assert oficiales[0]['id'] == resultado.propuestas[1]['horario_id']


def test_se_avisa_de_los_meses_que_dependian_del_oficial_anterior(instalacion):
    """Cambiar el oficial de octubre cambia de qué parte noviembre.

    No se toca nada por su cuenta —reescribir un mes que la oficina ya tiene
    sería peor— pero se dice cuál ha quedado apoyado en algo que ya no existe.
    """
    octubre = generacion.generar(10, 2026)
    generacion.marcar_oficial(octubre.propuestas[0]['horario_id'])
    noviembre = generacion.generar(11, 2026)
    generacion.marcar_oficial(noviembre.propuestas[0]['horario_id'])

    aviso = generacion.marcar_oficial(octubre.propuestas[1]['horario_id'])
    assert 'noviembre de 2026' in aviso['meses_que_dependian']
    assert 'noviembre de 2026' in aviso['mensaje']


def test_se_puede_deshacer_la_eleccion(instalacion):
    """Marcar por error no puede ser un camino sin vuelta."""
    resultado = generacion.generar(10, 2026)
    generacion.marcar_oficial(resultado.propuestas[0]['horario_id'])
    horarios.quitar_oficial(2026, 10)
    assert horarios.oficial(2026, 10) is None


def test_publicar_exige_haber_elegido_antes(instalacion):
    generacion.generar(10, 2026)
    with pytest.raises(ValueError) as fallo:
        horarios.publicar(2026, 10)
    assert 'oficial' in str(fallo.value)


def test_publicar_deja_constancia_de_cuando(instalacion):
    resultado = generacion.generar(10, 2026)
    generacion.marcar_oficial(resultado.propuestas[0]['horario_id'])
    publicado = horarios.publicar(2026, 10)
    assert publicado['publicado'] and publicado['publicado_en']


# ----------------------------------------------------- cuando no se puede

def test_sin_el_mes_anterior_se_dice_que_hacer(instalacion):
    with pytest.raises(generacion.NoSePuedeGenerar) as fallo:
        generacion.generar(12, 2026)
    mensaje = str(fallo.value)
    assert 'noviembre de 2026' in mensaje, 'el aviso tiene que nombrar el mes que falta'
    assert 'marca como oficial' in mensaje, 'y decir qué hacer, no solo que no se puede'


def test_sin_personal_se_dice_en_castellano(instalacion):
    from gestor.datos.base import transaccion
    with transaccion() as conexion:
        conexion.execute('DELETE FROM empleados')
    with pytest.raises(generacion.NoSePuedeGenerar) as fallo:
        generacion.generar(10, 2026)
    assert 'plantilla' in str(fallo.value)


# ------------------------------------------- las novedades llegan al horario

def test_unas_vacaciones_aprobadas_aparecen_en_el_mes(instalacion):
    quien = personal.listar()[0]
    solicitud = novedades.crear_solicitud({
        'empleado_id': quien['id'], 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-12', 'fecha_fin': '2026-10-16'})
    novedades.resolver_solicitud(solicitud, 'aprobada')

    resultado = generacion.generar(10, 2026)
    fila = next(f for f in resultado.propuestas[0]['horario']
                if f['empleado_id'] == quien['id'])
    turnos = {d['fecha']: d['turno'] for d in fila['dias']}
    assert turnos['2026-10-12'] == 'VAC', turnos['2026-10-12']
    assert turnos['2026-10-16'] == 'VAC'


def test_una_solicitud_pendiente_no_cambia_nada(instalacion):
    """Lo que no se ha aprobado todavía no es una decisión."""
    quien = personal.listar()[0]
    novedades.crear_solicitud({
        'empleado_id': quien['id'], 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-12', 'fecha_fin': '2026-10-16'})

    resultado = generacion.generar(10, 2026)
    fila = next(f for f in resultado.propuestas[0]['horario']
                if f['empleado_id'] == quien['id'])
    assert not any(d['turno'] == 'VAC' for d in fila['dias'])


def test_una_asignacion_administrativa_aparece_en_el_dia_pedido(instalacion):
    quien = next(p for p in personal.listar() if p['area'] == 'gestion_social')
    novedades.crear_asignacion({
        'empleado_id': quien['id'], 'tipo': 'asignacion_administrativa',
        'fechas': ['2026-10-14'], 'horario_administrativo': 'ADM-GS',
        'descripcion': 'Reunión de área'})

    resultado = generacion.generar(10, 2026)
    fila = next(f for f in resultado.propuestas[0]['horario']
                if f['empleado_id'] == quien['id'])
    dia = next(d for d in fila['dias'] if d['fecha'] == '2026-10-14')
    assert dia['turno'] == 'ADM-GS', dia['turno']
