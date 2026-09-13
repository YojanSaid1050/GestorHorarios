# -*- coding: utf-8 -*-
"""Modificar un horario ya armado sin rehacer el mes entero.

La idea que se comprueba aquí cabe en una frase: **lo que no se ha pedido
cambiar se congela**. Es lo que evita que mover el turno de una persona
reorganice los descansos de las otras diecisiete.

Y la segunda, igual de importante: un cambio que no cabe dentro de las reglas
**no se aplica en silencio**. Se dice qué pasó con él. Lo contrario —dejar que
alguien crea que su cambio quedó puesto— es peor que no dejarle cambiarlo.
"""
from __future__ import annotations

import pytest

from gestor.datos import ajustes, horarios
from gestor.servicios import edicion, generacion


@pytest.fixture
def octubre(base):
    """Octubre de 2026 generado y oficializado, que es de donde se parte."""
    from gestor.servicios import siembra
    siembra.sembrar()
    generado = generacion.generar(10, 2026)
    generacion.marcar_oficial(generado.propuestas[0]['horario_id'])
    return horarios.oficial(2026, 10)


def _celda_editable(guardado, area='gestion_social', turnos=('AM', 'PM')):
    """Una casilla de este mes, no heredada del anterior."""
    for fila in guardado['datos']['horario']:
        if area and fila.get('area') != area:
            continue
        for dia in fila.get('dias') or []:
            if (dia.get('mes_propio') and dia.get('turno') in turnos
                    and not dia.get('heredado')
                    and not str(dia.get('origen') or '').startswith('base_')):
                return fila, dia
    pytest.skip('el mes generado no tiene ninguna casilla editable de ese área')


def _turnos(resultado, empleado_id):
    fila = next(f for f in resultado['horario'] if f['empleado_id'] == empleado_id)
    return {d['fecha']: d['turno'] for d in fila['dias']}


# ------------------------------------------------------ el cambio de un día

def test_un_cambio_manual_que_cabe_se_aplica_y_se_guarda(octubre):
    fila, dia = _celda_editable(octubre)
    resultado = edicion.reprogramar(edicion.Peticion(
        mes=10, anio=2026, horario_id=octubre['id'], solo_este_dia=True,
        ajustes_manuales=[{'empleado_id': fila['empleado_id'],
                           'fecha': dia['fecha'], 'turno': 'D'}]))

    diagnostico = resultado['diagnostico_ajustes_manuales'][0]
    assert diagnostico['estado'] == 'aplicado'
    assert diagnostico['turno_anterior'] == dia['turno']
    assert _turnos(resultado['alternativas'][0], fila['empleado_id'])[dia['fecha']] == 'D'

    # Y sobrevive: si desapareciera al volver a generar, revisar celda por celda
    # sería trabajo perdido cada vez y nadie usaría el editor.
    guardados = ajustes.para_el_motor(10, 2026)
    assert any(a['empleado_id'] == fila['empleado_id'] and a['fecha'] == dia['fecha']
               for a in guardados)


def test_cambiar_un_día_no_mueve_el_resto_del_mes(octubre):
    """Lo que no se ha pedido cambiar se queda exactamente igual."""
    fila, dia = _celda_editable(octubre)
    antes = {(f['empleado_id'], d['fecha']): d['turno']
             for f in octubre['datos']['horario'] for d in f['dias']}

    resultado = edicion.reprogramar(edicion.Peticion(
        mes=10, anio=2026, horario_id=octubre['id'], solo_este_dia=True,
        ajustes_manuales=[{'empleado_id': fila['empleado_id'],
                           'fecha': dia['fecha'], 'turno': 'D'}]))

    despues = {(f['empleado_id'], d['fecha']): d['turno']
               for f in resultado['alternativas'][0]['horario'] for d in f['dias']}
    movidas = {k for k, v in despues.items() if antes.get(k) != v}
    fuera = {k for k in movidas if k[1] not in _semana_de(dia['fecha'])}
    assert not fuera, f'se movieron casillas fuera de la semana tocada: {sorted(fuera)[:5]}'


def _semana_de(fecha):
    from datetime import date, timedelta

    from gestor.dominio import calendario
    lunes = calendario.lunes_de(date.fromisoformat(fecha))
    return {(lunes + timedelta(days=i)).isoformat() for i in range(7)}


# ------------------------------------------------------------- por áreas

def test_reprogramar_un_área_no_toca_las_otras(octubre):
    """Es lo que evita que un permiso de una persona mueva a las otras dos áreas."""
    antes = {(f['empleado_id'], d['fecha']): d['turno']
             for f in octubre['datos']['horario'] for d in f['dias']}
    areas = {int(f['empleado_id']): f['area'] for f in octubre['datos']['horario']}

    resultado = edicion.reprogramar(edicion.Peticion(
        mes=10, anio=2026, horario_id=octubre['id'], areas=['comunicaciones']))

    despues = {(f['empleado_id'], d['fecha']): d['turno']
               for f in resultado['alternativas'][0]['horario'] for d in f['dias']}
    movidas = {k for k, v in despues.items() if antes.get(k) != v}
    intrusas = {k for k in movidas if areas.get(k[0]) != 'comunicaciones'}
    assert not intrusas, f'se movió gente de otras áreas: {sorted(intrusas)[:5]}'


