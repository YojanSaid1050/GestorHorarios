"""Navegador de pruebas configurable, sin rutas de una máquina particular."""
import json
import os


def abrir(guion):
    opciones = {'headless': True}
    ejecutable = os.environ.get('GESTOR_CHROMIUM')
    if ejecutable:
        opciones['executable_path'] = ejecutable
    argumentos = os.environ.get('GESTOR_CHROMIUM_ARGUMENTOS')
    if argumentos:
        opciones['args'] = json.loads(argumentos)
    return guion.chromium.launch(**opciones)
