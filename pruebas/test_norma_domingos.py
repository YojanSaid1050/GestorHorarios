# -*- coding: utf-8 -*-
"""La comprobación independiente del reparto de domingos.

Era la única regla estricta del motor que nadie más comprobaba. Estas pruebas
fijan tres cosas: que es estricta, que la vigencia parcial se exime con su
motivo, y que un aviso cualquiera del motor **no** sirve de permiso.
"""
from __future__ import annotations

from qa.reglas import norma_domingos


def _persona(nombre, turnos_domingo, heredado_primero=True, **extra):
    fechas = ['2026-10-04', '2026-10-11', '2026-10-18', '2026-10-25']
    dias = [{'fecha': f, 'es_domingo': True, 'mes_propio': True, 'turno': t,
             'heredado': heredado_primero and i == 0}
            for i, (f, t) in enumerate(zip(fechas, turnos_domingo, strict=True))]
    return {'nombre': nombre, 'tipo_turno': 'rotativo', 'descanso_fijo': None,
            'exento_especiales': False, 'dias': dias, **extra}


def test_la_mitad_exacta_cumple():
    assert norma_domingos([_persona('Ana', ['AM', 'D', 'PM', 'D'])]).bien


def test_tres_de_cuatro_incumple_aunque_el_primero_sea_heredado():
    """El domingo heredado cuenta para el total; los demás los decide el programa."""
    n = norma_domingos([_persona('Ana', ['AM', 'AM', 'D', 'AM'])])
    assert n.fallos == ['Ana: trabaja 3 de 4 domingos; le tocaban 2']


def test_quien_entra_a_mitad_de_mes_queda_exento_con_su_motivo():
    n = norma_domingos([_persona('Ana', ['NV', 'AM', 'AM', 'D'])])
    assert n.bien and 'vigente en 3 de 4 domingos' in n.exentos[0]


def test_un_aviso_cualquiera_que_diga_domingos_no_es_permiso():
    """Esto escondía veintidós repartos que el propio motor había rechazado."""
    otro_aviso = ('Ana: cerró el periodo anterior descansando muy al principio de la '
                  'semana, así que en este no le tocaban domingos seguidos')
    n = norma_domingos([_persona('Ana', ['AM', 'AM', 'D', 'AM'])], [otro_aviso])
    assert not n.bien


def test_el_aviso_expreso_de_ese_reparto_si_exime():
    aviso = ('Ana: trabaja 3 de 4 domingos dentro de su vigencia; debía trabajar 2 y '
             'descansar el resto. No se encontró ningún reparto que lo cumpla.')
    n = norma_domingos([_persona('Ana', ['AM', 'AM', 'D', 'AM'])], [aviso])
    assert n.bien and 'avisado por el motor' in n.exentos[0]


def test_administrativos_y_descanso_fijo_no_entran_en_el_reparto():
    n = norma_domingos([
        _persona('Adm', ['AM', 'AM', 'AM', 'AM'], tipo_turno='administrativo'),
        _persona('Fijo', ['AM', 'AM', 'AM', 'AM'], descanso_fijo=3),
    ])
    assert n.bien and len(n.exentos) == 2


# ------------------------------------------------ opciones que el motor descarta

def test_si_el_motor_la_da_por_valida_el_fallo_cuenta():
    from qa.reglas import lo_rechazo_el_motor
    fallo = 'Ana: trabaja 3 de 4 domingos; le tocaban 2'
    assert not lo_rechazo_el_motor(fallo, {'valido': True, 'errores': [fallo]})


def test_si_el_motor_la_descarta_por_lo_mismo_coinciden():
    from qa.reglas import lo_rechazo_el_motor
    error = ('Ana: trabaja 3 de 4 domingos dentro de su vigencia; debía trabajar 2 '
             'y descansar el resto.')
    assert lo_rechazo_el_motor('Ana: trabaja 3 de 4 domingos; le tocaban 2',
                               {'valido': False, 'errores': [error]})


def test_si_el_motor_la_descarta_por_otra_cosa_el_fallo_cuenta():
    from qa.reglas import lo_rechazo_el_motor
    assert not lo_rechazo_el_motor('Ana: trabaja 3 de 4 domingos; le tocaban 2',
                                   {'valido': False, 'errores': ['Luis: pareja en AM']})
