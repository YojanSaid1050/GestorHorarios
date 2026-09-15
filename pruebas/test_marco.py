# -*- coding: utf-8 -*-
"""La ventana vuelve como la dejaste, salvo cuando eso sería dejarte tirado.

Lo que se comprueba aquí es la parte que se puede comprobar sin un escritorio
delante: dónde se guarda, qué se guarda y —sobre todo— **cuándo se decide no
hacer caso a lo guardado**.

Esa última parte es la que importa. Un portátil que se desenchufa de dos
monitores deja unas medidas apuntadas en x=2400, y en un solo monitor eso está
fuera de la pantalla: la ventana se abre donde no se ve y parece que el programa
no ha arrancado. Sin nada que enseñar y sin nada que leer.

Lo que la ventana hace de verdad al abrirse —arrastrar, ajustarse a los bordes,
redimensionar— no se puede comprobar desde aquí y está en `EN_WINDOWS.md`.
"""
from __future__ import annotations

import pytest

from gestor.servicios import marco

UN_MONITOR = [(0, 0, 1920, 1080)]
DOS_MONITORES = [(0, 0, 1920, 1080), (1920, 0, 1920, 1080)]


# ------------------------------------------- no fiarse de lo guardado

def test_una_ventana_en_un_monitor_que_ya_no_está_no_se_usa():
    """El caso del portátil que se desenchufa. Es el que justifica todo esto."""
    assert marco.cabe(2400, 100, 1440, 900, DOS_MONITORES) is True
    assert marco.cabe(2400, 100, 1440, 900, UN_MONITOR) is False


def test_una_ventana_medio_fuera_sigue_valiendo():
    """Basta con poder agarrarla y traerla: no hace falta que se vea entera.

    Ser más estricto sería recolocarle la ventana a quien la había dejado a
    propósito asomando por el borde.
    """
    assert marco.cabe(1800, 500, 1440, 900, UN_MONITOR) is True


def test_sin_saber_qué_pantallas_hay_se_va_al_centro():
    """Ante la duda, lo que no deja a nadie sin ver el programa."""
    assert marco.cabe(0, 0, 1440, 900, []) is False


def test_al_abrir_se_descarta_lo_que_no_cabe(base):
    marco.recordar(ancho=1500, alto=950, x=2400, y=100)

    en_dos = marco.como_abrir(DOS_MONITORES)
    assert (en_dos['x'], en_dos['y']) == (2400, 100)

    en_uno = marco.como_abrir(UN_MONITOR)
    assert en_uno['x'] is None and en_uno['y'] is None, (
        'con un solo monitor esa posición está fuera de la pantalla')
    assert (en_uno['ancho'], en_uno['alto']) == (1500, 950), (
        'el tamaño sigue valiendo aunque la posición no'
    )


# ------------------------------------------------------ lo que se guarda

def test_la_ventana_vuelve_como_se_dejó(base):
    marco.recordar(ancho=1600, alto=1000, x=120, y=80)
    puesta = marco.como_abrir(UN_MONITOR)
    assert (puesta['ancho'], puesta['alto']) == (1600, 1000)
    assert (puesta['x'], puesta['y']) == (120, 80)


def test_de_fábrica_abre_centrada_y_con_el_tamaño_de_siempre(base):
    puesta = marco.como_abrir(UN_MONITOR)
    assert (puesta['ancho'], puesta['alto']) == (marco.ANCHO_POR_DEFECTO,
                                                 marco.ALTO_POR_DEFECTO)
    assert puesta['x'] is None and puesta['y'] is None


def test_no_se_puede_guardar_una_ventana_ilegible(base):
    """Por debajo del mínimo la cuadrícula del horario deja de leerse.

    Da igual de dónde venga el número —un arrastre raro, una pantalla que cambia
    de resolución—: lo que se guarda nunca puede dejar el programa inservible.
    """
    marco.recordar(ancho=300, alto=200, x=0, y=0)
    puesta = marco.como_abrir(UN_MONITOR)
    assert puesta['ancho'] >= marco.ANCHO_MINIMO
    assert puesta['alto'] >= marco.ALTO_MINIMO


