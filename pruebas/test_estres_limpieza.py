# -*- coding: utf-8 -*-
"""El estrés tiene que poder borrar lo que crea, también en Windows.

En la publicación de Windows `qa/estres.py` terminaba los doce meses bien y
después se caía entero al borrar su carpeta temporal:

    PermissionError: [WinError 32] The process cannot access the file because
    it is being used by another process: '...\\datos\\horarios.db'

El «otro proceso» era el propio script. `integridad()` abría la base con
`with sqlite3.connect(...)`, que confirma pero **no cierra**, y en Python 3.11 esa
conexión además forma un ciclo de referencias consigo misma: no se cierra ni al
salir de la función, solo cuando pasa el recolector de ciclos. En Linux borrar un
archivo abierto está permitido y nunca se vio.

Estas pruebas no esperan a Windows para verlo: cuentan directamente los
descriptores que el proceso sigue teniendo abiertos dentro de la carpeta.
"""
from __future__ import annotations

import gc
import os
from pathlib import Path

import pytest

from qa.estres import Prueba, borrar_carpeta
from qa.servidor import Servidor, entrar_como_admin


def _abiertos_dentro_de(carpeta: Path) -> list[str]:
    """Los archivos de esa carpeta que este proceso tiene abiertos ahora mismo."""
    raiz = str(carpeta.resolve())
    abiertos = []
    for descriptor in os.listdir('/proc/self/fd'):
        try:
            destino = os.readlink(f'/proc/self/fd/{descriptor}')
        except OSError:
            continue
        if destino.startswith(raiz):
            abiertos.append(Path(destino).name)
    return abiertos


@pytest.mark.skipif(not Path('/proc/self/fd').is_dir(),
                    reason='cuenta descriptores con /proc; en Windows lo prueba el borrado')
def test_la_comprobación_de_integridad_no_deja_la_base_abierta(tmp_path):
    """Sin forzar la recogida de basura: eso escondería justo el fallo."""
    datos = tmp_path / 'datos'
    prueba = Prueba(tmp_path / 'acta')
    with Servidor(datos) as prueba.s:
        prueba.h = entrar_como_admin(prueba.s)
        prueba.integridad()
        propios = _abiertos_dentro_de(datos)
    assert not propios, (
        f'tras comprobar la integridad este proceso sigue teniendo abiertos {propios}; '
        'en Windows eso impide borrar la carpeta')


def test_el_servidor_de_pruebas_sale_muerto_y_sin_dejar_archivos(tmp_path):
    datos = tmp_path / 'datos'
    with Servidor(datos) as servidor:
        registro = servidor.registro
        proceso = servidor.proceso
    assert proceso.poll() is not None, 'el servidor sigue vivo después de salir'
    assert not registro.exists(), 'se quedó el archivo con lo que dijo el servidor'


def test_la_carpeta_de_un_escenario_se_puede_borrar_al_terminar(tmp_path):
    """El recorrido entero de un escenario: servidor, integridad, y borrar."""
    carpeta = tmp_path / 'escenario'
    prueba = Prueba(tmp_path / 'acta')
    with Servidor(carpeta / 'datos') as prueba.s:
        prueba.h = entrar_como_admin(prueba.s)
        prueba.integridad()
    assert borrar_carpeta(carpeta, intentos=1) == ''
    assert not carpeta.exists()


def test_un_fallo_al_borrar_se_cuenta_y_no_tumba_los_demás(tmp_path, monkeypatch):
    """Antes el error saltaba por encima del `try` y se llevaba todo el script."""
    import qa.estres as estres

    monkeypatch.setattr(estres, 'borrar_carpeta', lambda *_a, **_k: 'WinError 32: ocupado')
    monkeypatch.setattr(estres, 'Servidor', _ServidorDeMentira)
    monkeypatch.setattr(estres, 'entrar_como_admin', lambda _s: {})
    prueba = Prueba(tmp_path)
    prueba.bases = list
    prueba.integridad = lambda: None
    corrieron = []
    prueba.ejecutar('primero', lambda: corrieron.append(1))
    prueba.ejecutar('segundo', lambda: corrieron.append(2))

    assert corrieron == [1, 2], 'el segundo escenario no llegó a ejecutarse'
    assert [e['estado'] for e in prueba.informe['escenarios']] == ['fallo', 'fallo']
    assert all('no se pudo limpiar' in f['error'] for f in prueba.informe['fallos'])


class _ServidorDeMentira:
    def __init__(self, carpeta):
        self.carpeta = carpeta

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture(autouse=True)
def _sin_recoger_basura_a_escondidas():
    """Que ningún `gc.collect()` de otra prueba tape el fallo entre medias."""
    antes = gc.isenabled()
    gc.disable()
    yield
    if antes:
        gc.enable()
