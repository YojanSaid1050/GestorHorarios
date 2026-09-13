# -*- coding: utf-8 -*-
"""Quién cubre turno y quién no. La pregunta que más veces se contestó mal.

Cada prueba de aquí corresponde a un fallo que llegó a la oficina antes de que
alguien lo viera en una pantalla. No están para subir un número: están para que
esos cuatro casos no vuelvan.
"""
from __future__ import annotations

import pytest

from gestor.dominio import cobertura, codigos
from gestor.dominio.cobertura import (
    ReglaCobertura,
    cabe_el_cambio,
    conteo,
    exigido,
    franja_cubierta,
    incumplimientos,
)

LUNES = '2026-10-05'


def _casilla(fecha, turno, **extra):
    dia = {
        'fecha': fecha,
        'turno': turno,
        'dia_semana_numero': 0,
        'vigente': True,
        'origen': 'descanso_automatico' if turno == 'D' else 'turno_base',
    }
    dia.update(extra)
    return dia


def _persona(eid, nombre, area, turnos, **extra):
    dias = [_casilla(f'2026-10-{5 + i:02d}', t, dia_semana_numero=i % 7)
            for i, t in enumerate(turnos)]
    persona = {'empleado_id': eid, 'nombre': nombre, 'area': area, 'dias': dias}
    persona.update(extra)
    return persona


REGLA_AC = ReglaCobertura(area='atencion_ciudadano', vigente_desde='2026-08-01',
                          minimo_area=1, am_maximo=3, pm_maximo=1)
REGLA_GS = ReglaCobertura(area='gestion_social', vigente_desde='2026-08-01',
                          am_minimo=1, pm_minimo=1)


# ------------------------------------------------ qué cubre cada código

def test_los_turnos_operativos_se_cubren_a_si_mismos():
    persona = {'nombre': 'X'}
    assert franja_cubierta(persona, _casilla(LUNES, 'AM')) == 'AM'
    assert franja_cubierta(persona, _casilla(LUNES, 'PM')) == 'PM'


def test_el_descanso_y_las_ausencias_no_cubren_nada():
    persona = {'nombre': 'X'}
    for turno in ('D', 'VAC', 'INC', 'PER', 'NV'):
        assert franja_cubierta(persona, _casilla(LUNES, turno)) is None, turno


def test_el_administrativo_general_conserva_la_franja_que_tenia():
    """ADM-GS cambia lo que hace la persona, no el hueco que deja en el cuadro."""
    persona = {'nombre': 'X'}
    assert franja_cubierta(persona, _casilla(LUNES, 'ADM-GS', turno_original='PM')) == 'PM'
    assert franja_cubierta(persona, _casilla(LUNES, 'ADM-GS', turno_original='AM')) == 'AM'


def test_el_administrativo_general_cede_ante_la_decision_tomada_a_mano():
    """Si en Asignaciones se dijo que libera la tarde, libera la tarde."""
    persona = {'nombre': 'X'}
    casilla = _casilla(LUNES, 'ADM-GS', turno_original='PM', cobertura_operativa='AM')
    assert franja_cubierta(persona, casilla) == 'AM'


def test_el_administrativo_de_atencion_al_ciudadano_no_cubre_ningun_turno():
    """El fallo que se vio tres veces en la oficina.

    ADM-AC es un horario propio y permanente: esa persona trabaja, pero no
    releva a nadie en la mañana ni en la tarde. Contarlo como cobertura hacía
    que un día con toda el área descansando salvo la administrativa pasara por
    bueno.
    """
    persona = {'nombre': 'Persona Cualquiera'}
    assert franja_cubierta(persona, _casilla(LUNES, 'ADM-AC')) is None
    assert franja_cubierta(persona, _casilla(LUNES, 'ADM-AC', turno_original='AM')) is None


