# -*- coding: utf-8 -*-
"""Qué pasa con los datos cuando alguien desinstala el programa.

Desinstalar borra el programa. Los datos —el personal, las novedades, los meses
publicados, el historial— viven aparte a propósito, y la pregunta de si también
se van es de la persona, no del instalador.

Se pregunta **una vez, con claridad y con la ruta delante**, y ante cualquier
duda se conservan:

* si la pregunta no se puede hacer (una desinstalación silenciosa, o un sistema
  sin ventanas), **no se borra nada**;
* si se puede hacer pero **nadie contesta en dos minutos**, tampoco. Preguntar
  sin tope dejaba la desinstalación esperando para siempre un clic que en un
  equipo sin nadie delante no iba a llegar;
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
MB_AL_FRENTE = 0x10000          # MB_SETFOREGROUND
MB_ENCIMA_DE_TODO = 0x40000     # MB_TOPMOST
RESPUESTA_SI = 6
#: Lo que contesta Windows cuando se acabó el tiempo y nadie pulsó nada.
RESPUESTA_SE_ACABO_EL_TIEMPO = 32000

#: Cuánto se espera a que alguien conteste. Dos minutos es de sobra para quien
#: está delante, y un tope para cuando no hay nadie.
ESPERA_MAXIMA_MS = 120_000

ICONO_AVISO = 0x30
ICONO_INFORMACION = 0x40


def _es_un_si(respuesta: int) -> bool:
    """De lo que contesta Windows a sí o no.

    Está aparte para poder comprobarlo sin abrir un cuadro de diálogo. Lo que
    importa aquí es que **todo lo que no sea un sí explícito es un no**: el
    tiempo agotado, la ventana cerrada con la cruz, un código que no se esperaba.
    """
    return int(respuesta) == RESPUESTA_SI


def _preguntar(texto: str, titulo: str) -> bool:
    """Sí o no, con el «no» preseleccionado y **con un tope de tiempo**.

    Que el botón marcado por defecto sea «no» no es un detalle: quien desinstala
    va deprisa y pulsa Intro. Con el «sí» por defecto, una tecla de más borraría
    el trabajo de la oficina.

    Y el tope tampoco. La cabecera de este archivo lleva desde el principio
    diciendo que si la pregunta no se puede hacer —«un sistema sin ventanas»— no
    se borra nada, pero el código no lo cumplía: `MessageBoxW` **espera para
    siempre** a que alguien pulse un botón. Donde no hay nadie —un despliegue
    gobernado por el sistema, una sesión sin escritorio interactivo— la
    desinstalación se quedaba colgada sin decir nada y sin terminar nunca.

    Lo destapó una máquina de GitHub: la batería de pruebas se paró once minutos
    en este preciso `MessageBoxW`, esperando un clic que no iba a llegar.

    Se usa `MessageBoxTimeoutW`, que hace lo mismo y se rinde sola. No está en la
    documentación de Microsoft pero lleva ahí desde Windows XP y es lo que usa
    medio mundo para esto. Si no estuviera, se conserva sin preguntar: quedarse
    esperando es peor que no preguntar.
    """
    if os.name != 'nt':
        return False
    estilo = (MB_SI_NO | MB_ICONO_PREGUNTA | MB_PRIMERO_EL_NO
              | MB_AL_FRENTE | MB_ENCIMA_DE_TODO)
    try:
        preguntar_con_tope = ctypes.windll.user32.MessageBoxTimeoutW
    except Exception:                                              # noqa: BLE001
        return False
    try:
        respuesta = preguntar_con_tope(None, texto, titulo, estilo, 0,
                                       ESPERA_MAXIMA_MS)
    except Exception:                                              # noqa: BLE001
        # Sin poder preguntar, se conserva. Es la decisión que no es
        # irreversible.
        return False
    return _es_un_si(respuesta)


def _avisar(texto: str, titulo: str, icono: int) -> None:
    """Contarle algo a quien desinstala, sin quedarse esperando su clic.

    Estos dos avisos —«no se pudieron borrar» y «quedó una copia»— llamaban a
    `MessageBoxW` directamente, con el mismo problema que la pregunta: donde no
    hay nadie que pulse «Aceptar», la desinstalación no termina nunca. Y aquí es
    peor, porque a estas alturas los datos **ya están borrados**: el trabajo está
    hecho y lo único que queda pendiente es un cartel.

    Por eso un aviso que nadie lee no es un problema, y esperar por él sí.
    """
    if os.name != 'nt':
        return
    try:
        ctypes.windll.user32.MessageBoxTimeoutW(
            None, texto, titulo, icono | MB_AL_FRENTE | MB_ENCIMA_DE_TODO, 0,
            ESPERA_MAXIMA_MS)
    except Exception:                                              # noqa: BLE001
        # Que no se pueda enseñar el cartel no cambia nada de lo que ya pasó.
        pass


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
        _avisar(f'No se pudieron borrar los datos:\n{exc}\n\nSiguen en '
                f'{carpeta}. Puedes borrar esa carpeta a mano cuando quieras.',
                f'Desinstalar {version.NOMBRE}', ICONO_AVISO)
        return

    if copia:
        _avisar(f'Se borraron los datos.\n\nPor si acaso, quedó una copia de la '
                f'base de datos en:\n{copia}\n\nSi no la necesitas, puedes '
                'borrarla.',
                f'Desinstalar {version.NOMBRE}', ICONO_INFORMACION)
