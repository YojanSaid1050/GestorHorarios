# -*- coding: utf-8 -*-
"""Lo que una decisión ya tomada tiene que aguantar.

Tres caminos distintos llevaban al mismo sitio: algo que alguien decidió —un
turno puesto a mano, una semana cerrada, una incapacidad aprobada— desaparecía
sin una palabra porque otro camino del programa no sabía que existía.

* Volver a generar el mes entero no leía los cambios a mano guardados.
* Volver a generar el mes entero tampoco leía las semanas cerradas.
* Un cambio a mano con la casilla de forzar marcada pasaba por encima de una
  incapacidad aprobada, y encima borraba el vínculo con la novedad: el horario
  decía AM y la solicitud seguía aprobada.

Las tres se ven igual desde la oficina: se mira el cuadro y lo que había no
está. Por eso van juntas.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from gestor.datos import horarios, novedades
from gestor.datos.base import transaccion
from gestor.dominio import calendario
from gestor.servicios import cierres, edicion, generacion

pytestmark = pytest.mark.lenta


@pytest.fixture
def octubre(base):
    """Octubre de 2026 generado y con una propuesta ya oficial."""
    from gestor.servicios import reglas_cobertura, reglas_operacion, siembra
    reglas_cobertura.olvidar_lo_leido()
    reglas_operacion.invalidar_cache()
    siembra.sembrar()
    generacion.marcar_oficial(generacion.generar(10, 2026).propuestas[0]['horario_id'])
    return horarios.oficial(2026, 10)


def _dia_editable(oficial, cual=5):
    """Un día de octubre que no venga heredado del mes anterior."""
    fila = oficial['horario'][0]
    libres = [d for d in fila['dias']
              if not d.get('heredado')
              and not str(d.get('origen') or '').startswith('base_')]
    return int(fila['empleado_id']), libres[cual]


def _turno_en(resultado, empleado_id, fecha):
    for fila in resultado['horario']:
        if int(fila['empleado_id']) != int(empleado_id):
            continue
        for dia in fila['dias']:
            if str(dia['fecha']) == fecha:
                return dia
    return None


def _cerrar(lunes, anio=2026, mes=10):
    with transaccion() as conexion:
        conexion.execute(
            'INSERT OR REPLACE INTO semanas(anio, mes, lunes, cerrada) '
            'VALUES(?,?,?,1)', (int(anio), int(mes), str(lunes)))


def _lunes_de(fecha: str) -> str:
    dia = date.fromisoformat(str(fecha)[:10])
    return (dia - timedelta(days=dia.weekday())).isoformat()


# ------------------------------------- un cambio a mano sobrevive a regenerar

def test_regenerar_el_mes_conserva_los_cambios_guardados_a_mano(octubre):
    """Se ponía el turno a mano, se volvía a generar, y estaba como antes.

    Y sin decir nada: el ajuste seguía guardado —la pantalla lo enseñaba— pero
    el horario no lo tenía. Dos respuestas distintas a la misma pregunta, y la
    que la oficina imprime era la equivocada.
    """
    empleado, dia = _dia_editable(octubre)
    nuevo = 'PM' if dia['turno'] != 'PM' else 'AM'
    edicion.reprogramar(edicion.Peticion(
        mes=10, anio=2026, solo_este_dia=True,
        ajustes_manuales=[{'empleado_id': empleado, 'fecha': dia['fecha'],
                           'turno': nuevo}],
        permitir_excepciones_manuales=True,
        motivo_excepcion_manual='cubre una reunión de área'))

    rehecho = generacion.generar(10, 2026).propuestas[0]
    assert _turno_en(rehecho, empleado, dia['fecha'])['turno'] == nuevo


# ------------------------------------------- una semana cerrada está cerrada

def test_regenerar_el_mes_no_toca_una_semana_cerrada(octubre):
    """Con algo que, si no estuviera cerrada, la cambiaría seguro.

    Comprobar que la semana sale igual tras regenerar sin más no demuestra
    nada: saliendo del mismo sitio, el reparto vuelve a dar lo mismo aunque
    nadie la esté protegiendo. Hace falta aprobar dentro de ella unas
    vacaciones —que es exactamente el camino por el que apareció el fallo— y
    ver que aun así no entra.
    """
    empleado, dia = _dia_editable(octubre)
    semana = cierres.fechas_de(_lunes_de(dia['fecha']))
    _cerrar(_lunes_de(dia['fecha']))

    solicitud = novedades.crear_solicitud({
        'empleado_id': empleado, 'tipo': 'vacaciones',
        'fecha_inicio': min(semana), 'fecha_fin': max(semana),
        'observacion': 'aprobadas después de cerrar la semana'})
    novedades.resolver_solicitud(int(solicitud), 'aprobada')

    rehecho = generacion.generar(10, 2026).propuestas[0]
    for fila in octubre['horario']:
        for antes in fila['dias']:
            if str(antes['fecha'])[:10] not in semana:
                continue
            despues = _turno_en(rehecho, int(fila['empleado_id']), antes['fecha'])
            assert despues['turno'] == antes['turno'], (
                f"la semana cerrada cambió: {fila['nombre']} el {antes['fecha']} "
                f"pasó de {antes['turno']} a {despues['turno']}")


def test_un_manual_forzado_no_entra_en_una_semana_cerrada(octubre):
    """Era la puerta de atrás: los manuales se aplican **después** de lo congelado.

    Con un rango que abarcaba varias semanas, una de ellas cerrada, el cambio
    caía dentro de la cerrada y salía aplicado igual, porque nadie comprobaba
    que la fecha pedida estuviera dentro de lo editable.
    """
    empleado, dia = _dia_editable(octubre)
    _cerrar(_lunes_de(dia['fecha']))
    lunes = [inicio.isoformat() for inicio, _ in calendario.semanas(10, 2026)]
    otro = 'AM' if dia['turno'] != 'AM' else 'PM'

    with pytest.raises(edicion.NoSePudoReprogramar) as fallo:
        edicion.reprogramar(edicion.Peticion(
            mes=10, anio=2026, semana_inicio=lunes[0], semana_fin=lunes[-1],
            ajustes_manuales=[{'empleado_id': empleado, 'fecha': dia['fecha'],
                               'turno': otro}],
            permitir_excepciones_manuales=True,
            motivo_excepcion_manual='hace falta ese día'))
    assert 'cerrada' in str(fallo.value)


def test_una_semana_compartida_sigue_cerrada_desde_el_otro_mes(octubre):
    """Los periodos se solapan, y una semana es una, no dos.

    La primera semana de octubre es también la última de septiembre. Cerrarla
    desde septiembre y preguntar desde octubre daba «no está cerrada», porque
    la consulta filtraba por el mes desde el que se miraba.
    """
    primer_lunes = calendario.semanas(10, 2026)[0][0].isoformat()
    _cerrar(primer_lunes, mes=9)

    assert primer_lunes in cierres.semanas_cerradas(2026, 10)


# ----------------------------------- una ausencia aprobada manda sobre el mes

def test_forzar_no_convierte_una_incapacidad_aprobada_en_trabajo(octubre):
    """El horario refleja la decisión; no es donde se deshace.

    Antes quedaba AM, con `solicitud_id` a nulo —o sea, sin rastro de la
    incapacidad— mientras la solicitud seguía aprobada en su pantalla. Quien
    mirara el cuadro veía a alguien trabajando un día que tenía justificado.
    """
    empleado, dia = _dia_editable(octubre, cual=8)
    solicitud = novedades.crear_solicitud({
        'empleado_id': empleado, 'tipo': 'incapacidad',
        'fecha_inicio': dia['fecha'], 'fecha_fin': dia['fecha'],
        'observacion': 'incapacidad médica'})
    novedades.resolver_solicitud(int(solicitud), 'aprobada')

    resultado = edicion.reprogramar(edicion.Peticion(
        mes=10, anio=2026, solo_este_dia=True,
        ajustes_manuales=[{'empleado_id': empleado, 'fecha': dia['fecha'],
                           'turno': 'AM'}],
        permitir_excepciones_manuales=True,
        motivo_excepcion_manual='lo necesito ese día'))

    quedo = _turno_en(resultado['alternativas'][0], empleado, dia['fecha'])
    assert quedo['turno'] == 'INC'
    assert quedo['solicitud_id'] == int(solicitud), (
        'la casilla perdió el vínculo con la novedad que la puso')

    parte = resultado['diagnostico_ajustes_manuales'][0]
    assert parte['estado'] == 'no_aplicado'
    assert 'Solicitudes' in parte['mensaje'], (
        'el aviso tiene que decir dónde se cambia, no mandar a forzar otra vez')


def test_un_ajuste_viejo_no_deja_el_mes_entero_en_rojo(octubre):
    """Si la realidad le pasa por encima, se descarta; no se convierte en error.

    Un ajuste guardado hace semanas sobre un día que después recibió unas
    vacaciones aprobadas no puede marcar como inválidas las cinco propuestas del
    mes: dejaría el mes en rojo sin más salida que ir a buscarlo y borrarlo.
    """
    empleado, dia = _dia_editable(octubre, cual=10)
    nuevo = 'PM' if dia['turno'] != 'PM' else 'AM'
    edicion.reprogramar(edicion.Peticion(
        mes=10, anio=2026, solo_este_dia=True,
        ajustes_manuales=[{'empleado_id': empleado, 'fecha': dia['fecha'],
                           'turno': nuevo}],
        permitir_excepciones_manuales=True,
        motivo_excepcion_manual='cambio pedido por el área'))

    solicitud = novedades.crear_solicitud({
        'empleado_id': empleado, 'tipo': 'vacaciones',
        'fecha_inicio': dia['fecha'], 'fecha_fin': dia['fecha'],
        'observacion': 'vacaciones aprobadas después'})
    novedades.resolver_solicitud(int(solicitud), 'aprobada')

    propuesta = generacion.generar(10, 2026).propuestas[0]
    assert _turno_en(propuesta, empleado, dia['fecha'])['turno'] == 'VAC'
    assert not [e for e in propuesta.get('errores') or []
                if 'novedad aprobada' in str(e)]


# ------------------------ el aviso de «conviene regenerar» no se va solo

def test_generar_sin_elegir_no_borra_el_aviso(octubre):
    """El fallo se veía así: el aviso desaparecía y nada había cambiado.

    Generar deja cinco propuestas encima de la mesa; el horario del mes sigue
    siendo el que había. Se generaba, no se elegía ninguna, y el oficial seguía
    siendo el de antes —sin la novedad recién aprobada dentro— pero ya sin nadie
    que lo dijera.
    """
    from gestor.servicios import periodos

    empleado, dia = _dia_editable(octubre, cual=8)
    solicitud = novedades.crear_solicitud({
        'empleado_id': empleado, 'tipo': 'vacaciones',
        'fecha_inicio': dia['fecha'], 'fecha_fin': dia['fecha'],
        'observacion': 'aprobadas después de elegir el horario'})
    novedades.resolver_solicitud(int(solicitud), 'aprobada')
    periodos.marcar([dia['fecha']], 'se aprobó una novedad')
    assert periodos.estado(10, 2026)['desactualizado'] is True

    era = horarios.oficial(2026, 10)['id']
    nuevas = generacion.generar(10, 2026)

    assert horarios.oficial(2026, 10)['id'] == era, (
        'generar no cambia el horario del mes, solo propone')
    assert periodos.estado(10, 2026)['desactualizado'] is True, (
        'el aviso se fue sin que nada lo resolviera')

    generacion.marcar_oficial(nuevas.propuestas[0]['horario_id'])
    assert periodos.estado(10, 2026)['desactualizado'] is False


def test_recalcular_un_área_no_borra_lo_pendiente_de_otra(octubre):
    """Resolver lo de Gestión Social no resuelve lo de Comunicaciones.

    El aviso se borraba entero, sin área, así que recalcular una hacía
    desaparecer las marcas de las demás —cuyo horario había salido congelado
    tal y como estaba, o sea, sin lo que tuvieran pendiente—.

    El motivo es el mismo texto en las dos, y tiene que serlo: es el que
    escribe `rutas_novedades` cada vez que se aprueba una, venga del área que
    venga. Con dos textos distintos la prueba pasaría sin el arreglo.
    """
    from gestor.servicios import periodos

    periodos.marcar(['2026-10-15'], 'se aprobó una novedad', area='gestion_social')
    periodos.marcar(['2026-10-15'], 'se aprobó una novedad', area='comunicaciones')

    resultado = edicion.reprogramar(edicion.Peticion(
        mes=10, anio=2026, areas=['gestion_social']))
    generacion.marcar_oficial(resultado['alternativas'][0]['horario_id'])

    estado = periodos.estado(10, 2026)
    assert list(estado['areas']) == ['comunicaciones'], (
        f'quedaron marcadas {list(estado["areas"])}')
    assert estado['desactualizado'] is True