def test_trabajar_y_cubrir_no_son_lo_mismo():
    """La distinción que se perdía al tener una sola lista de códigos.

    Quien hace ADM-AC está trabajando —le cuenta la racha, no necesita descanso
    ese día, suma horas— y a la vez no cubre ningún turno. Un módulo que use
    «trabaja» para decidir la cobertura se equivoca exactamente aquí.
    """
    assert 'ADM-AC' in codigos.TRABAJADOS
    assert 'ADM-AC' not in codigos.CUBREN
    assert codigos.trabaja('ADM-AC') is True
    assert codigos.franja_que_cubre('ADM-AC', 'AM') is None


# ------------------------------------- los días de cobertura de cada persona

def test_quien_solo_cubre_ciertos_dias_no_cuenta_los_demas():
    """Quien solo cubre algunos días: martes, miércoles, sábados y domingos."""
    sergio = {'nombre': 'Quien Cubre A Ratos', 'cobertura_dias': [1, 2, 5, 6]}
    martes = _casilla('2026-10-06', 'PM', dia_semana_numero=1)
    jueves = _casilla('2026-10-08', 'PM', dia_semana_numero=3)
    assert franja_cubierta(sergio, martes) == 'PM'
    assert franja_cubierta(sergio, jueves) is None


def test_sin_lista_de_dias_se_cubren_todos():
    """`None` es «todos los días», y es lo normal. La lista vacía es «ninguno»."""
    assert franja_cubierta({'nombre': 'X'}, _casilla(LUNES, 'AM')) == 'AM'
    assert franja_cubierta({'nombre': 'X', 'cobertura_dias': []},
                           _casilla(LUNES, 'AM')) is None


def test_los_dias_de_cobertura_valen_igual_para_el_turno_y_para_el_area():
    """Se cablearon en un conteo y se olvidaron en el otro.

    Al haber un único `franja_cubierta`, los dos conteos leen lo mismo por
    construcción: ya no hay dos sitios que puedan discrepar.
    """
    sergio = _persona(1, 'Quien Cubre A Ratos', 'gestion_social', ['PM'], cobertura_dias=[1])
    otra = _persona(2, 'Ana', 'gestion_social', ['AM'])
    horario = [sergio, otra]
    cuenta = conteo(horario, 'gestion_social', LUNES)   # el lunes no cubre
    assert cuenta.pm == 0 and cuenta.am == 1
    assert cuenta.cubriendo == 1
    assert cuenta.vigentes == 2


# --------------------------------------------------- el día que hay que ver

def test_un_area_con_solo_la_administrativa_es_un_dia_sin_cobertura():
    """El viernes 2 de octubre, tal como aparece en el horario de la oficina.

    Tres de las cuatro personas de Atención al Ciudadano descansan y la cuarta
    hace ADM-AC. El área tiene a alguien trabajando y aun así no tiene a nadie
    cubriendo: eso es lo que hay que denunciar.
    """
    horario = [
        _persona(1, 'Persona Primera', 'atencion_ciudadano', ['D']),
        _persona(2, 'Persona Segunda', 'atencion_ciudadano', ['D']),
        _persona(3, 'Persona Tercera', 'atencion_ciudadano', ['D']),
        _persona(4, 'Persona Cuarta', 'atencion_ciudadano', ['ADM-AC']),
    ]
    cuenta = conteo(horario, 'atencion_ciudadano', LUNES)
    assert cuenta.cubriendo == 0, 'ADM-AC no puede contar como cobertura'
    assert cuenta.vigentes == 4

    fallos = incumplimientos(horario, 'atencion_ciudadano', LUNES, REGLA_AC)
    assert fallos, 'un área sin nadie cubriendo tiene que salir en rojo'
    assert fallos[0].norma == 'cobertura del área'


