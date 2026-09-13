# -*- coding: utf-8 -*-
"""¿Esta instalación funciona? Se lo pregunta el programa a sí mismo.

Se ejecuta con `GestorHorarios.exe --comprobar`, no abre ninguna ventana y
contesta con una lista de líneas y un código de salida. Tiene dos usos, y el
primero es el que la justifica:

**1 · Al construir el instalador.** Hay una familia entera de fallos que no se
ven de ninguna otra forma: el ejecutable se construye sin una queja y no
arranca, porque falta una pieza que PyInstaller no vio. Pasó con las piezas de
uvicorn, que se cargan por nombre. Y estuvo a punto de pasar otra vez con
`python-multipart`, que además **cambió de nombre** entre versiones: se pidió
como `python_multipart`, PyInstaller escribió «Hidden import not found», y
siguió construyendo. Ese aviso queda sepultado entre veinte mil líneas de
registro, y el fallo aparece en el equipo de la oficina.

Un ejecutable que se arranca a sí mismo y contesta «arranco y sirvo» cierra esa
familia entera de una vez, y no solo el caso que se recuerde.

**2 · Cuando alguien llama diciendo que no funciona.** Es lo primero que se le
puede pedir que ejecute, y contesta en diez segundos qué falta y dónde.

Trabaja sobre una **carpeta de datos temporal**, nunca sobre la de la oficina:
esto siembra una instalación nueva y no tiene por qué tocar la buena.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def _pedir(base: str, camino: str, metodo: str = 'GET', cuerpo=None, cabeceras=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    peticion = urllib.request.Request(
        f'{base}{camino}', data=datos, method=metodo,
        headers={'Content-Type': 'application/json', **(cabeceras or {})})
    try:
        with urllib.request.urlopen(peticion, timeout=60) as respuesta:
            return respuesta.status, json.loads(respuesta.read() or b'null')
    except urllib.error.HTTPError as fallo:
        try:
            return fallo.code, json.loads(fallo.read() or b'null')
        except ValueError:
            return fallo.code, None
    except Exception as exc:                                       # noqa: BLE001
        return 0, {'detail': str(exc)}


def _paginar(base: str, camino: str) -> tuple[int, bytes]:
    """Pedir algo que no es JSON —la propia página— y devolverlo en bruto."""
    try:
        with urllib.request.urlopen(f'{base}{camino}', timeout=60) as respuesta:
            return respuesta.status, respuesta.read(400)
    except urllib.error.HTTPError as fallo:
        return fallo.code, b''
    except Exception:                                              # noqa: BLE001
        return 0, b''


class Acta:
    def __init__(self) -> None:
        self.fallos: list[str] = []

    def comprobar(self, bien: bool, que: str, detalle: str = '') -> bool:
        print(f"  [{'ok  ' if bien else 'FALLA'}] {que}"
              + (f'\n          {detalle}' if not bien and detalle else ''), flush=True)
        if not bien:
            self.fallos.append(que)
        return bien


def comprobar() -> int:
    """Arranca el servidor de esta misma copia y le pregunta si está entero."""
    from gestor import version
    from gestor.principal import HOST, esperar_al_servidor, puerto_libre

    print(f'{version.NOMBRE} {version.VERSION} · comprobación de la instalación\n')
    acta = Acta()
    carpeta = Path(tempfile.mkdtemp(prefix='gestor_comprobacion_'))
    proceso = None
    try:
        # Se arranca **otro proceso** del mismo ejecutable, con su carpeta de
        # datos aparte. Levantar el servidor en este mismo proceso no serviría:
        # los módulos ya están importados, y lo que se quiere saber es
        # justamente si se pueden importar todos partiendo de cero.
        puerto = puerto_libre()
        entorno = {**os.environ, 'GESTOR_DATOS': str(carpeta),
                   'GESTOR_PUERTO': str(puerto), 'GESTOR_SIN_VENTANA': '1'}
        # Empaquetado, `sys.executable` **es** el propio programa; corriendo el
        # código a pelo hay que pasarle el módulo. Las dos formas hacen falta: la
        # primera es la que se comprueba de verdad y la segunda es la que permite
        # probar esta comprobación sin construir un instalador.
        orden = ([sys.executable, '--servidor'] if getattr(sys, 'frozen', False)
                 else [sys.executable, '-m', 'gestor.principal', '--servidor'])
        proceso = subprocess.Popen(orden, env=entorno, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        base = f'http://{HOST}:{puerto}'
        arrancó = esperar_al_servidor(puerto, 60.0)
        if not arrancó and proceso.poll() is not None:
            salida = (proceso.stdout.read() if proceso.stdout else '')[-1500:]
            acta.comprobar(False, 'el programa arranca', salida)
            return 1
        acta.comprobar(arrancó, 'el programa arranca y responde')
        if not arrancó:
            return 1

        estado, salud = _pedir(base, '/api/salud')
        acta.comprobar(estado == 200 and salud.get('version') == version.VERSION,
                       'dice la versión que es', f'{estado} · {salud}')
        acta.comprobar(not salud.get('problemas'),
                       'arranca sin problemas que contar',
                       str(salud.get('problemas')))

        # La pantalla: si falta, el programa abre en blanco y nada lo delata.
        # No se pide con `_pedir`, que espera JSON: la página es HTML, y al
        # intentar leerla como JSON esto contestaba «0» y denunciaba una pantalla
        # que estaba perfectamente.
        codigo, cuerpo = _paginar(base, '/')
        acta.comprobar(codigo == 200 and b'<' in cuerpo[:200],
                       'la pantalla está dentro del programa',
                       f'la página principal contestó {codigo}')

        # Los datos iniciales: sin ellos arranca vacío y no se entiende por qué.
        estado, cuentas = _pedir(base, '/api/auth/cuentas-login')
        acta.comprobar(estado == 200 and len(cuentas.get('cuentas') or []) >= 1,
                       'las cuentas de acceso están sembradas', str(cuentas)[:160])

        estado, sesion = _pedir(base, '/api/auth/login', 'POST',
                                {'usuario': 'admin', 'password': 'xYojanSaidx1050'})
        entrado = estado == 200 and sesion.get('token')
        acta.comprobar(bool(entrado), 'se puede entrar', str(sesion)[:160])
        if entrado:
            cabeceras = {'X-Session-Token': sesion['token']}
            estado, gente = _pedir(base, '/api/empleados', cabeceras=cabeceras)
            acta.comprobar(estado == 200 and isinstance(gente, list) and gente,
                           'el personal de fábrica está puesto',
                           f'{estado} · {len(gente) if isinstance(gente, list) else gente}')
            estado, agosto = _pedir(base, '/api/horarios/opciones/2026/8',
                                    cabeceras=cabeceras)
            acta.comprobar(estado == 200 and agosto.get('cantidad'),
                           'los dos meses base están transcritos',
                           f'agosto contestó {estado} · {agosto}')

            # La ruta que recibe un archivo subido. Un 404 aquí significa que
            # falta `python-multipart`: FastAPI no puede ni declararla, y con
            # ella se cae la aplicación entera al arrancar. Es exactamente el
            # fallo que esta comprobación existe para coger.
            estado, _ = _pedir(base, '/api/operacion/restore', 'POST')
            acta.comprobar(estado not in (0, 404, 500),
                           'restaurar una copia está disponible',
                           f'contestó {estado}: falta «python-multipart» en el paquete')

        # El permiso solo hace falta si el repositorio es privado, y hoy no lo
        # es: cualquiera puede preguntar si hay una versión nueva. Se comprueba
        # igual cuando el interruptor esté puesto, porque entonces su ausencia es
        # exactamente lo que deja a una instalación sin enterarse de nada.
        from gestor import credenciales
        from gestor.version import REPOSITORIO_PRIVADO
        permiso = credenciales.permiso()
        if REPOSITORIO_PRIVADO and getattr(sys, 'frozen', False):
            acta.comprobar(bool(permiso),
                           'lleva el permiso para buscar versiones nuevas',
                           'sin él, esta copia no se enterará nunca de una '
                           'actualización, y nada lo avisará')
        elif not permiso:
            print('  [nota ] sin permiso de actualizaciones, que con el '
                  'repositorio público es lo normal')
        if permiso:
            quedan = permiso.dias_que_le_quedan()
            acta.comprobar(quedan is None or quedan > 0,
                           f'y no está caducado (caduca el {permiso.caduca})',
                           f'caducó hace {abs(quedan or 0)} días')
    finally:
        if proceso is not None and proceso.poll() is None:
            proceso.terminate()
            try:
                proceso.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proceso.kill()
        shutil.rmtree(carpeta, ignore_errors=True)

    print()
    if acta.fallos:
        print(f'{len(acta.fallos)} problema(s): ' + ', '.join(acta.fallos))
        return 1
    print('La instalación está entera.')
    return 0
