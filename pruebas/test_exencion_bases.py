"""El pasado manual es inmutable; continuar un incumplimiento no queda exento."""
from copy import deepcopy
from datetime import date, timedelta

from gestor.dominio.nucleo import _tope_absoluto
from gestor.motor.comun import (
    _violaciones_fatiga_laboral,
    _violaciones_max_dias_consecutivos,
)


def persona(turnos, origen='base_septiembre_2026'):
    return {'empleado_id': 1, 'nombre': 'Persona histórica', 'tipo_turno': 'rotativo',
            'dias': [{'fecha': (date(2026, 9, 20) + timedelta(days=i)).isoformat(),
                      'turno': t, 'origen': origen, 'bloqueado': True, 'heredado': True}
                     for i, t in enumerate(turnos)]}


def test_la_fatiga_de_la_base_no_es_un_conflicto_nuevo():
    fila = persona(['PM', 'AM'])
    antes = deepcopy(fila)
    assert not _violaciones_fatiga_laboral([fila])
    assert fila == antes


def test_un_am_nuevo_despues_del_pm_historico_si_se_comprueba():
    fila = persona(['PM', 'AM'])
    fila['dias'][-1].update(origen='turno_base', heredado=False, bloqueado=False)
    assert len(_violaciones_fatiga_laboral([fila])) == 1


def test_una_asignacion_manual_no_se_confunde_con_una_base():
    assert len(_violaciones_fatiga_laboral([persona(['PM', 'AM'], 'ajuste_manual')])) == 1


def test_una_jornada_nueva_intermedia_no_queda_exenta():
    fila = persona(['PM', 'CAP', 'AM'])
    fila['dias'][1].update(origen='turno_base', heredado=False, bloqueado=False)
    assert len(_violaciones_fatiga_laboral([fila])) == 1


def test_la_racha_historica_no_bloquea_pero_su_extension_si():
    fila = persona(['AM'] * 16)
    antes = deepcopy(fila)
    assert not _violaciones_max_dias_consecutivos([fila])
    assert not _tope_absoluto([fila])
    assert fila == antes
    fila['dias'][-1].update(origen='turno_base', heredado=False, bloqueado=False)
    assert _violaciones_max_dias_consecutivos([fila])
    assert _tope_absoluto([fila])
