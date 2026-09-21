"""Doble inofensivo de Velopack, solo para probar el asistente compilado en CI.

Nunca cierra procesos, instala paquetes ni modifica el registro. Solo escribe
archivos de prueba dentro de la carpeta temporal expresamente autorizada.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument('--silent', action='store_true')
    argumentos.add_argument('--installto', required=True)
    argumentos.add_argument('--log')
    opciones = argumentos.parse_args()
    base = Path(os.environ['GESTOR_PRUEBA_RAIZ']).resolve()
    destino = Path(opciones.installto).resolve()
    llamada = Path(os.environ['GESTOR_PRUEBA_LLAMADA'])
    llamada.write_text(json.dumps({'destino': str(destino)}), encoding='utf-8')
    if destino == base or not destino.is_relative_to(base):
        return 91
    actual = destino / 'current'
    actual.mkdir(parents=True, exist_ok=True)
    (actual / 'GestorHorarios.exe').write_bytes(b'archivo de prueba; no ejecutable')
    (destino / 'Update.exe').write_bytes(b'archivo de prueba; no ejecutable')
    (actual / 'sq.version').write_text(
        '<package><metadata><id>GestorHorarios</id></metadata></package>',
        encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