def test_un_dia_heredado_se_informa_igual_pero_marcado_como_heredado():
    """Callarlo fue el error de la versión anterior.

    Los días que vienen de un mes ya publicado no se pueden cambiar desde el mes
    nuevo, y por eso quedaban exentos de toda comprobación. El resultado es que
    un hueco real —el viernes 2— no aparecía en ninguna pantalla. Ahora se
    informa, marcado como heredado: no se le reprocha al mes que se está
    creando, pero se ve.
    """
    horario = [
        _persona(1, 'Persona Primera', 'atencion_ciudadano', ['D']),
        _persona(2, 'Persona Segunda', 'atencion_ciudadano', ['D']),
        _persona(3, 'Persona Tercera', 'atencion_ciudadano', ['D']),
        _persona(4, 'Persona Cuarta', 'atencion_ciudadano', ['ADM-AC']),
    ]
    for persona in horario:
        for dia in persona['dias']:
            dia['origen'] = 'base_septiembre_2026'
            dia['bloqueado'] = True

    fallos = incumplimientos(horario, 'atencion_ciudadano', LUNES, REGLA_AC)
    assert fallos, 'un día heredado con un hueco real tiene que verse'
    assert all(f.heredado for f in fallos), 'y tiene que constar que viene de antes'


def test_el_ultimo_viernes_administrativo_no_es_un_incumplimiento():
    """Ese día el área entera hace jornada ADM y nadie está en AM ni en PM."""
    horario = [
        _persona(i, f'Persona {i}', 'atencion_ciudadano', ['ADM-GS'])
        for i in range(1, 5)
    ]
    for persona in horario:
        persona['dias'][0]['es_ultimo_viernes_administrativo'] = True
    assert incumplimientos(horario, 'atencion_ciudadano', LUNES, REGLA_AC) == []


# ------------------------------------------------------------ la válvula

def test_un_minimo_nunca_puede_exigir_a_toda_el_area():
    """Alguien tiene que poder descansar.

    Sin esta válvula, un área de tres personas con un mínimo de tres hace
    imposible cualquier horario y el mes no se puede generar.
    """
    assert exigido(3, 3) == 2
    assert exigido(1, 1) == 0
    assert exigido(1, 4) == 1
    assert exigido(0, 4) == 0


def test_quien_no_esta_vigente_no_cuenta_para_nada():
    """Ni suma al mínimo ni hace que se le exija más al área."""
    horario = [
        _persona(1, 'Ana', 'gestion_social', ['AM']),
        _persona(2, 'Se fue', 'gestion_social', ['NV']),
    ]
    cuenta = conteo(horario, 'gestion_social', LUNES)
    assert cuenta.vigentes == 1
    assert cuenta.am == 1


# ------------------------------------------------------- mover a alguien

def test_no_se_mueve_a_alguien_si_deja_su_turno_sin_nadie():
    horario = [
        _persona(1, 'Ana', 'gestion_social', ['AM']),
        _persona(2, 'Beto', 'gestion_social', ['PM']),
        _persona(3, 'Cris', 'gestion_social', ['AM']),
    ]
    beto = horario[1]
    assert not cabe_el_cambio(horario, beto, beto['dias'][0], 'AM', REGLA_GS), (
        'mover al único de la tarde deja la tarde vacía'
    )


def test_si_queda_alguien_cubriendo_el_cambio_cabe():
    horario = [
        _persona(1, 'Ana', 'gestion_social', ['AM']),
        _persona(2, 'Beto', 'gestion_social', ['PM']),
        _persona(3, 'Cris', 'gestion_social', ['PM']),
    ]
    beto = horario[1]
    assert cabe_el_cambio(horario, beto, beto['dias'][0], 'AM', REGLA_GS)


def test_el_techo_lo_salta_una_decision_tomada_a_mano_y_el_suelo_no():
    """Las dos naturalezas de la regla, que no se pueden tratar igual."""
    regla = ReglaCobertura(area='comunicaciones', vigente_desde='2026-08-01',
                           minimo_area=1, am_maximo=2, pm_maximo=1)
    horario = [
        _persona(1, 'Ana', 'comunicaciones', ['AM']),
        _persona(2, 'Beto', 'comunicaciones', ['AM']),
        _persona(3, 'Cris', 'comunicaciones', ['PM']),
    ]
    cris = horario[2]
    assert not cabe_el_cambio(horario, cris, cris['dias'][0], 'AM', regla), (
        'con el techo puesto, un tercero en la mañana no cabe')
    assert cabe_el_cambio(horario, cris, cris['dias'][0], 'AM', regla,
                          respetar_techo=False), (
        'una asignación decidida a mano sí puede pasar por encima del techo')


