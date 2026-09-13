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
        self.proceso = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'gestor.web.aplicacion:app',
             '--host', '127.0.0.1', '--port', str(self.puerto), '--log-level', 'warning'],
            cwd=RAIZ, env=entorno,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if not self.esperar():
            salida = ''
            if self.proceso and self.proceso.stdout:
                self.proceso.kill()
                salida = self.proceso.stdout.read()[-3000:]
            raise RuntimeError(f'El servidor no arrancó.\n{salida}')
        return self

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
        if self.proceso and self.proceso.poll() is None:
            self.proceso.terminate()
            try:
                self.proceso.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proceso.kill()

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


def entrar_como_admin(servidor: Servidor) -> dict:
    """Las cabeceras de una sesión de administrador."""
    estado, datos = servidor.pedir('/api/auth/login', 'POST',
                                   {'usuario': 'admin', 'password': 'xYojanSaidx1050'})
    if estado != 200:
        raise RuntimeError(f'No se pudo entrar: {datos}')
    return {'X-Session-Token': datos['token']}
