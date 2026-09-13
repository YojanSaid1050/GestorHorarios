# -*- coding: utf-8 -*-
"""Abrir la aplicación: el servidor local y la ventana que lo enseña.

Cuatro cosas pasan aquí, y el orden importa:

1. **Velopack toma el control primero.** Cuando el programa se está instalando,
   actualizando o desinstalando, Windows lanza este mismo ejecutable con un
   argumento especial; `App.run()` de Velopack hace lo que toca y termina el
   proceso. Si esto no fuera lo primero de todo, una instalación abriría una
   ventana a medio instalar.
2. **Se comprueba que no haya otra copia abierta.** Dos procesos escribiendo en
   la misma base de datos es la forma más rápida de perder un mes de trabajo.
3. **Se levanta el servidor** en un puerto libre, en un hilo aparte.
4. **Se abre la ventana** y se registra, para que «Guardar como» y «abrir
   carpeta» puedan usarla.

El puerto no está fijado a un número concreto a propósito. Un puerto fijo
convierte cualquier cosa que lo esté ocupando —otra aplicación, un proceso
anterior que no llegó a morir— en un arranque fallido que nadie sabe explicar.
Se pide uno libre al sistema y se le dice a la ventana cuál tocó.
"""
from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import time

from gestor import rutas, version

#: Solo una copia a la vez. El nombre lleva la versión fuera a propósito: si la
#: llevara dentro, una versión nueva podría abrirse encima de una vieja y las
#: dos escribirían en la misma base.
MUTEX = r'Local\GestorHorarios_InstanciaUnica'
_YA_EXISTE = 183

HOST = '127.0.0.1'


class UnaSolaCopia:
    """Impide que se abran dos Gestores de Horarios a la vez."""

    def __init__(self) -> None:
        self._asa = None

    def conseguida(self) -> bool:
        if os.name != 'nt':
            return True
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        asa = kernel32.CreateMutexW(None, True, MUTEX)
        if not asa:
            return False
        if kernel32.GetLastError() == _YA_EXISTE:
            kernel32.CloseHandle(asa)
            return False
        self._asa = asa
        return True

    def soltar(self) -> None:
        if os.name == 'nt' and self._asa:
            try:
                ctypes.windll.kernel32.ReleaseMutex(self._asa)
                ctypes.windll.kernel32.CloseHandle(self._asa)
            except Exception:                                      # noqa: BLE001
                pass
            self._asa = None


def avisar(texto: str, titulo: str = version.NOMBRE, error: bool = False) -> None:
    """Un aviso que se vea aunque no haya ventana todavía."""
    if os.name == 'nt':
        try:
            ctypes.windll.user32.MessageBoxW(None, texto, titulo, 0x10 if error else 0x40)
            return
        except Exception:                                          # noqa: BLE001
            pass
    print(f'{titulo}: {texto}', file=sys.stderr)


def puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.bind((HOST, 0))
        return int(sonda.getsockname()[1])


