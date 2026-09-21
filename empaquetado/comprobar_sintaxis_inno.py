"""Compila el asistente completo sin construir ni ejecutar la aplicación.

Python.exe sirve únicamente de archivo de relleno para [Files]. El asistente
resultante nunca se ejecuta y se elimina al terminar la comprobación.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from gestor.version import VERSION

RAIZ = Path(__file__).resolve().parents[1]


def main() -> int:
    if sys.platform != 'win32':
        print('La compilación del asistente requiere Windows e Inno Setup.')
        return 2
    compilador = shutil.which('ISCC')
    if not compilador:
        print('No se encuentra ISCC: ejecuta primero preparar_inno.ps1.')
        return 1
    with tempfile.TemporaryDirectory(prefix='gestor-sintaxis-inno-') as temporal:
        orden = [compilador, f'/DVersionApp={VERSION}',
                 f'/DInstaladorBase={sys.executable}', f'/O{temporal}',
                 '/FComprobacionAsistente', str(RAIZ / 'empaquetado' / 'asistente.iss')]
        try:
            resultado = subprocess.run(orden, check=False, timeout=90)  # noqa: S603
        except subprocess.TimeoutExpired:
            print('El compilador del asistente no terminó en 90 segundos.')
            return 1
        if resultado.returncode:
            return resultado.returncode
        if not (Path(temporal) / 'ComprobacionAsistente.exe').is_file():
            print('Inno terminó sin generar el asistente de comprobación.')
            return 1
    print('El asistente completo compila correctamente. No se ha ejecutado.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
