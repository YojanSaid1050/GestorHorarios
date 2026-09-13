# -*- coding: utf-8 -*-
"""Dejar constancia de lo que falla, para poder mirarlo después.

El programa se entrega como un ejecutable de Windows sin consola. Cuando algo
falla en el equipo de la oficina no hay ventana negra que leer, ni terminal, ni
nada: la persona ve que «no funciona» y ahí se acaba la información. Durante
mucho tiempo el backend no escribió una sola línea de registro y había cuarenta
y nueve sitios que capturaban un error y seguían adelante en silencio.

Esto no es para el usuario —a quien hay que hablarle en la pantalla y con
palabras suyas— sino para quien tenga que averiguar qué pasó.

El archivo vive junto a los datos, se corta a medio mega y se conservan tres.
Si ni siquiera se puede escribir ahí, el programa arranca igual: un registro que
impide usar la aplicación sería peor que no tenerlo.
"""
from __future__ import annotations

import logging
import logging.handlers

# Dónde está escribiendo ahora mismo, para notar si la carpeta de datos cambia.
_CARPETA_ACTUAL: object = None


def obtener(nombre: str = 'gestor') -> logging.Logger:
    """El registro del programa, apuntando siempre a la carpeta de datos de ahora.

    Se comprueba la carpeta en cada llamada, y no una sola vez al principio. En
    el programa instalado la carpeta no cambia nunca, así que esto no hace nada;
    pero la batería de pruebas le da a cada prueba su propia carpeta, y un
    registro que se quedara con la primera escribiría dentro del repositorio.
    Ese descuido —fijar una ruta al importar— ya costó caro una vez en
    `rutas.py` y otra en el registro de exportaciones.
    """
    global _CARPETA_ACTUAL
    log_raiz = logging.getLogger('gestor')

    from gestor import rutas as paths
    carpeta = paths.RAIZ_DATOS
    if carpeta != _CARPETA_ACTUAL:
        for viejo in list(log_raiz.handlers):
            log_raiz.removeHandler(viejo)
            try:
                viejo.close()
            except Exception:                                    # noqa: BLE001
                pass
        log_raiz.setLevel(logging.INFO)
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            manejador = logging.handlers.RotatingFileHandler(
                carpeta / 'registro.log', maxBytes=512_000, backupCount=3,
                encoding='utf-8')
            manejador.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s %(name)s: %(message)s'))
            log_raiz.addHandler(manejador)
        except Exception:                                        # noqa: BLE001
            # Sin sitio donde escribir se sigue adelante: el registro es una
            # ayuda para diagnosticar, no un requisito para funcionar.
            log_raiz.addHandler(logging.NullHandler())
        _CARPETA_ACTUAL = carpeta

    return logging.getLogger(nombre)
