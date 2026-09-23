"""Aplicar una actualización privada de septiembre sin sustituir la nómina.

GESTOR_BASE_SEPTIEMBRE contiene el JSON transcrito del Excel, codificado en
base64. Es opcional: cuando no existe se conserva la base de GESTOR_NOMINA.
No toca ninguna base de datos instalada ni modifica agosto.
"""
from __future__ import annotations

import base64
import csv
import json
import os
from datetime import date, timedelta
from pathlib import Path

VARIABLE = 'GESTOR_BASE_SEPTIEMBRE'


def aplicar(datos: Path) -> bool:
    texto = os.environ.get(VARIABLE, '').strip()
    if not texto:
        return False
    try:
        contenido = base64.b64decode(texto, validate=True).decode('utf-8-sig')
        base = json.loads(contenido)
    except (ValueError, UnicodeError) as error:
        raise SystemExit(f'{VARIABLE} no contiene un JSON en base64 válido.') from error
    if not isinstance(base, dict) or base.get('periodo') != {'anio': 2026, 'mes': 9}:
        raise SystemExit(f'{VARIABLE} debe corresponder a septiembre de 2026.')
    with (datos / 'empleados_iniciales.csv').open(encoding='utf-8-sig', newline='') as archivo:
        nombres = {fila['nombre'].strip() for fila in csv.DictReader(archivo)}
    personas = base.get('empleados')
    if not isinstance(personas, list) or not personas:
        raise SystemExit('La actualización de septiembre no contiene personal.')
    fechas = {(date(2026, 8, 31) + timedelta(days=i)).isoformat() for i in range(35)}
    vistos = set()
    for persona in personas:
        nombre = persona.get('nombre') if isinstance(persona, dict) else None
        if not isinstance(nombre, str) or nombre not in nombres or nombre in vistos:
            raise SystemExit('Septiembre contiene una persona desconocida o duplicada. '
                             'Revisa la correspondencia con la plantilla original.')
        vistos.add(nombre)
        turnos = persona.get('turnos')
        if not isinstance(turnos, dict) or set(turnos) != fechas:
            raise SystemExit('Cada persona debe tener los 35 días del 31/08 al 04/10.')
        if any(not isinstance(t, str) or t not in {'AM', 'PM', 'D', 'ADM-GS', 'ADM-AC'}
               for t in turnos.values()):
            raise SystemExit('Septiembre contiene un turno no reconocido.')
    (datos / 'base_septiembre_2026.json').write_text(
        json.dumps(base, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Septiembre actualizado desde la fuente privada: {len(personas)} personas, 35 días.')
    return True
