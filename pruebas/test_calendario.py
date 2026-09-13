# -*- coding: utf-8 -*-
"""Semanas completas, períodos que se solapan y festivos.

El modelo de semanas completas es la idea de la que cuelga casi todo, y la que
más veces se ha entendido mal desde fuera del motor. Estas pruebas fijan los
casos concretos que ya se han equivocado alguna vez.
"""
from __future__ import annotations

from datetime import date

import pytest

from gestor.dominio import calendario, festivos

# ------------------------------------------------------ el período de un mes

def test_octubre_de_2026_va_del_28_de_septiembre_al_1_de_noviembre():
    """El ejemplo que hay que tener en la cabeza al leer cualquier otra cosa."""
    inicio, fin = calendario.rango(10, 2026)
    assert inicio == date(2026, 9, 28)
    assert fin == date(2026, 11, 1)
    assert inicio.weekday() == 0 and fin.weekday() == 6


def test_septiembre_de_2026_llega_hasta_el_4_de_octubre():
    inicio, fin = calendario.rango(9, 2026)
    assert inicio == date(2026, 8, 31)
    assert fin == date(2026, 10, 4)


def test_agosto_de_2026_es_la_excepcion_y_abarca_sus_dias_naturales():
    """Es la base histórica: se corresponde con el horario ya publicado."""
    inicio, fin = calendario.rango(8, 2026)
    assert inicio == date(2026, 8, 1)
    assert fin == date(2026, 8, 31)


def test_ningun_periodo_empieza_antes_del_primer_dia_de_operacion():
    inicio, _fin = calendario.rango(9, 2026)
    assert inicio >= calendario.PRIMER_DIA


@pytest.mark.parametrize('mes, anio', [(m, a) for a in (2026, 2027) for m in range(1, 13)
                                       if (a, m) >= (2026, 9)])
def test_todo_periodo_empieza_en_lunes_y_termina_en_domingo(mes, anio):
    inicio, fin = calendario.rango(mes, anio)
    assert inicio.weekday() == 0, f'{anio}-{mes:02d} no empieza en lunes'
    assert fin.weekday() == 6, f'{anio}-{mes:02d} no termina en domingo'
    assert (fin - inicio).days % 7 == 6, 'el período no son semanas enteras'


# -------------------------------------------------- los períodos se solapan

def test_un_dia_puede_pertenecer_a_dos_meses():
    """El atajo que ya costó caro.

    El 1 de octubre está en el período de septiembre y en el de octubre.
    Preguntarle a la fecha por su mes natural hacía que, al aprobar unas
    vacaciones de ese día, solo se avisara a octubre; septiembre se quedaba
    dando por bueno un horario que ya no coincidía con lo aprobado.
    """
    periodos = calendario.periodos_de_la_fecha(date(2026, 10, 1))
    assert (2026, 9) in periodos
    assert (2026, 10) in periodos


def test_un_dia_de_mitad_de_mes_pertenece_a_uno_solo():
    assert calendario.periodos_de_la_fecha(date(2026, 10, 15)) == [(2026, 10)]


def test_el_solape_entre_septiembre_y_octubre_es_del_28_al_4():
    solapados = [f for f in (date(2026, 9, d) for d in range(26, 31))
                 if len(calendario.periodos_de_la_fecha(f)) == 2]
    assert solapados == [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]


# ------------------------------------------------ el viernes administrativo

def test_el_ultimo_viernes_se_decide_sobre_el_mes_del_dia():
    """Y no sobre el mes que se está programando.

    En la primera y la última semana del período conviven días de dos meses, y
    ese día el área entera hace jornada administrativa: confundirse de mes deja
    a un área sin nadie en AM ni en PM en un día cualquiera.
    """
    assert calendario.es_ultimo_viernes(date(2026, 10, 30))
    assert not calendario.es_ultimo_viernes(date(2026, 10, 23))
    # El 25 de septiembre es el último viernes de septiembre, y cae dentro del
    # período de septiembre, no del de octubre.
    assert calendario.es_ultimo_viernes(date(2026, 9, 25))


