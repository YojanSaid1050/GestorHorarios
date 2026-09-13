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
import sys
import uuid
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

TEMPORAL = Path('/tmp/pruebas_gestor_horarios')


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