@pytest.mark.parametrize('area', ['gestion_social', 'atencion_ciudadano', 'comunicaciones'])
def test_cada_area_tiene_nombre_en_castellano(area):
    from gestor.dominio.cobertura import NOMBRES_AREA
    assert NOMBRES_AREA[area] and NOMBRES_AREA[area] != area


# ------------------------------- el viernes administrativo que no lo es

def _dia_de_viernes(turno, **extra):
    """Una casilla del último viernes del mes."""
    return {'fecha': '2026-12-25', 'turno': turno, 'mes_propio': True,
            'es_ultimo_viernes_administrativo': True, 'vigente': True, **extra}


def _area(turnos, area='atencion_ciudadano'):
    return [{'empleado_id': i, 'nombre': f'Persona {i}', 'area': area,
             'tipo_turno': 'rotativo', 'dias': [_dia_de_viernes(t)]}
            for i, t in enumerate(turnos, start=1)]


def test_el_ultimo_viernes_con_todos_en_adm_sigue_exento():
    """La exención de siempre: ese día el área entera hace jornada ADM.

    Nadie está en AM ni en PM, y es a propósito, así que reprocharle al día que
    no haya cobertura sería reprocharle que la regla se cumpla.
    """
    horario = _area(['ADM-AC', 'ADM-AC', 'ADM-AC'])
    cuenta = cobertura.conteo(horario, 'atencion_ciudadano', '2026-12-25')
    assert cuenta.viernes_administrativo is True

    regla = cobertura.ReglaCobertura(area='atencion_ciudadano',
                                     vigente_desde='2026-08-01', minimo_area=1)
    assert cobertura.incumplimientos(horario, 'atencion_ciudadano',
                                     '2026-12-25', regla) == []


def test_navidad_en_el_ultimo_viernes_sigue_comprobando_la_cobertura():
    """El agujero que encontró la revisión norma por norma.

    Navidad y Viernes Santo caen en el último viernes de su mes, así que el
    calendario los marca como el viernes administrativo. Pero se programan como
    festivos: nadie hace jornada administrativa y todo el mundo trabaja en AM o
    en PM. Con la marca bastando por sí sola, esos dos días quedaban **exentos
    de comprobar cobertura**: un área podía quedarse sin nadie y no salía en
    ninguna pantalla. Es el mismo silencio que dejó el viernes 2 de octubre.

    La exención pide ahora las dos cosas: que el calendario lo diga **y** que
    de verdad haya jornada administrativa.
    """
    horario = _area(['D', 'D', 'D'])
    cuenta = cobertura.conteo(horario, 'atencion_ciudadano', '2026-12-25')
    assert cuenta.viernes_administrativo is False, (
        'nadie está en ADM: no es una jornada administrativa'
    )

    regla = cobertura.ReglaCobertura(area='atencion_ciudadano',
                                     vigente_desde='2026-08-01', minimo_area=1)
    fallos = cobertura.incumplimientos(horario, 'atencion_ciudadano',
                                       '2026-12-25', regla)
    assert fallos, 'el área se quedó sin nadie y no se dijo'
    assert 'cubriendo turno' in fallos[0].mensaje


def test_un_viernes_a_medias_tampoco_se_exime_entero():
    """Con parte del área en ADM y parte trabajando, el día se mide igual."""
    horario = _area(['ADM-AC', 'D', 'D'])
    cuenta = cobertura.conteo(horario, 'atencion_ciudadano', '2026-12-25')
    assert cuenta.viernes_administrativo is True, (
        'sí hay jornada administrativa: la marca es correcta'
    )
    # Y ADM-AC sigue sin cubrir turno, que es la otra mitad de la norma.
    assert cuenta.cubriendo == 0
