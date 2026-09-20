# -*- coding: utf-8 -*-
"""Lo que toda prueba necesita antes de empezar.

Cada prueba arranca sobre una instalación recién hecha: base vacía y ninguna
huella de la anterior. No es manía. La batería vieja compartía carpeta entre
pruebas y llegó a denunciar un fallo de reparto que en realidad había dejado
escrito otra prueba media hora antes; costó horas encontrarlo. Aquí el
aislamiento es la regla y no la excepción.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Ninguna prueba puede tocar la instalación de nadie. Se fija aquí, **antes** de
# que se importe `gestor.rutas`, porque ese módulo calcula dónde vive todo al
# importarse y ya no hay forma de cambiarlo después.
#
# Sin esto, una prueba que se olvidara de pedir carpeta propia escribía en la de
# verdad: en Windows, `%LOCALAPPDATA%\GestorHorarios-datos`. Se vio desde fuera,
# en el registro de una instalación real, con la traza de un `RuntimeError` que
# lanza a propósito una prueba —la que comprueba que un fallo al abrir se cuenta
# con palabras— apuntada entre los arranques de verdad. Ahí solo era ruido en un
# archivo; la misma rendija deja a una prueba escribir en la base de datos que la
# oficina usa todos los días.
#
# Se respeta si ya viene puesta: la QA fija la suya a propósito.
os.environ.setdefault(
    'GESTOR_DATOS',
    str(Path(tempfile.gettempdir()) / f'gestor_bateria_{os.getpid()}'))

TEMPORAL = Path(tempfile.gettempdir()) / 'pruebas_gestor_horarios'


@pytest.fixture
def carpeta_de_datos(tmp_path, monkeypatch):
    """Una carpeta de datos nueva, y los módulos apuntando a ella.

    Apuntar la variable de entorno no basta: `gestor.rutas` calcula las rutas al
    importarse y otros módulos se quedan con una copia. Hay que recargar el
    módulo para que todo el mundo mire al sitio nuevo. Este detalle fue el
    origen de un fallo fantasma en la versión anterior —una prueba escribía en
    la base de otra— que costó más explicar que arreglar.
    """
    destino = tmp_path / uuid.uuid4().hex[:8]
    monkeypatch.setenv('GESTOR_DATOS', str(destino))

    from gestor import rutas
    importlib.reload(rutas)
    for nombre in ('gestor.datos.base',):
        modulo = sys.modules.get(nombre)
        if modulo is not None:
            importlib.reload(modulo)

    yield destino

    monkeypatch.delenv('GESTOR_DATOS', raising=False)
    importlib.reload(rutas)
    for nombre in ('gestor.datos.base',):
        modulo = sys.modules.get(nombre)
        if modulo is not None:
            importlib.reload(modulo)


@pytest.fixture
def base(carpeta_de_datos):
    """Una base recién creada, con su forma definitiva."""
    from gestor.datos import base as modulo_base
    modulo_base.preparar_base()
    return modulo_base


@pytest.fixture(autouse=True)
def _las_pruebas_arrancan_con_la_clave_ya_cambiada(request, monkeypatch):
    """Como una instalación donde alguien ya hizo lo que hay que hacer.

    Las dos cuentas de fábrica nacen marcadas para cambiar la contraseña, y
    mientras esa marca esté puesta el servidor no deja hacer **nada más** que
    cambiarla: es lo que impide que la contraseña escrita dentro del instalador
    sirva para entrar a la plantilla de la oficina.

    Aquí se quita, y no es relajar la comprobación: es empezar donde empieza
    cualquier instalación pasado el primer día. Comprobar la marca en las
    trescientas pruebas de la batería no aporta nada y las llenaba de 403 que no
    tenían que ver con lo que cada una miraba.

    La comprobación de verdad —que se pone, que bloquea, que cambiarla
    desbloquea y que a quien ya la cambió no se le toca— está entera en
    `pruebas/test_claves_de_fabrica.py`, que se sale de aquí con la marca
    `claves_de_fabrica` para ver el comportamiento real.
    """
    if request.node.get_closest_marker('claves_de_fabrica'):
        yield
        return

    from gestor.servicios import acceso

    original = acceso.asegurar_cuentas_iniciales

    def sin_marca():
        original()
        from gestor.datos.base import transaccion
        with transaccion() as conexion:
            conexion.execute('UPDATE usuarios SET requiere_cambio_clave=0')

    monkeypatch.setattr(acceso, 'asegurar_cuentas_iniciales', sin_marca)
    # Y la reparación de instalaciones antiguas, que corre justo después y
    # volvería a marcarlas: la contraseña de estas cuentas **es** la de fábrica,
    # porque es con la que entran las pruebas.
    monkeypatch.setattr(acceso, 'marcar_las_claves_de_fabrica_que_siguen_puestas',
                        lambda: 0)
    yield


@pytest.fixture(autouse=True)
def _sin_intentos_fallidos_heredados():
    """El contador de intentos fallidos vive en memoria, no en la base.

    Es lo correcto en la oficina —se olvida al reiniciar, nadie se queda fuera
    de su propio programa por un contador que sobrevivió a un apagón— pero
    significa que sobrevive también de una prueba a la siguiente, que sí
    comparten proceso. Varias pruebas entran mal a propósito; sin esto, la
    sexta se encontraría un 429 que no tiene nada que ver con lo que mira.
    """
    from gestor.servicios import acceso
    acceso.olvidar_los_fallos()
    yield
    acceso.olvidar_los_fallos()


@pytest.fixture(scope='session', autouse=True)
def _sin_restos_de_ejecuciones_anteriores():
    import shutil
    shutil.rmtree(TEMPORAL, ignore_errors=True)
    yield
    shutil.rmtree(TEMPORAL, ignore_errors=True)


def pytest_addoption(parser):
    parser.addoption('--lentas', action='store_true', default=False,
                     help='ejecutar también las pruebas que generan meses completos')


def pytest_configure(config):
    config.addinivalue_line('markers', 'lenta: genera meses completos y tarda')


def pytest_collection_modifyitems(config, items):
    if config.getoption('--lentas'):
        return
    saltar = pytest.mark.skip(reason='necesita --lentas')
    for item in items:
        if 'lenta' in item.keywords:
            item.add_marker(saltar)
