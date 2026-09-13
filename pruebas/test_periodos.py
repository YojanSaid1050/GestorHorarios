# -*- coding: utf-8 -*-
"""Los meses que se quedan viejos, y el aviso que lo dice.

La aplicación **no regenera nada por su cuenta**. Un mes que la oficina ya
imprimió no puede cambiar solo porque alguien apruebe unas vacaciones: la gente
tendría un papel en la pared distinto de lo que dice la pantalla. Lo que sí
tiene que pasar es que quede constancia, con el motivo escrito, para que una
persona decida cuándo volver a armarlo.

Estas pruebas vigilan las dos mitades de esa idea: que el aviso aparezca cuando
tiene que aparecer, y que el horario guardado siga exactamente igual.
"""
from __future__ import annotations

import json

import pytest

from gestor.servicios import periodos


def _mensajes(razones) -> list[str]:
    return [r['mensaje'] for r in razones]


@pytest.fixture
def con_personal(base):
    from gestor.servicios import siembra
    siembra.sembrar()
    from gestor.datos import personal
    return {p['nombre']: p['id'] for p in personal.listar()}


def _fingir_horario(anio: int, mes: int, oficial: bool = True) -> int:
    """Un mes «ya generado», sin pagar el precio de generarlo de verdad.

    Lo que se está probando aquí es la marca, no el reparto. Generar seis meses
    reales para comprobar un aviso convertiría una batería de segundos en una de
    minutos y nadie la ejecutaría.
    """
    from gestor.datos.base import transaccion
    with transaccion() as conexion:
        cursor = conexion.execute(
            'INSERT INTO horarios(anio, mes, datos_json, valido, grupo_id, oficial) '
            'VALUES(?,?,?,1,?,?)',
            (anio, mes, json.dumps({'horario': []}), f'{anio}-{mes:02d}-prueba',
             1 if oficial else 0))
        return int(cursor.lastrowid)


# --------------------------------------------------------------- lo básico

def test_un_mes_que_nunca_se_generó_no_se_marca(base):
    """Avisar de que noviembre quedó viejo cuando noviembre no existe es ruido.

    Y el ruido tiene un coste concreto: enseña a no leer los avisos. Si la
    pantalla dice que hay meses desactualizados desde el primer día, cuando de
    verdad haya uno nadie va a mirar.
    """
    assert periodos.marcar(['2026-10-15'], 'algo cambió') == []
    assert periodos.desactualizados() == []


def test_se_marca_el_mes_generado_con_su_motivo(base):
    _fingir_horario(2026, 10)
    marcados = periodos.marcar(['2026-10-15'], 'se aprobó una novedad')

    assert marcados == ['octubre de 2026']
    estado = periodos.estado(10, 2026)
    assert estado['desactualizado'] is True
    assert _mensajes(estado['razones']) == ['se aprobó una novedad']
    assert estado['razones'][0]['origen'] == 'cambios', (
        'la pantalla no dice lo mismo según de dónde venga el cambio')


def test_una_fecha_solapada_marca_los_dos_meses(base):
    """El 1 de noviembre pertenece al período de octubre y al de noviembre.

    Es el mismo atajo que ya costó caro en las novedades: preguntarle a una
    fecha por su mes natural dejaba a un mes dando por bueno un horario que ya
    no coincidía con lo aprobado.
    """
    _fingir_horario(2026, 10)
    _fingir_horario(2026, 11)

    marcados = periodos.marcar(['2026-11-01'], 'se aprobó un permiso')

    assert marcados == ['octubre de 2026', 'noviembre de 2026']
    assert periodos.estado(10, 2026)['desactualizado'] is True
    assert periodos.estado(11, 2026)['desactualizado'] is True


def test_los_meses_base_no_se_marcan_nunca(base):
    """Aconsejar rehacer agosto es un consejo que no se puede seguir.

    Agosto y septiembre de 2026 llegan transcritos del Excel que la oficina ya
    trabajó: la aplicación se niega a reiniciarlos y no hay forma de generarlos.
    Un aviso que no se puede atender enseña a no leer los avisos.
    """
    _fingir_horario(2026, 9)
    _fingir_horario(2026, 10)

    marcados = periodos.marcar(['2026-10-01'], 'se aprobó un permiso')

    assert marcados == ['octubre de 2026']
    assert periodos.estado(9, 2026)['desactualizado'] is False
    assert [m['mes'] for m in periodos.desactualizados()] == [10]


def test_los_motivos_se_acumulan_sin_repetirse(base):
    _fingir_horario(2026, 10)
    periodos.marcar(['2026-10-05'], 'se aprobó una novedad')
    periodos.marcar(['2026-10-12'], 'se aprobó una novedad')
    periodos.marcar(['2026-10-19'], 'se retiró a alguien')

    razones = _mensajes(periodos.estado(10, 2026)['razones'])
    assert razones == ['se aprobó una novedad', 'se retiró a alguien'], (
        'tres aprobaciones seguidas tienen que decirse una vez, no tres')


def test_una_fecha_ilegible_no_rompe_nada(base):
    _fingir_horario(2026, 10)
    assert periodos.marcar([None, '', 'mañana', '2026-10-05'], 'cambió algo') == [
        'octubre de 2026']


# ------------------------------------------------------- cambios sin final

