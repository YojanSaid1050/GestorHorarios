# -*- coding: utf-8 -*-
"""La plantilla de un mes es la de ese mes, no la de hoy.

`personal.listar()` devuelve la ficha final de cada persona. Generar un mes con
eso aplica el futuro hacia atrás: programar que alguien pasa a rotativo desde el
2 de noviembre y generar octubre daba un octubre con esa persona ya rotando.

Lo llamativo es que el motor sabía hacerlo bien desde el principio.
`gestor/dominio/vigencia.py` resuelve la configuración día a día,
`motor/construccion.py` la usa y marca el día en que empieza a regir. Esperaban
`config_inicial` y `cambios_config`, y nadie se los daba nunca: la pieza estaba
entera y desconectada. Lo que faltaba era `personal.para_periodo`.
"""
from __future__ import annotations

import pytest

from gestor.datos import personal
from gestor.servicios import cambios_de_turno, generacion

#: Octubre de 2026 va del 28 de septiembre al 1 de noviembre: los periodos se
#: solapan y la primera semana es también la última del mes anterior.
INICIO, FIN = '2026-09-28', '2026-11-01'


@pytest.fixture
def con_personal(base):
    from gestor.servicios import reglas_cobertura, reglas_operacion, siembra
    reglas_cobertura.olvidar_lo_leido()
    reglas_operacion.invalidar_cache()
    siembra.sembrar()
    return next(p for p in personal.listar()
                if p['tipo_turno'] == 'fijo' and not p.get('pareja_id'))


def _ficha_del_periodo(empleado_id: int) -> dict:
    return next(p for p in personal.para_periodo(INICIO, FIN)
                if int(p['id']) == int(empleado_id))


def _dia(propuesta: dict, empleado_id: int, fecha: str) -> dict:
    fila = next(f for f in propuesta['horario']
                if int(f['empleado_id']) == int(empleado_id))
    return next(d for d in fila['dias'] if str(d['fecha']) == fecha)


# --------------------------------------------- lo de noviembre no rige en octubre

def test_un_cambio_de_noviembre_no_se_aplica_en_octubre(con_personal):
    persona = con_personal
    cambios_de_turno.programar(persona['id'], {
        'tipo_turno': 'rotativo', 'inicio_rotacion': 'AM',
        'vigente_desde': '2026-11-02'})

    assert personal.obtener(persona['id'])['tipo_turno'] == 'rotativo', (
        'la ficha de hoy sí tiene que reflejar el cambio')
    ficha = _ficha_del_periodo(persona['id'])
    assert ficha['tipo_turno'] == 'fijo'
    assert ficha['config_inicial']['tipo_turno'] == 'fijo'
    assert ficha['cambios_config'] == []


@pytest.mark.lenta
def test_el_mes_generado_tampoco_lo_aplica(con_personal):
    """Que es donde se veía: un día de octubre etiquetado como rotativo."""
    persona = con_personal
    cambios_de_turno.programar(persona['id'], {
        'tipo_turno': 'rotativo', 'inicio_rotacion': 'AM',
        'vigente_desde': '2026-11-02'})

    propuesta = generacion.generar(10, 2026).propuestas[0]
    assert _dia(propuesta, persona['id'], '2026-10-14')['cfg_tipo_turno'] == 'fijo'


# ------------------------------------- y un cambio de dentro sí, desde su lunes

def test_un_cambio_dentro_del_mes_es_una_transición(con_personal):
    persona = con_personal
    cambios_de_turno.programar(persona['id'], {
        'tipo_turno': 'rotativo', 'inicio_rotacion': 'AM',
        'vigente_desde': '2026-10-19'})

    ficha = _ficha_del_periodo(persona['id'])
    assert ficha['config_inicial']['tipo_turno'] == 'fijo'
    assert [(c['desde'], c['cfg']['tipo_turno'], c['afecta_turno'])
            for c in ficha['cambios_config']] == [('2026-10-19', 'rotativo', True)]


@pytest.mark.lenta
def test_el_mes_generado_cambia_el_lunes_y_no_antes(con_personal):
    """Antes del lunes 19 sigue siendo fija; desde el 19, rotativa.

    Y el día 19 queda marcado como `cambio_vigencia`: el turno puede cambiar
    ahí por decisión de alguien, no por un fallo del reparto.
    """
    persona = con_personal
    cambios_de_turno.programar(persona['id'], {
        'tipo_turno': 'rotativo', 'inicio_rotacion': 'AM',
        'vigente_desde': '2026-10-19'})

    propuesta = generacion.generar(10, 2026).propuestas[0]
    assert _dia(propuesta, persona['id'], '2026-10-12')['cfg_tipo_turno'] == 'fijo'
    assert _dia(propuesta, persona['id'], '2026-10-19')['cfg_tipo_turno'] == 'rotativo'
    assert _dia(propuesta, persona['id'], '2026-10-19')['cambio_vigencia'] is True
    assert _dia(propuesta, persona['id'], '2026-10-12')['cambio_vigencia'] is False


# ------------------------------------------------------------ y sin cambios, igual

def test_sin_cambios_programados_la_ficha_es_la_de_siempre(con_personal):
    """Que es el caso de todos los días, y no puede salir más caro ni distinto."""
    ficha = _ficha_del_periodo(con_personal['id'])
    assert ficha['tipo_turno'] == con_personal['tipo_turno']
    assert ficha['turno_fijo'] == con_personal['turno_fijo']
    assert 'cambios_config' not in ficha
