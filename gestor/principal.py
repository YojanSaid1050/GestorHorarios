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
import sys
import time

from gestor import rutas, version
from gestor.servidor_local import (
    HOST as HOST,
)
from gestor.servidor_local import (
    ServidorLocal,
)
from gestor.servidor_local import (
    esperar_al_servidor as esperar_al_servidor,
)
from gestor.servidor_local import (
    puerto_libre as puerto_libre,
)

#: Solo una copia a la vez. El nombre lleva la versión fuera a propósito: si la
#: llevara dentro, una versión nueva podría abrirse encima de una vieja y las
#: dos escribirían en la misma base.
MUTEX = r'Local\GestorHorarios_InstanciaUnica'
_YA_EXISTE = 183



def _con_salida_aunque_no_haya_consola() -> None:
    """Darle a `sys.stdout` y `sys.stderr` algo donde escribir. Siempre.

    El programa instalado se abre **sin ventana de consola** —es una aplicación
    de escritorio, no una herramienta de terminal—, y en ese caso PyInstaller
    deja `sys.stdout` y `sys.stderr` valiendo `None`. A partir de ahí, cualquier
    `print` revienta con «'NoneType' object has no attribute 'write'», y lo que
    es peor, uvicorn revienta **al arrancar**: su configuración de registro
    pregunta `sys.stdout.isatty()` para decidir si pinta colores.

    Eso es exactamente lo que le pasó al primer instalador que se entregó: un
    cuadro de error de Windows nada más abrir, «Unable to configure formatter
    "default"», y el programa no llegaba a levantarse.

    No se cambia a dónde van los mensajes de verdad: el registro de la
    aplicación sigue yendo a su archivo. Esto solo evita que escribir en un sitio
    que no existe tumbe el programa.
    """
    for nombre in ('stdout', 'stderr'):
        if getattr(sys, nombre, None) is None:
            setattr(sys, nombre, open(os.devnull, 'w', encoding='utf-8'))  # noqa: SIM115


_con_salida_aunque_no_haya_consola()


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


#: Cuánto se espera a que alguien cierre un aviso antes de seguir sin él. Un
#: cartel que nadie lee no es un problema; esperar por él para siempre sí.
ESPERA_MAXIMA_MS = 120_000
MB_AL_FRENTE = 0x10000
MB_ENCIMA_DE_TODO = 0x40000


def avisar(texto: str, titulo: str = version.NOMBRE, error: bool = False) -> None:
    """Un aviso que se vea aunque no haya ventana todavía, y que no se eternice.

    Con `MessageBoxW` a secas, el aviso **espera para siempre** a que alguien
    pulse «Aceptar». Donde no hay nadie —el programa lanzado por una tarea
    programada, por un script de inicio de sesión o por la propia comprobación
    del empaquetado— eso deja el proceso colgado sin terminar nunca y sin un
    error que explique nada. Es el mismo fallo que tuvo el desinstalador y que se
    llevó tres publicaciones por delante.

    Se dice igual por la salida de errores, así que el mensaje no se pierde
    aunque el cartel se rinda o no se pueda abrir.
    """
    if os.name == 'nt':
        try:
            ctypes.windll.user32.MessageBoxTimeoutW(
                None, texto, titulo,
                (0x10 if error else 0x40) | MB_AL_FRENTE | MB_ENCIMA_DE_TODO,
                0, ESPERA_MAXIMA_MS)
        except Exception:                                          # noqa: BLE001
            pass
    print(f'{titulo}: {texto}', file=sys.stderr)








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


