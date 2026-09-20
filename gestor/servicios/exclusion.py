# -*- coding: utf-8 -*-
"""Decidir de una en una.

Aprobar una novedad son dos pasos: mirar con qué chocaría y, si no choca,
escribirla. Entre el primero y el segundo cabe otra petición que haga lo mismo,
y las dos se encuentran el terreno libre: dos solicitudes que se contradicen
quedan las dos aprobadas, cada una convencida de que era la única.

`BEGIN IMMEDIATE` no lo resuelve. Serializa las **escrituras**, que es otra
cosa: las dos comprobaciones ya habían pasado antes de que ninguna escribiera.
Lo que hay que serializar es la pareja entera, mirar y escribir, y eso no lo
sabe la base.

Aquí eso es un candado del proceso, y basta: esto es un programa de escritorio
—un solo servidor, en un solo equipo, para tres personas—. No es una solución
para un servicio repartido entre varias máquinas, y si algún día lo fuera, el
sitio donde ponerlo es este y no quince rutas.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

#: Reentrante a propósito: una ruta que ya lo tiene puede llamar a otra que
#: también lo pide —aprobar en grupo llama a aprobar— y quedarse esperándose a
#: sí misma sería un cuelgue, no una protección.
_CANDADO = threading.RLock()


@contextmanager
def decidiendo() -> Iterator[None]:
    """Mirar y escribir, sin que nadie se cuele en medio."""
    with _CANDADO:
        yield
