# -*- coding: utf-8 -*-
"""Cómo quedó la ventana la última vez, y con qué barra de título se abre.

Dos cosas pequeñas que se notan todos los días:

* **la ventana vuelve como la dejaste.** Abría siempre a 1440×900 en el centro,
  y quien trabaja con el horario a un lado y el Excel al otro tenía que
  recolocarla cada mañana;
* **la barra de título puede ser la del programa** en vez de la gris de Windows.
  Es lo único de todo el proyecto que no se puede comprobar sin un escritorio
  delante, y por eso lleva interruptor: si se porta mal en algún equipo, se
  vuelve a la de Windows desde Configuración, sin reinstalar nada.

## Por qué se guarda en la base y no en un archivo suelto

Porque la base ya es lo que se copia, lo que se restaura y lo que se conserva al
desinstalar. Un archivo aparte se quedaría fuera de las copias de seguridad y, al
restaurar, la ventana volvería a un sitio que no es el que tenía ese día.

## Lo que nunca se hace

**No se confía en las medidas guardadas.** Un portátil que se desenchufa de dos
monitores deja una ventana guardada en x=2400, que en un solo monitor está fuera
de la pantalla: se abre en un sitio invisible y parece que el programa no arranca.
Antes de usarlas se comprueban contra las pantallas que hay **ahora**, y si no
caben se vuelve al centro. Es el mismo principio que el resto del programa: ante
la duda, lo que no deja a nadie tirado.
"""
from __future__ import annotations

import json
from typing import Optional

from gestor.datos.base import abierta, transaccion
from gestor.registro import obtener

CLAVE = 'ventana'

#: Con lo que abre la primera vez. El mínimo no es decorativo: por debajo de
#: 1100×700 la cuadrícula del horario empieza a tener barra horizontal y deja de
#: poderse leer una semana de un vistazo, que es para lo que se mira.
ANCHO_POR_DEFECTO = 1440
ALTO_POR_DEFECTO = 900
ANCHO_MINIMO = 1100
ALTO_MINIMO = 700


def _leer_crudo() -> dict:
    try:
        with abierta() as conexion:
            fila = conexion.execute(
                'SELECT valor FROM configuracion WHERE clave=?', (CLAVE,)).fetchone()
    except Exception:                                              # noqa: BLE001
        # Se puede llamar antes de que exista el esquema. Abrir con el tamaño de
        # fábrica es mejor que no abrir, pero queda constancia.
        obtener().exception('no se pudo leer cómo quedó la ventana')
        return {}
    if not fila or not fila['valor']:
        return {}
    try:
        datos = json.loads(fila['valor'])
    except ValueError:
        obtener().warning('lo guardado sobre la ventana no se pudo leer: %r',
                          fila['valor'])
        return {}
    return datos if isinstance(datos, dict) else {}


def _guardar_crudo(datos: dict) -> None:
    with transaccion() as conexion:
        conexion.execute(
            'INSERT INTO configuracion(clave, valor) VALUES(?,?) '
            'ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor',
            (CLAVE, json.dumps(datos, ensure_ascii=False)))


#: Con qué barra de título se abre una instalación recién hecha.
#:
#: **La de Windows**, y es una decisión, no un descuido. La barra propia está
#: terminada y comprobada hasta donde se puede comprobar sin Windows —se conduce
#: con un ratón de verdad en `qa/ventana.py`—, pero lo que hace el sistema con
#: una ventana sin marco no se puede fingir desde aquí, y la oficina no es sitio
#: para estrenar eso sin haberlo visto funcionar.
#:
#: Así que viaja apagada: se enciende desde Configuración → «Barra de la
#: ventana», se prueba en un equipo, y si va bien se deja puesta. El interruptor
#: funciona en los dos sentidos.
BARRA_PROPIA_DE_FABRICA = False


def barra_propia() -> bool:
    """¿La barra de título la pinta el programa o la pone Windows?"""
    return bool(_leer_crudo().get('barra_propia', BARRA_PROPIA_DE_FABRICA))


def poner_barra_propia(propia: bool) -> bool:
    datos = _leer_crudo()
    datos['barra_propia'] = bool(propia)
    _guardar_crudo(datos)
    return bool(propia)


def cabe(x, y, ancho, alto, pantallas) -> bool:
    """¿Esa ventana se vería en alguna de las pantallas que hay ahora?

    Se pide que se vea un trozo con sentido, no un píxel: con cien por cien
    píxeles dentro ya se puede agarrar la barra y traerla al centro, y eso es lo
    que hace falta para que nadie se quede sin poder usar el programa.

    `pantallas` son rectángulos `(x, y, ancho, alto)`. Sin ninguna —que es lo que
    pasa en las pruebas y en un servidor— no hay nada contra lo que comprobar y
    se dice que no cabe: lo seguro es el centro.
    """
    if not pantallas:
        return False
    for px, py, pancho, palto in pantallas:
        visible_x = min(x + ancho, px + pancho) - max(x, px)
        visible_y = min(y + alto, py + palto) - max(y, py)
        if visible_x >= 100 and visible_y >= 100:
            return True
    return False


def como_abrir(pantallas=()) -> dict:
    """Las medidas con las que crear la ventana, ya comprobadas.

    Devuelve siempre algo usable. `x` e `y` valen `None` cuando hay que dejar
    que el sistema la centre, que es lo que se hace la primera vez y cuando lo
    guardado ya no cabe en ninguna pantalla.
    """
    datos = _leer_crudo()
    ancho = max(int(datos.get('ancho') or ANCHO_POR_DEFECTO), ANCHO_MINIMO)
    alto = max(int(datos.get('alto') or ALTO_POR_DEFECTO), ALTO_MINIMO)
    x, y = datos.get('x'), datos.get('y')
    if x is None or y is None or not cabe(int(x), int(y), ancho, alto, pantallas):
        x = y = None
    return {
        'ancho': ancho,
        'alto': alto,
        'x': None if x is None else int(x),
        'y': None if y is None else int(y),
        'maximizada': bool(datos.get('maximizada')),
        'barra_propia': bool(datos.get('barra_propia', BARRA_PROPIA_DE_FABRICA)),
    }


def recordar(ancho: Optional[int] = None, alto: Optional[int] = None,
             x: Optional[int] = None, y: Optional[int] = None,
             maximizada: Optional[bool] = None) -> dict:
    """Apuntar cómo está la ventana ahora mismo.

    Solo se guarda lo que se pasa: mover la ventana no tiene por qué olvidar si
    estaba maximizada, ni al revés.

    **Estando maximizada no se tocan las medidas.** Si se guardaran, al quitar
    la maximización la ventana volvería al tamaño de la pantalla entera y ya no
    habría forma de recuperar el tamaño que tenía antes.
    """
    datos = _leer_crudo()
    if maximizada is not None:
        datos['maximizada'] = bool(maximizada)
    if not datos.get('maximizada'):
        if ancho is not None and alto is not None:
            datos['ancho'] = max(int(ancho), ANCHO_MINIMO)
            datos['alto'] = max(int(alto), ALTO_MINIMO)
        if x is not None and y is not None:
            datos['x'], datos['y'] = int(x), int(y)
    _guardar_crudo(datos)
    return datos
