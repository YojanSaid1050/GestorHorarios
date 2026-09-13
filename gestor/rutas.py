# -*- coding: utf-8 -*-
"""Dónde está cada cosa: el programa, los datos y lo que la aplicación produce.

Hay una separación que es la más importante de todo el empaquetado y conviene
que esté escrita donde se decide:

* **El programa** vive donde lo pone el instalador y se reemplaza entero en cada
  actualización. Nada que valga la pena guardar puede estar ahí.
* **Los datos** viven en una carpeta aparte que el instalador no toca nunca. Son
  el trabajo de la oficina: personal, solicitudes, horarios publicados,
  historial.

Con Velopack esa separación deja de ser una convención y pasa a ser física: el
instalador coloca cada versión en su propia carpeta dentro de
``%LOCALAPPDATA%\\GestorHorarios`` y va cambiando cuál es la buena. Por eso los
datos **no** pueden vivir ahí debajo: se irían con el programa. Van a
``%LOCALAPPDATA%\\GestorHorarios-datos``, que es una carpeta hermana, fácil de
enseñar en pantalla y fácil de borrar entera cuando alguien pide empezar de
cero al desinstalar.

Se prefiere `LOCALAPPDATA` a `APPDATA` a propósito: la carpeta de perfil móvil
se sincroniza contra la red en dominios de empresa, y sincronizar un archivo
SQLite abierto es una forma conocida de corromperlo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from gestor.version import ID_APLICACION

#: ¿Estamos dentro del ejecutable empaquetado o corriendo el código a pelo?
EMPAQUETADA = bool(getattr(sys, 'frozen', False))

#: Dónde están los archivos que viajan **con** el programa: la pantalla, los
#: datos iniciales, los iconos. Se reemplazan en cada actualización.
RAIZ_PROGRAMA = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent


def _raiz_de_datos() -> Path:
    """La carpeta de trabajo del usuario.

    La variable de entorno existe para las pruebas y para la QA, que necesitan
    una instalación limpia por cada una. Sin ella, en Windows va a
    ``%LOCALAPPDATA%\\GestorHorarios-datos`` y en desarrollo a ``datos/`` dentro
    del proyecto, para no ensuciar el perfil de quien lo está programando.
    """
    elegida = os.environ.get('GESTOR_DATOS')
    if elegida:
        return Path(elegida).expanduser().resolve()
    if EMPAQUETADA or sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or str(Path.home())
        return Path(base) / f'{ID_APLICACION}-datos'
    return RAIZ_PROYECTO / 'datos'


RAIZ_DATOS = _raiz_de_datos()
BASE_DE_DATOS = RAIZ_DATOS / 'horarios.db'
EXPORTACIONES = RAIZ_DATOS / 'exportaciones'
COPIAS = RAIZ_DATOS / 'copias'
DESCARGAS = RAIZ_DATOS / 'descargas'
#: El archivo donde se apunta lo que falla. Se enseña en pantalla porque es lo
#: primero que hay que mirar cuando alguien llama diciendo que «no funciona».
REGISTRO = RAIZ_DATOS / 'registro.log'

PANTALLA = RAIZ_PROGRAMA / 'gestor' / 'pantalla'
DATOS_INICIALES = RAIZ_PROGRAMA / 'datos_iniciales'


def preparar() -> None:
    """Crea las carpetas que la aplicación necesita para arrancar."""
    for carpeta in (RAIZ_DATOS, EXPORTACIONES, COPIAS, DESCARGAS):
        carpeta.mkdir(parents=True, exist_ok=True)


def dato_inicial(nombre: str) -> Path:
    """Un archivo de los que vienen dentro del programa.

    Si falta, se admite una copia en la carpeta de datos del usuario. Así una
    instalación a la que le falte un archivo se repara dejándolo ahí, en vez de
    obligar a reinstalar; y si no está en ninguno de los dos sitios se devuelve
    la ruta de siempre, para que el aviso hable del sitio que corresponde.
    """
    empaquetado = DATOS_INICIALES / nombre
    if empaquetado.exists():
        return empaquetado
    repuesto = RAIZ_DATOS / 'datos_iniciales' / nombre
    return repuesto if repuesto.exists() else empaquetado


def como_dict() -> dict:
    """Lo que enseña la pantalla de «Archivos y datos»."""
    return {
        'programa': str(RAIZ_PROGRAMA),
        'datos': str(RAIZ_DATOS),
        'base_de_datos': str(BASE_DE_DATOS),
        'exportaciones': str(EXPORTACIONES),
        'copias': str(COPIAS),
        'registro': str(REGISTRO),
        'empaquetada': EMPAQUETADA,
    }
