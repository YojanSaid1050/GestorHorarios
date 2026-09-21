"""Diagnóstico del motor nativo; no lee ni modifica horarios o contraseñas."""
from __future__ import annotations

import faulthandler
import logging
import platform
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version

from gestor import rutas
from gestor.registro import obtener


def conectar(ventana) -> None:
    log = obtener('gestor.ventana')
    try:
        instalada = version('pywebview')
    except PackageNotFoundError:
        instalada = 'sin metadatos de distribución'
    log.info('Motor nativo: pywebview=%s; Python=%s; sistema=%s',
             instalada, platform.python_version(), platform.system())
    # pywebview escribe en otro logger. El ejecutable sin consola también debe
    # conservar sus errores de inyección, renderer y WebView2.
    externo = logging.getLogger('pywebview')
    for handler in obtener().handlers:
        if handler not in externo.handlers:
            externo.addHandler(handler)
    for nombre in ('initialized', 'shown', 'before_load', 'loaded', 'closed'):
        evento = getattr(ventana.events, nombre, None)
        if evento is not None:
            def anotar(*args, etapa=nombre):
                log.info('Ventana: %s', etapa)
            evento += anotar


@contextmanager
def pilas_si_se_bloquea(activar: bool):
    """El watchdog de Python funciona aunque el bucle de Windows deje de responder."""
    if not activar:
        yield
        return
    destino = rutas.RAIZ_DATOS / 'diagnostico-ventana.log'
    with destino.open('a', encoding='utf-8') as archivo:
        obtener().info('Diagnóstico nativo activo: pilas cada 45 s en %s', destino)
        faulthandler.dump_traceback_later(45, repeat=True, file=archivo)
        try:
            yield
        finally:
            faulthandler.cancel_dump_traceback_later()