def _abrir_ventana(url: str) -> None:
    from gestor import diagnostico_ventana, escritorio
    from gestor.servicios import ventana as servicio_ventana

    try:
        import webview
    except ImportError:
        avisar(f'Abre {version.NOMBRE} en el navegador: {url}')
        while True:
            time.sleep(0.5)

    diagnostico = '--diagnostico-ventana' in sys.argv[1:]
    segura = '--ventana-segura' in sys.argv[1:]
    sin_puente = '--sin-puente' in sys.argv[1:]
    ventana, _puente = escritorio.crear(
        url, f'{version.NOMBRE} {version.VERSION}',
        segura=segura or sin_puente, sin_puente=sin_puente)
    diagnostico_ventana.conectar(ventana)
    servicio_ventana.registrar(ventana)
    try:
        with diagnostico_ventana.pilas_si_se_bloquea(diagnostico):
            webview.start(debug=diagnostico,
                          gui='edgechromium' if sys.platform == 'win32' else None)
    finally:
        servicio_ventana.registrar(None)


def abrir() -> int:
    _velopack()
    unica = UnaSolaCopia()
    if not unica.conseguida():
        avisar('El Gestor de Horarios ya está abierto. Busca su ventana en la barra '
               'de tareas.')
        return 0
    try:
        rutas.preparar()
        with ServidorLocal() as servidor:
            _abrir_ventana(servidor.url)
    except KeyboardInterrupt:
        return 0
    finally:
        # También al fallar los datos, el servidor o create_window, antes de start().
        unica.soltar()
    return 0


def _solo_el_servidor() -> int:
    """Modo de diagnóstico sin ventana. Cerrar el proceso termina el servidor."""
    puerto = int(os.environ.get('GESTOR_PUERTO') or 0)
    rutas.preparar()
    try:
        with ServidorLocal(puerto=puerto) as servidor:
            print(f'servidor en {servidor.url}', flush=True)
            while servidor.hilo.is_alive():
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    return 0


def _lo_que_se_le_cuenta_a_la_oficina(fallo: BaseException) -> str:
    """El mensaje de un fallo que nadie previó, escrito para quien lo va a leer.

    Sin esto, lo que sale es el cuadro de PyInstaller: «Unhandled exception in
    script», ocho líneas de `File "logging\\config.py", line 552` y un nombre de
    excepción. Eso no es un mensaje: es un volcado, y a quien tiene que abrir el
    programa para armar el horario del mes no le dice absolutamente nada, ni
    siquiera a quién llamar.

    Pasó de verdad con el primer instalador entregado. Lo de dentro se arregló;
    esto es para el siguiente, el que todavía no conocemos.
    """
    from gestor import rutas
    return (f'{version.NOMBRE} no pudo abrirse.\n\n'
            f'{type(fallo).__name__}: {fallo}\n\n'
            f'Lo ocurrido queda apuntado con todo detalle en:\n{rutas.REGISTRO}\n\n'
            'Ese archivo es lo que hace falta para arreglarlo. Vuelve a intentarlo; '
            'si sigue igual, pásaselo a quien mantiene el programa.')


def main() -> int:
    # Estas dos banderas van **después** de `_velopack()` en `abrir()`, pero se
    # leen antes de cualquier cosa porque ninguna de las dos quiere ventana.
    # Velopack usa argumentos que empiezan por `--veloapp-`, así que no chocan.
    if '--comprobar-ventana' in sys.argv[1:]:
        from gestor.sonda_ventana import comprobar
        return comprobar()
    if '--sonda-ventana' in sys.argv[1:]:
        from gestor.sonda_ventana import ejecutar
        return ejecutar()
    if '--comprobar' in sys.argv[1:]:
        from gestor.autocomprobacion import comprobar
        return comprobar()
    if '--servidor' in sys.argv[1:]:
        return _solo_el_servidor()
    try:
        return abrir()
    except Exception as fallo:                                     # noqa: BLE001
        # Nada que salga de aquí puede llegar a la pantalla como un volcado.
        try:
            from gestor.registro import obtener
            obtener().exception('el programa no pudo abrirse')
        except Exception:                                          # noqa: BLE001, S110
            pass
        avisar(_lo_que_se_le_cuenta_a_la_oficina(fallo), error=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