def test_maximizada_no_se_lleva_por_delante_el_tamaño_de_antes(base):
    """El detalle que hace que esto sirva o no sirva.

    Maximizada, la ventana mide lo que la pantalla. Guardando esas medidas, al
    quitar la maximización volvería a ocupar la pantalla entera y el tamaño que
    la persona había elegido se habría perdido para siempre.
    """
    marco.recordar(ancho=1500, alto=950, x=100, y=60)
    marco.recordar(maximizada=True)
    marco.recordar(ancho=1920, alto=1080, x=0, y=0)

    puesta = marco.como_abrir(UN_MONITOR)
    assert puesta['maximizada'] is True
    assert (puesta['ancho'], puesta['alto']) == (1500, 950), (
        'se perdió el tamaño que tenía antes de maximizar')
    assert (puesta['x'], puesta['y']) == (100, 60)


def test_mover_la_ventana_no_olvida_que_estaba_maximizada(base):
    marco.recordar(maximizada=True)
    marco.recordar(x=10, y=10)
    assert marco.como_abrir(UN_MONITOR)['maximizada'] is True


def test_al_dejar_de_estar_maximizada_se_vuelven_a_guardar_las_medidas(base):
    marco.recordar(ancho=1500, alto=950, x=100, y=60)
    marco.recordar(maximizada=True)
    marco.recordar(maximizada=False)
    marco.recordar(ancho=1300, alto=800, x=20, y=20)

    puesta = marco.como_abrir(UN_MONITOR)
    assert (puesta['ancho'], puesta['alto']) == (1300, 800)


# ------------------------------------------------- la barra de título

def test_la_barra_propia_se_puede_apagar_sin_reinstalar_nada(base):
    """Es lo único del programa que no se puede probar sin un escritorio.

    Por eso lleva interruptor: si en algún equipo se porta mal —no arrastra, no
    se ajusta a los bordes—, se vuelve a la barra de Windows desde Configuración
    y se sigue trabajando, en vez de esperar a una versión nueva.
    """
    # De fábrica va la de Windows: la barra propia es lo único del programa que
    # no se puede comprobar sin un escritorio delante, así que viaja apagada y
    # se enciende a mano cuando alguien la haya visto funcionar.
    assert marco.barra_propia() is marco.BARRA_PROPIA_DE_FABRICA
    assert marco.BARRA_PROPIA_DE_FABRICA is False

    assert marco.poner_barra_propia(True) is True
    assert marco.barra_propia() is True
    assert marco.como_abrir(UN_MONITOR)['barra_propia'] is True

    assert marco.poner_barra_propia(False) is False
    assert marco.barra_propia() is False
    assert marco.como_abrir(UN_MONITOR)['barra_propia'] is False

    marco.poner_barra_propia(True)
    assert marco.barra_propia() is True


def test_apagar_la_barra_no_se_lleva_por_delante_el_tamaño(base):
    marco.recordar(ancho=1500, alto=950, x=100, y=60)
    marco.poner_barra_propia(False)
    puesta = marco.como_abrir(UN_MONITOR)
    assert (puesta['ancho'], puesta['alto']) == (1500, 950)


# --------------------------------------------------- que nada tumbe el arranque

def test_lo_guardado_ilegible_no_impide_abrir(base):
    """Un valor a medias en la base no puede dejar el programa sin arrancar."""
    from gestor.datos.base import transaccion

    with transaccion() as conexion:
        conexion.execute(
            'INSERT INTO configuracion(clave, valor) VALUES(?,?) '
            'ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor',
            (marco.CLAVE, '{esto no es json'))

    puesta = marco.como_abrir(UN_MONITOR)
    assert puesta['ancho'] == marco.ANCHO_POR_DEFECTO
    assert puesta['barra_propia'] is marco.BARRA_PROPIA_DE_FABRICA


def test_sin_base_de_datos_se_abre_igual(carpeta_de_datos):
    """Se llama al arrancar, antes de que el esquema exista siquiera."""
    puesta = marco.como_abrir(UN_MONITOR)
    assert puesta['ancho'] == marco.ANCHO_POR_DEFECTO
    assert puesta['alto'] == marco.ALTO_POR_DEFECTO


@pytest.mark.parametrize('pantallas', [UN_MONITOR, DOS_MONITORES, []])
def test_como_abrir_siempre_devuelve_algo_usable(base, pantallas):
    puesta = marco.como_abrir(pantallas)
    assert puesta['ancho'] >= marco.ANCHO_MINIMO
    assert puesta['alto'] >= marco.ALTO_MINIMO
    assert isinstance(puesta['maximizada'], bool)