def test_marcar_desde_alcanza_todo_lo_que_viene_después(base):
    """Una regla nueva no afecta a unas fechas: afecta a un antes y un después."""
    for mes in (9, 10, 11, 12):
        _fingir_horario(2026, mes)

    marcados = periodos.marcar_desde('2026-11-01', 'cambió la cobertura pedida')

    assert marcados == ['octubre de 2026', 'noviembre de 2026', 'diciembre de 2026'], (
        'octubre entra porque su período llega hasta el 1 de noviembre')
    assert periodos.estado(9, 2026)['desactualizado'] is False


def test_marcar_desde_no_toca_los_meses_ya_cerrados(base):
    _fingir_horario(2026, 9)
    _fingir_horario(2026, 10)
    periodos.marcar_desde('2026-12-01', 'cambió una regla')
    assert periodos.desactualizados() == []


# ------------------------------------------------------------------ el área

def test_el_origen_del_cambio_se_guarda_con_el_motivo(base):
    """«Hay novedades por aplicar» y «depende de otro mes» son dos avisos.

    Con dos acciones distintas, además: uno se resuelve aplicando las novedades
    de ese mes y el otro volviendo a generarlo entero desde el anterior.
    """
    _fingir_horario(2026, 10)
    periodos.marcar(['2026-10-15'], 'se aprobó una novedad', origen='novedades')
    periodos.marcar(['2026-10-16'], 'cambió el mes anterior', origen='continuidad')

    origenes = {r['origen'] for r in periodos.estado(10, 2026)['razones']}
    assert origenes == {'novedades', 'continuidad'}


def test_se_admiten_los_motivos_escritos_por_la_versión_anterior(base):
    """Un formato nuevo no puede hacer ilegible lo que ya estaba escrito."""
    import json
    _fingir_horario(2026, 10)
    with base.transaccion() as conexion:
        conexion.execute(
            'INSERT INTO periodos(anio, mes, sucio, razones_json) VALUES(?,?,1,?)',
            (2026, 10, json.dumps(['un motivo a la antigua'])))
    assert _mensajes(periodos.estado(10, 2026)['razones']) == ['un motivo a la antigua']


def test_el_área_se_marca_aparte(base):
    """Una novedad de Comunicaciones no obliga a recalcular Gestión Social."""
    _fingir_horario(2026, 10)
    periodos.marcar(['2026-10-15'], 'se aprobó una novedad', area='comunicaciones')

    estado = periodos.estado(10, 2026)
    assert list(estado['areas']) == ['comunicaciones']


def test_generar_solo_un_área_deja_el_mes_marcado_si_queda_otra(base):
    """El mes no está al día hasta que lo están todas sus áreas."""
    _fingir_horario(2026, 10)
    periodos.marcar(['2026-10-15'], 'novedad de una', area='comunicaciones')
    periodos.marcar(['2026-10-15'], 'novedad de otra', area='gestion_social')

    periodos.limpiar(10, 2026, area='comunicaciones')

    estado = periodos.estado(10, 2026)
    assert estado['desactualizado'] is True
    assert list(estado['areas']) == ['gestion_social']

    periodos.limpiar(10, 2026, area='gestion_social')
    assert periodos.estado(10, 2026)['desactualizado'] is False


# ----------------------------------------------------------------- limpiar

def test_volver_a_generar_deja_el_mes_al_día(base):
    _fingir_horario(2026, 10)
    periodos.marcar(['2026-10-15'], 'se aprobó una novedad', area='comunicaciones')
    periodos.limpiar(10, 2026)

    estado = periodos.estado(10, 2026)
    assert estado == {'desactualizado': False, 'razones': [], 'areas': {}}
    assert periodos.desactualizados() == []


def test_reiniciar_borra_también_las_marcas(base):
    """Reiniciar tiene que llevarse el estado del período, no solo el horario.

    Es exactamente el fallo que dio la versión anterior: se borraban los
    horarios y sobrevivía todo lo demás, así que al volver a generar salía el
    mismo mes y desde fuera el botón parecía no hacer nada.
    """
    from gestor.servicios import reinicios
    _fingir_horario(2026, 10)
    periodos.marcar(['2026-10-15'], 'se aprobó una novedad')

    reinicios.reiniciar_programacion(10, 2026)

    assert periodos.desactualizados() == []


# ------------------------------------------------------------- la redacción

def test_la_frase_se_lee_como_la_diría_una_persona():
    assert periodos.frase([]) == ''
    assert periodos.frase(['octubre de 2026']).strip() == (
        'Conviene volver a generar octubre de 2026: se armó antes de este cambio.')
    assert periodos.frase(['octubre de 2026', 'noviembre de 2026']).strip() == (
        'Conviene volver a generar octubre de 2026 y noviembre de 2026: '
        'se armaron antes de este cambio.')
    assert periodos.frase(['a', 'b', 'c']).strip().startswith(
        'Conviene volver a generar a, b y c:')


def test_si_marcar_falla_la_acción_sigue_valiendo(base, monkeypatch):
    """El aviso es un extra. Nunca puede tumbar la aprobación que lo provoca.

    Si un día la tabla de períodos da un error, lo que no puede pasar es que
    aprobar unas vacaciones devuelva un fallo y el usuario crea que no se
    aprobaron.
    """
    def revienta(*_args, **_kwargs):
        raise RuntimeError('la base dice que no')

    monkeypatch.setattr(periodos, 'marcar', revienta)
    assert periodos.avisar(['2026-10-15'], 'algo') == ''
    monkeypatch.setattr(periodos, 'marcar_desde', revienta)
    assert periodos.avisar_desde('2026-10-15', 'algo') == ''