def test_un_área_que_no_existe_se_dice_con_claridad(octubre):
    with pytest.raises(edicion.NoSePudoReprogramar, match='no es un área'):
        edicion.reprogramar(edicion.Peticion(
            mes=10, anio=2026, horario_id=octubre['id'], areas=['contabilidad']))


# ------------------------------------------------- lo que no se deja hacer

def test_no_se_toca_un_día_heredado_de_un_mes_publicado(octubre):
    heredado = None
    for fila in octubre['datos']['horario']:
        for dia in fila['dias']:
            if dia.get('heredado') or str(dia.get('origen') or '').startswith('base_'):
                heredado = (fila, dia)
                break
        if heredado:
            break
    if heredado is None:
        pytest.skip('octubre no heredó ningún día de septiembre')
    fila, dia = heredado
    with pytest.raises(edicion.NoSePudoReprogramar, match='ya publicado'):
        edicion.reprogramar(edicion.Peticion(
            mes=10, anio=2026, horario_id=octubre['id'], solo_este_dia=True,
            ajustes_manuales=[{'empleado_id': fila['empleado_id'],
                               'fecha': dia['fecha'], 'turno': 'D'}]))


def test_una_ausencia_no_se_pone_como_cambio_manual(octubre):
    """Unas vacaciones se registran como novedad, que es donde se aprueban."""
    fila, dia = _celda_editable(octubre)
    with pytest.raises(edicion.NoSePudoReprogramar, match='novedad'):
        edicion.reprogramar(edicion.Peticion(
            mes=10, anio=2026, horario_id=octubre['id'], solo_este_dia=True,
            ajustes_manuales=[{'empleado_id': fila['empleado_id'],
                               'fecha': dia['fecha'], 'turno': 'VAC'}]))


def test_forzar_sin_motivo_escrito_no_se_admite(octubre):
    """La justificación **es** el cambio: sin ella nadie puede auditarlo después."""
    fila, dia = _celda_editable(octubre)
    with pytest.raises(edicion.NoSePudoReprogramar, match='motivo'):
        edicion.reprogramar(edicion.Peticion(
            mes=10, anio=2026, horario_id=octubre['id'], solo_este_dia=True,
            permitir_excepciones_manuales=True, motivo_excepcion_manual='ya',
            ajustes_manuales=[{'empleado_id': fila['empleado_id'],
                               'fecha': dia['fecha'], 'turno': 'D'}]))


def test_una_semana_cerrada_no_se_recalcula_aunque_se_seleccione(octubre, base):
    """Cerrar una semana tiene que protegerla, no confiar en que nadie la marque."""
    from gestor.dominio import calendario
    semanas = calendario.semanas(10, 2026)
    lunes = semanas[1][0].isoformat()
    with base.transaccion() as conexion:
        for inicio, _ in semanas:
            conexion.execute('INSERT INTO semanas(anio, mes, lunes, cerrada) '
                             'VALUES(2026, 10, ?, 1)', (inicio.isoformat(),))

    with pytest.raises(edicion.NoSePudoReprogramar, match='cerrada'):
        edicion.reprogramar(edicion.Peticion(
            mes=10, anio=2026, horario_id=octubre['id'],
            semana_inicio=lunes, semana_fin=lunes))


def test_sin_horario_del_que_partir_se_explica(base):
    from gestor.servicios import siembra
    siembra.sembrar()
    with pytest.raises(edicion.NoSePudoReprogramar, match='mes completo'):
        edicion.reprogramar(edicion.Peticion(mes=12, anio=2026))


# --------------------------------------------------------- volver a empezar

def test_retirar_un_cambio_manual_lo_deja_de_aplicar(octubre):
    fila, dia = _celda_editable(octubre)
    edicion.reprogramar(edicion.Peticion(
        mes=10, anio=2026, horario_id=octubre['id'], solo_este_dia=True,
        ajustes_manuales=[{'empleado_id': fila['empleado_id'],
                           'fecha': dia['fecha'], 'turno': 'D'}]))
    assert ajustes.retirar(fila['empleado_id'], dia['fecha']) is True
    assert ajustes.para_el_motor(10, 2026) == []
    # No se borra: se conserva desactivado para poder responder «aquí hubo un
    # cambio manual y se retiró».
    assert any(not a['activo'] for a in ajustes.listar(incluir_retirados=True))


def test_retirar_algo_que_no_existe_devuelve_falso(octubre):
    assert ajustes.retirar(999, '2026-10-06') is False


def test_un_cambio_forzado_guarda_qué_regla_se_saltó(base):
    """Sin eso, tres meses después nadie puede explicar por qué ese día está así."""
    from gestor.servicios import siembra
    siembra.sembrar()
    ajustes.guardar(1, '2026-10-06', 'D', forzado=True,
                    justificacion='Lo pidió la coordinación por una actividad',
                    reglas=['COBERTURA_AREA'])
    guardado = ajustes.listar()[0]
    assert guardado['reglas'] == ['COBERTURA_AREA']
    assert guardado['justificacion'].startswith('Lo pidió')


def test_no_se_guarda_un_cambio_forzado_sin_motivo(base):
    from gestor.servicios import siembra
    siembra.sembrar()
    with pytest.raises(ValueError, match='motivo escrito'):
        ajustes.guardar(1, '2026-10-06', 'D', forzado=True, justificacion='')