def test_un_dia_que_no_es_viernes_nunca_lo_es():
    for dia in range(1, 32):
        f = date(2026, 10, dia)
        if f.weekday() != 4:
            assert not calendario.es_ultimo_viernes(f)


# ------------------------------------------------------------- las semanas

def test_las_semanas_del_periodo_lo_cubren_entero_y_sin_huecos():
    inicio, fin = calendario.rango(10, 2026)
    trozos = calendario.semanas(10, 2026)
    assert trozos[0][0] == inicio and trozos[-1][1] == fin
    for (_, fin_anterior), (inicio_siguiente, _) in zip(trozos, trozos[1:], strict=False):
        assert (inicio_siguiente - fin_anterior).days == 1, 'hay un hueco entre semanas'


def test_octubre_de_2026_tiene_cinco_semanas():
    assert len(calendario.semanas(10, 2026)) == 5


# --------------------------------------------------------------- los días

def test_cada_dia_trae_lo_que_el_motor_necesita_saber():
    dias = calendario.dias_del_periodo(10, 2026)
    assert len(dias) == 35
    primero = dias[0]
    for clave in ('fecha', 'dia_semana_numero', 'lunes_semana', 'es_domingo',
                  'es_festivo', 'es_ultimo_viernes_administrativo', 'mes_propio'):
        assert clave in primero, clave
    assert primero['fecha'] == '2026-09-28'
    assert primero['mes_propio'] is False, 'el 28 de septiembre no es de octubre'
    assert primero['pertenece'] == 'anterior'


def test_el_12_de_octubre_de_2026_es_festivo():
    """El día de la Raza, trasladado al lunes. Es el festivo del ejemplo real."""
    dias = {d['fecha']: d for d in calendario.dias_del_periodo(10, 2026)}
    assert dias['2026-10-12']['es_festivo'] is True
    assert dias['2026-10-12']['nombre_festivo']


# ------------------------------------------------------------- festivos

def test_la_ley_emiliani_traslada_al_lunes():
    # El 12 de octubre de 2026 cae en lunes; el de 2025 cae en domingo y se
    # traslada al 13.
    assert festivos.trasladar_al_lunes(date(2026, 10, 12)) == date(2026, 10, 12)
    assert festivos.trasladar_al_lunes(date(2025, 10, 12)) == date(2025, 10, 13)


def test_los_festivos_de_pascua_salen_donde_toca():
    calendario_2026 = festivos.del_anio(2026)
    pascua = festivos.domingo_de_pascua(2026)
    assert pascua == date(2026, 4, 5)
    assert calendario_2026[date(2026, 4, 2)] == 'Jueves Santo'
    assert calendario_2026[date(2026, 4, 3)] == 'Viernes Santo'


def test_un_anio_imposible_se_explica_en_vez_de_reventar():
    for malo in (0, 99999, 'ayer', None):
        with pytest.raises(ValueError):
            festivos.del_anio(malo)


def test_un_festivo_movido_a_mano_se_respeta():
    """Los ajustes se pasan como argumento: aquí no se abre ninguna base."""
    ajustado = festivos.con_ajustes(2026, [{
        'fecha_original': '2026-10-12',
        'fecha_nueva': '2026-10-13',
        'nombre': 'Día de la Raza (movido)',
    }])
    assert date(2026, 10, 12) not in ajustado
    assert ajustado[date(2026, 10, 13)] == 'Día de la Raza (movido)'


def test_calcular_festivos_no_necesita_base_de_datos():
    """Lo que hace que este cálculo se pueda probar con dos líneas.

    En la versión anterior abría la base para leer los ajustes, y un error de
    SQLite se tragaba con un `except` que devolvía el calendario sin ajustes en
    silencio: los festivos movidos por la oficina desaparecían sin avisar.
    """
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(festivos))
    importados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.update(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            importados.add(nodo.module or '')
    prohibidos = [m for m in importados
                  if m.startswith(('sqlite', 'gestor.datos'))]
    assert not prohibidos, f'el dominio no puede depender de la persistencia: {prohibidos}'
