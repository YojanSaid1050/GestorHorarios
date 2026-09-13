# -*- coding: utf-8 -*-
"""La ventana del escritorio, cuando la hay.

La aplicación es un servidor local con una ventana delante, pero el servidor
tiene que funcionar igual **sin** ventana: así se puede abrir en un navegador
para mirar algo, y así las pruebas no necesitan un escritorio.

Por eso la ventana no se importa: se **registra**. Quien arranca el programa deja
aquí la ventana que ha creado, y el resto del código pregunta si hay alguna. Sin
ella, las funciones que necesitan escritorio —«Guardar como», abrir una carpeta—
dicen que no están disponibles en vez de fallar con un error de importación que
no significa nada para quien lo lee.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from gestor.registro import obtener

_ventana = None


def registrar(ventana) -> None:
    """La llama quien abre la aplicación de escritorio, una sola vez."""
    global _ventana
    _ventana = ventana


def hay_ventana() -> bool:
    return _ventana is not None


def actual():
    return _ventana


def guardar_como(nombre_sugerido: str, carpeta: Optional[str] = None) -> Optional[str]:
    """Abre el «Guardar como» del sistema y devuelve la ruta elegida.

    `None` significa que la persona canceló. Que no haya ventana es distinto y
    se dice con una excepción: quien llama tiene que poder ofrecer la
    alternativa de guardar en la carpeta de exportaciones.
    """
    if _ventana is None:
        raise RuntimeError(
            'Este equipo no tiene el diálogo nativo de guardado disponible. '
            'El archivo se guardará en la carpeta de exportaciones.')
    import webview  # noqa: PLC0415
    elegido = _ventana.create_file_dialog(
        webview.SAVE_DIALOG, directory=str(carpeta or ''),
        save_filename=nombre_sugerido)
    if not elegido:
        return None
    return elegido if isinstance(elegido, str) else str(elegido[0])


def abrir_en_el_sistema(ruta) -> bool:
    """Abre un archivo o una carpeta con el programa que el sistema tenga puesto.

    Devuelve si se pudo. No lanza: que no se pueda abrir un Excel no es motivo
    para que falle la exportación que acaba de guardarlo bien.
    """
    destino = Path(ruta)
    if not destino.exists():
        return False
    try:
        if sys.platform.startswith('win'):
            os.startfile(str(destino))                             # noqa: S606
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(destino)])               # noqa: S603,S607
        else:
            subprocess.Popen(['xdg-open', str(destino)])           # noqa: S603,S607
        return True
    except Exception:                                              # noqa: BLE001
        obtener().exception('no se pudo abrir %s en el sistema', destino)
        return False
