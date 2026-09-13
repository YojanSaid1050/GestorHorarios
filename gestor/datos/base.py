# -*- coding: utf-8 -*-
"""La conexión con la base de datos, y nada más.

Todo lo que la aplicación guarda pasa por aquí. Dos decisiones que conviene ver
escritas porque las dos vienen de un problema real:

* **`row_factory` a `sqlite3.Row`**, para leer las filas por nombre de columna.
  Leerlas por posición hacía que añadir una columna en medio cambiara en
  silencio lo que devolvía una consulta escrita meses antes.
* **`foreign_keys` activado en cada conexión**, no una vez al crear la base.
  SQLite lo desactiva por defecto y es por conexión: sin esto, borrar a una
  persona dejaba sus solicitudes apuntando a un identificador que ya no existía,
  y el fallo aparecía mucho después, al abrir una pantalla que las listaba.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from gestor import rutas
from gestor.datos import esquema


def conectar() -> sqlite3.Connection:
    rutas.preparar()
    conexion = sqlite3.connect(rutas.BASE_DE_DATOS, timeout=30)
    conexion.row_factory = sqlite3.Row
    conexion.execute('PRAGMA foreign_keys = ON')
    # WAL: permite leer mientras se escribe. La pantalla consulta mucho
    # mientras el motor está armando un mes, y sin esto se veía un «database is
    # locked» en medio de una generación larga.
    #
    # Se comprueba antes de ponerlo, y no es un ahorro: **cambiar de modo de
    # diario pide un candado exclusivo sobre la base**, y esto se ejecutaba en
    # cada conexión, decenas de veces por operación. Mientras otra conexión
    # tuviera algo abierto, esa línea se quedaba esperando el candado. En Linux
    # casi nunca se nota; en Windows, donde los candados de archivo son
    # obligatorios y no orientativos, es una forma de quedarse parado sin un
    # error, sin un mensaje y sin nada que mirar.
    #
    # El modo se guarda en el propio archivo, así que basta con ponerlo la
    # primera vez. Preguntar es una lectura y no bloquea a nadie.
    if conexion.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'wal':
        conexion.execute('PRAGMA journal_mode = WAL')
    return conexion


@contextmanager
def abierta() -> Iterator[sqlite3.Connection]:
    """Una conexión que se cierra sola, aunque algo reviente por el camino."""
    conexion = conectar()
    try:
        yield conexion
    finally:
        conexion.close()


@contextmanager
def transaccion() -> Iterator[sqlite3.Connection]:
    """Todo o nada.

    Se usa siempre que un cambio toca más de una tabla. La aplicación anterior
    tenía sitios donde se borraba de una tabla, fallaba la siguiente y quedaba
    media operación hecha; el caso peor fue un reinicio de programación que
    borró los horarios y dejó vivos los cambios manuales que los reconstruían.
    """
    conexion = conectar()
    try:
        conexion.execute('BEGIN IMMEDIATE')
        yield conexion
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def preparar_base() -> None:
    """Crea la base si no existe y la deja lista para usar."""
    with abierta() as conexion:
        esquema.crear(conexion)


def version_del_esquema() -> int:
    with abierta() as conexion:
        fila = conexion.execute(
            "SELECT valor FROM configuracion WHERE clave='version_esquema'").fetchone()
        return int(fila['valor']) if fila else 0
