"""Servidor local con dueño, espera de arranque y cierre explícitos."""
from __future__ import annotations

import socket
import threading
import time

from gestor.registro import obtener

HOST = '127.0.0.1'


def puerto_libre() -> int:
    with socket.socket() as sonda:
        sonda.bind((HOST, 0))
        return int(sonda.getsockname()[1])


def esperar_al_servidor(puerto: int, segundos: float = 30) -> bool:
    """Compatibilidad para la sonda que comprueba un proceso externo."""
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        try:
            with socket.create_connection((HOST, puerto), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


class ServidorLocal:
    """Reserva el puerto hasta el cierre: no hay carrera entre elegirlo y usarlo."""

    def __init__(self, app=None, puerto: int = 0, espera: float = 30):
        self.app = app
        self.puerto = puerto
        self.espera = espera
        self.servidor = None
        self.hilo = None
        self.socket = None

    @property
    def url(self):
        return f'http://{HOST}:{self.puerto}'

    def __enter__(self):
        import uvicorn

        if self.app is None:
            from gestor.web.aplicacion import app
            self.app = app
        try:
            self.socket = socket.socket()
            self.socket.bind((HOST, self.puerto))
            self.puerto = self.socket.getsockname()[1]
            self.socket.listen(128)
            config = uvicorn.Config(self.app, host=HOST, port=self.puerto,
                                    log_level='warning', access_log=False, log_config=None)
            self.servidor = uvicorn.Server(config)
            self.hilo = threading.Thread(target=self.servidor.run,
                                         kwargs={'sockets': [self.socket]},
                                         name='servidor', daemon=True)
            self.hilo.start()
            limite = time.monotonic() + self.espera
            while not self.servidor.started:
                if not self.hilo.is_alive() or time.monotonic() >= limite:
                    raise RuntimeError('El servidor no terminó de preparar la aplicación.')
                time.sleep(0.05)
            obtener().info('Servidor local preparado en %s', self.url)
            return self
        except BaseException:
            self.cerrar()
            raise

    def cerrar(self):
        if self.servidor is not None:
            self.servidor.should_exit = True
        if self.hilo is not None and self.hilo.is_alive():
            self.hilo.join(timeout=5)
            if self.hilo.is_alive():
                obtener().warning('El servidor sigue cerrando una operación en curso.')
        if self.socket is not None:
            self.socket.close()
            self.socket = None

    def __exit__(self, *_):
        self.cerrar()
