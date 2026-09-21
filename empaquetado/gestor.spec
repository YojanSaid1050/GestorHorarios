# -*- mode: python ; coding: utf-8 -*-
"""Cómo se empaqueta el Gestor de Horarios para Windows.

Es **--onedir**, no --onefile, y esa es la decisión que hay detrás de todo lo
demás. Un solo archivo tiene que descomprimirse entero en una carpeta temporal
cada vez que se abre: tarda más, algunos antivirus lo tratan como sospechoso, y
—lo importante— Velopack no puede reemplazar por partes lo que viaja en un
bloque. Con una carpeta, cada versión ocupa la suya y actualizar es cambiar cuál
es la buena; una actualización o está entera o no está.

Lo que viaja dentro:

* la **pantalla** completa (HTML, CSS y JavaScript), porque el servidor la sirve
  desde el propio programa;
* los **datos iniciales** —el personal y las dos programaciones base— sin los
  cuales una instalación nueva arranca vacía y no puede empezar por octubre.

Lo que **no** viaja: nada de la carpeta de datos del usuario. Se crea en su
sitio la primera vez que se abre.
"""
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

RAIZ = Path(SPECPATH).resolve().parent

# ---------------------------------------------------------------------------
# Cómo se llama aquí el módulo que recibe archivos subidos.
#
# Es una dependencia de verdad —sin ella, la ruta que restaura una copia revienta
# al **definirse**, o sea al arrancar la aplicación entera— y cambió de nombre por
# el camino. Se busca el que exista y, si no existe ninguno, se para: construir un
# instalador que no arranca es peor que no construir nada.
# ---------------------------------------------------------------------------
import importlib.util as _buscar

NOMBRE_DE_MULTIPART = [n for n in ('multipart', 'python_multipart')
                       if _buscar.find_spec(n) is not None]
if not NOMBRE_DE_MULTIPART:
    raise SystemExit(
        'Falta «python-multipart», que es lo que usa FastAPI para recibir el '
        'archivo de una copia de seguridad. Instálalo con:\n'
        '    pip install -r requisitos.txt\n'
        'Sin él el ejecutable se construye y no arranca.')


a = Analysis(
    [str(RAIZ / 'gestor' / 'principal.py')],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=[
        *copy_metadata('pywebview'),
        (str(RAIZ / 'gestor' / 'pantalla'), 'gestor/pantalla'),
        (str(RAIZ / 'datos_iniciales'), 'datos_iniciales'),
    ],
    hiddenimports=[
        # Uvicorn y FastAPI cargan piezas por nombre en tiempo de ejecución, así
        # que el analizador estático no las ve. Sin esta lista el ejecutable se
        # construye sin quejarse y falla al arrancar, que es el peor momento.
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        # Lo carga FastAPI solo cuando ve la primera ruta que recibe un archivo
        # —restaurar una copia—, así que el analizador no lo encuentra solo. Y el
        # nombre del módulo **depende de la versión instalada**: hasta la 0.0.12
        # se importaba como `multipart` y desde entonces como `python_multipart`.
        # Poner los dos a pelo no vale: PyInstaller escribe `ERROR: Hidden import
        # no encontrado` para el que falte y **sigue construyendo**, así que el
        # aviso se pierde entre veinte mil líneas de registro y el fallo aparece
        # al arrancar, cuando ya está entregado. Se pregunta cuál existe.
        *NOMBRE_DE_MULTIPART,
        'webview.platforms.edgechromium',
        'openpyxl',
        'velopack',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pytest', 'numpy'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GestorHorarios',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Sin consola: la aplicación es una ventana. Lo que falla se apunta en el
    # registro de la carpeta de datos, que la pantalla enseña.
    console=False,
    icon=str(RAIZ / 'empaquetado' / 'icono.ico')
        if (RAIZ / 'empaquetado' / 'icono.ico').exists() else None,
    version=str(RAIZ / 'empaquetado' / 'version_windows.txt')
        if (RAIZ / 'empaquetado' / 'version_windows.txt').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='GestorHorarios',
)
