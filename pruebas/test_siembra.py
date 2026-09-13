# -*- coding: utf-8 -*-
"""Lo que trae una instalación recién hecha.

Agosto y septiembre de 2026 no se generan: se transcriben del Excel que la
oficina ya trabajó. El archivo que llega solo dice «esta persona, este día, este
turno», y todo lo demás —qué día de la semana es, si es festivo, a qué semana
pertenece, cuántas horas suma— **se calcula aquí**, con las mismas funciones que
usa el motor.

Esta prueba existe por un fallo que solo se veía abriendo la aplicación: al
elegir agosto o septiembre, la cabecera de la cuadrícula decía «undefined» en
cada columna, los fines de semana y los festivos no se distinguían de un día
normal, y todas las horas salían a cero. La transcripción era correcta; lo que
faltaba era el calendario. Ninguna prueba de Python lo habría cogido, porque los
turnos estaban bien.
"""
from __future__ import annotations

import pytest

from gestor.datos import horarios
from gestor.dominio import calendario

#: Lo que la pantalla necesita de cada casilla para poder pintarla.
CAMPOS_DEL_CALENDARIO = (
    'dia', 'mes', 'anio', 'dia_semana', 'dia_semana_numero', 'lunes_semana',
    'es_sabado', 'es_domingo', 'es_festivo', 'es_ultimo_viernes_administrativo',
    'mes_propio', 'pertenece',
)

MESES_BASE = ((2026, 8), (2026, 9))


@pytest.fixture
def sembrada(base):
    from gestor.servicios import siembra
    resultado = siembra.sembrar()
    assert not resultado.faltan, f'faltan archivos iniciales: {resultado.faltan}'
    return base


@pytest.mark.parametrize(('anio', 'mes'), MESES_BASE)
def test_los_meses_base_quedan_publicados(sembrada, anio, mes):
    guardado = horarios.oficial(anio, mes)
    assert guardado is not None, f'{anio}-{mes:02d} tendría que venir en la instalación'
    assert guardado['publicado'], 'la oficina ya lo trabajó: llega publicado'
    assert guardado['datos']['horario'], 'no puede venir vacío'


@pytest.mark.parametrize(('anio', 'mes'), MESES_BASE)
def test_cada_casilla_trae_su_día_del_calendario(sembrada, anio, mes):
    """Sin esto la cabecera de la cuadrícula decía «undefined» en cada columna."""
    guardado = horarios.oficial(anio, mes)
    sin_calendario = []
    for fila in guardado['datos']['horario']:
        for dia in fila['dias']:
            faltan = [c for c in CAMPOS_DEL_CALENDARIO if dia.get(c) is None]
            if faltan:
                sin_calendario.append((fila['nombre'], dia['fecha'], faltan))
    assert not sin_calendario, sin_calendario[:3]


@pytest.mark.parametrize(('anio', 'mes'), MESES_BASE)
def test_el_calendario_no_se_transcribe_sino_que_se_calcula(sembrada, anio, mes):
    """Los datos del día tienen que coincidir con los del calendario de verdad."""
    guardado = horarios.oficial(anio, mes)
    esperado = {d['fecha']: d for d in calendario.dias_del_periodo(mes, anio)}
    for fila in guardado['datos']['horario']:
        for dia in fila['dias']:
            patron = esperado.get(dia['fecha'])
            assert patron, f'{dia["fecha"]} no pertenece al período de {anio}-{mes:02d}'
            for campo in ('dia', 'mes', 'dia_semana', 'es_festivo', 'mes_propio'):
                assert dia[campo] == patron[campo], (
                    f'{dia["fecha"]}: {campo} dice {dia[campo]} y toca {patron[campo]}')


def test_los_festivos_de_agosto_se_marcan(sembrada):
    """Dos hay en agosto de 2026, y tienen que verse distintos de un día normal."""
    guardado = horarios.oficial(2026, 8)
    festivos = {d['fecha'] for f in guardado['datos']['horario']
                for d in f['dias'] if d.get('es_festivo')}
    assert festivos == {'2026-08-07', '2026-08-17'}, sorted(festivos)


@pytest.mark.parametrize(('anio', 'mes'), MESES_BASE)
def test_las_horas_salen_calculadas_y_no_a_cero(sembrada, anio, mes):
    guardado = horarios.oficial(anio, mes)
    estadisticas = guardado['datos'].get('estadisticas') or []
    assert estadisticas, 'sin estadísticas la pantalla enseña todo a cero'
    assert len(estadisticas) == len(guardado['datos']['horario'])
    assert all(x.get('horas_periodo') for x in estadisticas), (
        'alguien aparece con cero horas en un mes que sí trabajó')


@pytest.mark.parametrize(('anio', 'mes'), MESES_BASE)
def test_la_pareja_viaja_con_la_fila(sembrada, anio, mes):
    """La revisión de publicación la necesita para mirar si coinciden de turno."""
    guardado = horarios.oficial(anio, mes)
    con_pareja = [f for f in guardado['datos']['horario'] if f.get('pareja_id')]
    assert con_pareja, 'ninguna fila trae pareja, y en la plantilla sí hay parejas'


@pytest.mark.parametrize(('anio', 'mes'), MESES_BASE)
def test_las_casillas_transcritas_se_reconocen_como_tales(sembrada, anio, mes):
    """Un día heredado no se le puede reprochar al mes que lo hereda.

    Se marca con su origen para poder decir «esto viene de un mes ya publicado»
    en vez de callarlo, que es lo que hacía la versión anterior.
    """
    guardado = horarios.oficial(anio, mes)
    for fila in guardado['datos']['horario']:
        for dia in fila['dias']:
            assert str(dia.get('origen') or '').startswith('base_'), dia
            assert dia.get('bloqueado') is True


def test_septiembre_llega_hasta_el_4_de_octubre(sembrada):
    """El período son semanas completas, y por eso se solapa con octubre."""
    guardado = horarios.oficial(2026, 9)
    fechas = sorted({d['fecha'] for f in guardado['datos']['horario'] for d in f['dias']})
    assert fechas[0] == '2026-08-31' and fechas[-1] == '2026-10-04'
    assert len(fechas) == 35, 'cinco semanas completas'


def test_sembrar_dos_veces_no_duplica_nada(sembrada):
    """Se llama en cada arranque: tiene que poder repetirse sin efectos."""
    from gestor.servicios import siembra
    antes = len(horarios.propuestas(2026, 9))
    siembra.sembrar()
    assert len(horarios.propuestas(2026, 9)) == antes
