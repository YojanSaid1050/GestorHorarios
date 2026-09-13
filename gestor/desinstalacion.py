# -*- coding: utf-8 -*-
"""Qué pasa con los datos cuando alguien desinstala el programa.

Desinstalar borra el programa. Los datos —el personal, las novedades, los meses
publicados, el historial— viven aparte a propósito, y la pregunta de si también
se van es de la persona, no del instalador.

Se pregunta **una vez, con claridad y con la ruta delante**, y ante cualquier
duda se conservan:

* si la pregunta no se puede hacer (una desinstalación silenciosa, o un sistema
  sin ventanas), **no se borra nada**;
* si algo falla al borrar, **no se borra nada** y se dice dónde quedó todo.

Conservar de más es un fastidio; borrar de más es irreparable. Por eso todos los
caminos que no son un «sí» explícito acaban conservando, y por eso antes de
borrar se deja una copia de la base de datos en el escritorio: si alguien dice
que sí y a los cinco minutos se arrepiente, todavía hay algo que recuperar.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

MB_SI_NO = 0x04
MB_ICONO_PREGUNTA = 0x20
MB_PRIMERO_EL_NO = 0x100
RESPUESTA_SI = 6


def _preguntar(texto: str, titulo: str) -> bool:
    """Sí o no, con el «no» preseleccionado.

    Que el botón marcado por defecto sea «no» no es un detalle: quien desinstala
    va deprisa y pulsa Intro. Con el «sí» por defecto, una tecla de más borraría
    el trabajo de la oficina.
    """
    if os.name != 'nt':
        return False
    try:
        respuesta = ctypes.windll.user32.MessageBoxW(
            None, texto, titulo, MB_SI_NO | MB_ICONO_PREGUNTA | MB_PRIMERO_EL_NO)
        return int(respuesta) == RESPUESTA_SI
    except Exception:                                              # noqa: BLE001
        # Sin poder preguntar, se conserva. Es la decisión que no es
        # irreversible.
        return False


def _copia_de_seguridad(base: Path) -> Path | None:
    """Una copia de la base en el escritorio, antes de borrar nada."""
    if not base.is_file():
        return None
    try:
        escritorio = Path.home() / 'Desktop'
        if not escritorio.is_dir():
            escritorio = Path.home()
        destino = escritorio / f'GestorHorarios_copia_{datetime.now():%Y%m%d_%H%M%S}.db'
        shutil.copy2(base, destino)
        return destino
    except Exception:                                              # noqa: BLE001
        return None


def al_desinstalar() -> None:
    """Lo que Velopack llama justo antes de quitar el programa."""
    from gestor import rutas, version

    carpeta = rutas.RAIZ_DATOS
    if not carpeta.exists():
        return

    # Una desinstalación silenciosa —la que lanza un despliegue automático— no
    # tiene a nadie delante a quien preguntar. Nunca borra.
    if any(a.lower() in ('/silent', '/verysilent', '--silent') for a in sys.argv):
        return

    quiere_borrar = _preguntar(
        f'¿Quieres borrar también los datos de {version.NOMBRE}?\n\n'
        f'Están en:\n{carpeta}\n\n'
        'Ahí está el personal, las novedades, los horarios publicados y el '
        'historial.\n\n'
        'Si eliges No, se conservan: al volver a instalar el programa, todo '
        'seguirá donde estaba.\n'
        'Si eliges Sí, se guardará antes una copia de la base de datos en tu '
        'escritorio.',
        f'Desinstalar {version.NOMBRE}')
    if not quiere_borrar:
        return

    copia = _copia_de_seguridad(rutas.BASE_DE_DATOS)
    try:
        shutil.rmtree(carpeta)
    except Exception as exc:                                       # noqa: BLE001
        ctypes.windll.user32.MessageBoxW(
            None,
            f'No se pudieron borrar los datos:\n{exc}\n\nSiguen en {carpeta}. '
            'Puedes borrar esa carpeta a mano cuando quieras.',
            f'Desinstalar {version.NOMBRE}', 0x30)
        return

    if copia:
        ctypes.windll.user32.MessageBoxW(
            None,
            f'Se borraron los datos.\n\nPor si acaso, quedó una copia de la base '
            f'de datos en:\n{copia}\n\nSi no la necesitas, puedes borrarla.',
            f'Desinstalar {version.NOMBRE}', 0x40)