def esperar_al_servidor(puerto: int, segundos: float = 30.0) -> bool:
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            with socket.create_connection((HOST, puerto), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _arrancar_servidor(puerto: int):
    import uvicorn

    from gestor.web.aplicacion import app

    configuracion = uvicorn.Config(app, host=HOST, port=puerto, log_level='warning',
                                   access_log=False)
    servidor = uvicorn.Server(configuracion)
    hilo = threading.Thread(target=servidor.run, name='servidor', daemon=True)
    hilo.start()
    return servidor


def _velopack() -> None:
    """Deja que el instalador haga lo suyo antes de abrir nada.

    Windows lanza este mismo ejecutable durante la instalación, la
    actualización y la desinstalación, con un argumento que lo dice. `run()`
    atiende esos casos y termina el proceso; en un arranque normal no hace nada
    y la aplicación sigue.

    `set_auto_apply_on_startup(False)` es deliberado: actualizar es una decisión
    que toma una persona desde la pantalla, no algo que ocurra sola mientras
    alguien está armando el horario de un mes.

    Si Velopack no está —al ejecutar el código fuente, o en las pruebas— no pasa
    nada: la aplicación es exactamente la misma sin él.
    """
    try:
        from velopack import App  # noqa: PLC0415
    except ImportError:
        return
    try:
        from gestor.desinstalacion import al_desinstalar

        aplicacion = App()
        aplicacion.set_auto_apply_on_startup(False)
        aplicacion.on_before_uninstall_fast_callback(lambda _version: al_desinstalar())
        aplicacion.run()
    except Exception:                                              # noqa: BLE001
        from gestor.registro import obtener
        obtener().exception('Velopack no pudo procesar el arranque')


def abrir() -> int:
    _velopack()

    unica = UnaSolaCopia()
    if not unica.conseguida():
        avisar('El Gestor de Horarios ya está abierto. Busca su ventana en la barra '
               'de tareas.')
        return 0

    try:
        rutas.preparar()
    except Exception as exc:                                       # noqa: BLE001
        avisar(f'No se pudo preparar la carpeta de datos en {rutas.RAIZ_DATOS}: {exc}',
               error=True)
        return 1

    puerto = puerto_libre()
    servidor = _arrancar_servidor(puerto)
    if not esperar_al_servidor(puerto):
        avisar('El programa no llegó a arrancar. Vuelve a abrirlo; si sigue igual, '
               f'mira el registro en {rutas.REGISTRO}.', error=True)
        return 1

    try:
        import webview  # noqa: PLC0415
    except ImportError:
        # Sin ventana la aplicación sigue siendo usable desde el navegador. Es
        # lo que permite mirar algo desde otro equipo de la oficina.
        avisar(f'Abre {version.NOMBRE} en el navegador: http://{HOST}:{puerto}')
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    from gestor.servicios import ventana as servicio_ventana

    marco = webview.create_window(
        f'{version.NOMBRE} {version.VERSION}', f'http://{HOST}:{puerto}',
        width=1440, height=900, min_size=(1100, 700), confirm_close=False)
    servicio_ventana.registrar(marco)
    try:
        webview.start()
    finally:
        servidor.should_exit = True
        servicio_ventana.registrar(None)
        unica.soltar()
    return 0


def _solo_el_servidor() -> int:
    """Levantar el servidor y nada más. Sin ventana y sin candado.

    Lo usa la autocomprobación, que arranca **otro proceso** de este mismo
    ejecutable para averiguar si arranca partiendo de cero. Sin candado a
    propósito: la copia que está comprobando puede estar abierta, y bloquearse a
    sí misma sería el único resultado que esta comprobación no puede permitirse.
    La carpeta de datos la fija quien llama, con `GESTOR_DATOS`.
    """
    puerto = int(os.environ.get('GESTOR_PUERTO') or 0) or puerto_libre()
    try:
        rutas.preparar()
    except Exception as exc:                                       # noqa: BLE001
        print(f'No se pudo preparar {rutas.RAIZ_DATOS}: {exc}', file=sys.stderr)
        return 1
    servidor = _arrancar_servidor(puerto)
    if not esperar_al_servidor(puerto):
        return 1
    print(f'servidor en http://{HOST}:{puerto}', flush=True)
    try:
        while not servidor.should_exit:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    return 0


def main() -> int:
    # Estas dos banderas van **después** de `_velopack()` en `abrir()`, pero se
    # leen antes de cualquier cosa porque ninguna de las dos quiere ventana.
    # Velopack usa argumentos que empiezan por `--veloapp-`, así que no chocan.
    if '--comprobar' in sys.argv[1:]:
        from gestor.autocomprobacion import comprobar
        return comprobar()
    if '--servidor' in sys.argv[1:]:
        return _solo_el_servidor()
    return abrir()


if __name__ == '__main__':
    raise SystemExit(main())
