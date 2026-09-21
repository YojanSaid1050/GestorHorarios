"""Ejercita el enumerador real de pywebview, sin necesitar un escritorio."""
import threading
from types import SimpleNamespace

import webview.util

from gestor.escritorio import Puente


def enumerar(monkeypatch, puente):
    scripts = []
    cargado = threading.Event()
    anfitrion = SimpleNamespace(
        _js_api=puente, _functions={}, _expose_lock=threading.Lock(),
        run_js=scripts.append,
        events=SimpleNamespace(before_load=threading.Event(),
                               _pywebviewready=threading.Event(), loaded=cargado))

    class HiloSinEspera:
        def __init__(self, target):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(webview.util, 'Thread', HiloSinEspera)
    monkeypatch.setattr(webview.util, 'load_js_files', lambda *_: ('inicio', '%(functions)s'))
    webview.util.inject_pywebview('edgechromium', anfitrion)
    assert cargado.is_set()
    return scripts[-1]


def test_el_puente_no_recuerda_la_ventana_como_objeto_publico(monkeypatch):
    lecturas = []

    class VentanaNativa:
        @property
        def native(self):
            lecturas.append('acceso nativo durante la inyección')
            return None

        def destroy(self):
            pass

    puente = Puente()
    # Asignar igual que escritorio.crear en la versión bajo prueba.
    if hasattr(puente, 'ventana'):
        puente.ventana = VentanaNativa()
    else:
        puente._ventana = VentanaNativa()
    funciones = enumerar(monkeypatch, puente)
    assert lecturas == [], 'pywebview recorrió el objeto nativo antes de terminar su carga'
    assert 'ventana.' not in funciones
    assert 'barra_propia' in funciones


def test_modo_seguro_no_lee_ni_sobrescribe_la_geometria(base, monkeypatch):
    import webview

    from gestor import escritorio
    from gestor.servicios import marco

    def prohibido(*_):
        raise AssertionError('El modo seguro no debe leer ni guardar la geometría')

    opciones = {}
    monkeypatch.setattr(marco, 'como_abrir', prohibido)
    monkeypatch.setattr(escritorio, '_apuntarse_a_los_avisos', prohibido)

    def crear(*_, **kwargs):
        opciones.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(webview, 'create_window', crear)
    escritorio.crear('http://127.0.0.1', 'Prueba', segura=True, sin_puente=True)
    assert opciones['js_api'] is None
    assert 'frameless' not in opciones
    assert 'x' not in opciones


def test_un_error_de_ventana_libera_servidor_y_mutex(monkeypatch):
    import pytest

    from gestor import principal

    pasos = []

    class Copia:
        def conseguida(self):
            return True

        def soltar(self):
            pasos.append('mutex cerrado')

    class Servidor:
        url = 'http://127.0.0.1:1'

        def __enter__(self):
            pasos.append('servidor abierto')
            return self

        def __exit__(self, *_):
            pasos.append('servidor cerrado')

    def falla(_):
        raise RuntimeError('No se puede crear la ventana')

    monkeypatch.setattr(principal, '_velopack', lambda: None)
    monkeypatch.setattr(principal, 'UnaSolaCopia', Copia)
    monkeypatch.setattr(principal, 'ServidorLocal', Servidor)
    monkeypatch.setattr(principal.rutas, 'preparar', lambda: None)
    monkeypatch.setattr(principal, '_abrir_ventana', falla)
    with pytest.raises(RuntimeError):
        principal.abrir()
    assert pasos == ['servidor abierto', 'servidor cerrado', 'mutex cerrado']


def test_servidor_real_responde_y_libera_puerto():
    import socket
    import urllib.request

    from fastapi import FastAPI

    from gestor.servidor_local import ServidorLocal

    app = FastAPI()

    @app.get('/sonda')
    def sonda():
        return {'ok': True}

    with ServidorLocal(app=app) as servidor:
        puerto = servidor.puerto
        with urllib.request.urlopen(servidor.url + '/sonda', timeout=2) as r:
            assert r.status == 200
        hilo = servidor.hilo
    assert not hilo.is_alive()
    # TIME_WAIT puede impedir un nuevo bind aun con el servidor cerrado.
    # Lo que importa es que no siga aceptando conexiones ni ejecutando el hilo.
    with socket.socket() as conexion:
        conexion.settimeout(0.5)
        assert conexion.connect_ex(('127.0.0.1', puerto)) != 0
