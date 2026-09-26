# -*- coding: utf-8 -*-
"""Levantar la aplicación de verdad para poder usarla desde fuera.

No es el `TestClient` de las pruebas: es el servidor real, con su base de datos
en una carpeta nueva, escuchando en un puerto. Es lo único que permite abrirlo
con un navegador y comprobar lo que ve una persona, que es donde aparecen los
fallos que ninguna prueba de Python encuentra: un botón que no llama a nada, una
respuesta con otro nombre de campo, un modal que tapa lo siguiente.

Cada suite arranca su propio servidor sobre una instalación limpia. Compartirla
entre suites fue lo que hizo, en la versión anterior, que una prueba denunciara
un fallo de reparto que en realidad había dejado escrito otra media hora antes.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.bind(('127.0.0.1', 0))
        return int(sonda.getsockname()[1])


class Servidor:
    """La aplicación funcionando, con su carpeta de datos propia."""

    def __init__(self, carpeta: str | Path, limpiar: bool = True):
        self.carpeta = Path(carpeta)
        self.limpiar = limpiar
        self.puerto = puerto_libre()
        self.proceso: subprocess.Popen | None = None

    @property
    def base(self) -> str:
        return f'http://127.0.0.1:{self.puerto}'

    def __enter__(self) -> 'Servidor':
        if self.limpiar and self.carpeta.exists():
            shutil.rmtree(self.carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        entorno = {**os.environ, 'GESTOR_DATOS': str(self.carpeta),
                   'PYTHONPATH': str(RAIZ), 'PYTHONUNBUFFERED': '1'}
        # Lo que diga el servidor va a un archivo, no a una tubería.
        #
        # Con `stdout=PIPE` y nadie leyéndola, el servidor se bloquea en cuanto
        # la llena —en Windows son unos pocos kilobytes— y deja de contestar a
        # mitad de una prueba. Bastan unas cuantas trazas de error de uvicorn,
        # que van a la consola, para llegar ahí. Es el mismo fallo que ya se
        # corrigió en la autocomprobación del ejecutable.
        #
        # Fuera de la carpeta de datos a propósito: esa carpeta la borra quien
        # la creó, y un archivo que el servidor aún tuviera abierto lo impediría.
        descriptor, nombre = tempfile.mkstemp(prefix='gestor-servidor-', suffix='.log')
        os.close(descriptor)
        self.registro = Path(nombre)
        self._salida = self.registro.open('w', encoding='utf-8', errors='replace')
        self.proceso = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'gestor.web.aplicacion:app',
             '--host', '127.0.0.1', '--port', str(self.puerto), '--log-level', 'warning'],
            cwd=RAIZ, env=entorno,
            stdout=self._salida, stderr=subprocess.STDOUT, text=True)
        if not self.esperar():
            self.__exit__()
            raise RuntimeError(f'El servidor no arrancó.\n{self.lo_que_dijo()[-3000:]}')
        return self

    def lo_que_dijo(self) -> str:
        """Todo lo que el servidor escribió en la consola hasta ahora."""
        if getattr(self, 'registro', None) is None:
            return getattr(self, '_dicho', '')
        try:
            return self.registro.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return ''

    def esperar(self, segundos: float = 60.0) -> bool:
        limite = time.time() + segundos
        while time.time() < limite:
            if self.proceso and self.proceso.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(f'{self.base}/api/salud', timeout=1.0):
                    return True
            except (urllib.error.URLError, OSError):
                time.sleep(0.3)
        return False

    def __exit__(self, *_):
        """Pararlo, **y esperar a que haya terminado de verdad**.

        Tras `kill()` no se esperaba. En Windows eso deja un proceso que todavía
        tiene abiertos la base y su registro, y quien borre la carpeta de datos
        justo después se encuentra con «el archivo está siendo usado por otro
        proceso». Un servidor de pruebas que se sale de aquí vivo no es un
        detalle: es una carpeta que no se puede limpiar.
        """
        if self.proceso and self.proceso.poll() is None:
            self.proceso.terminate()
            try:
                self.proceso.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proceso.kill()
                self.proceso.wait(timeout=10)
        salida = getattr(self, '_salida', None)
        if salida is not None and not salida.closed:
            salida.close()
        # Lo que dijo se guarda antes de borrar el archivo, para poder
        # enseñarlo si algo falló; el archivo en sí no tiene por qué quedarse.
        registro = getattr(self, 'registro', None)
        if registro is not None:
            self._dicho = self.lo_que_dijo()
            registro.unlink(missing_ok=True)
            self.registro = None

    # ------------------------------------------------------ hablar con él

    def pedir(self, camino: str, metodo: str = 'GET', cuerpo=None,
              cabeceras: dict | None = None):
        import json
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        peticion = urllib.request.Request(
            f'{self.base}{camino}', data=datos, method=metodo,
            headers={'Content-Type': 'application/json', **(cabeceras or {})})
        try:
            with urllib.request.urlopen(peticion, timeout=300) as respuesta:
                return respuesta.status, json.loads(respuesta.read() or b'null')
        except urllib.error.HTTPError as fallo:
            cuerpo_error = fallo.read()
            try:
                return fallo.code, json.loads(cuerpo_error or b'null')
            except ValueError:
                return fallo.code, {'detail': cuerpo_error.decode('utf-8', 'replace')}


CLAVE_ADMIN_QA = 'RevisionLocal-934!'


def entrar_como_admin(servidor: Servidor) -> dict:
    """Preparar una cuenta de pruebas mediante el flujo real de cambio de clave."""
    estado, datos = servidor.pedir('/api/auth/login', 'POST',
                                   {'usuario': 'admin', 'password': CLAVE_ADMIN_QA})
    if estado != 200:
        estado, datos = servidor.pedir('/api/auth/login', 'POST',
                                       {'usuario': 'admin', 'password': 'xYojanSaidx1050'})
        if estado != 200:
            raise RuntimeError(f'No se pudo preparar la cuenta de pruebas: {datos}')
        cabeceras = {'X-Session-Token': datos['token']}
        estado, datos = servidor.pedir('/api/auth/password', 'PUT',
                                       {'actual': 'xYojanSaidx1050', 'nueva': CLAVE_ADMIN_QA},
                                       cabeceras)
        if estado != 200:
            raise RuntimeError(f'No se pudo cambiar la clave de la cuenta de pruebas: {datos}')
        estado, datos = servidor.pedir('/api/auth/login', 'POST',
                                       {'usuario': 'admin', 'password': CLAVE_ADMIN_QA})
    if estado != 200:
        raise RuntimeError(f'No se pudo entrar: {datos}')
    return {'X-Session-Token': datos['token']}
