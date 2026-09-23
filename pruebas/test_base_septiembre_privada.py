"""El Excel actualizado no puede sustituir agosto ni inventar personas."""
import base64
import json
from datetime import date, timedelta

import pytest

from empaquetado import base_septiembre


@pytest.fixture
def datos(tmp_path):
    (tmp_path / 'empleados_iniciales.csv').write_text('nombre\nPersona Uno\n', encoding='utf-8')
    (tmp_path / 'base_agosto_2026.json').write_text('agosto original', encoding='utf-8')
    (tmp_path / 'base_septiembre_2026.json').write_text('septiembre anterior', encoding='utf-8')
    return tmp_path


def contenido():
    return {'periodo': {'anio': 2026, 'mes': 9}, 'empleados': [
        {'nombre': 'Persona Uno', 'turnos': {
            (date(2026, 8, 31) + timedelta(days=i)).isoformat(): 'AM' for i in range(35)}}]}


def secreto(monkeypatch, base):
    monkeypatch.setenv(base_septiembre.VARIABLE,
                       base64.b64encode(json.dumps(base).encode()).decode())


def test_actualiza_solo_septiembre(datos, monkeypatch):
    base = contenido()
    secreto(monkeypatch, base)
    assert base_septiembre.aplicar(datos)
    assert json.loads((datos / 'base_septiembre_2026.json').read_text()) == base
    assert (datos / 'base_agosto_2026.json').read_text() == 'agosto original'
    assert (datos / 'empleados_iniciales.csv').read_text() == 'nombre\nPersona Uno\n'


def test_sin_actualizacion_conserva_la_base_original(datos, monkeypatch):
    monkeypatch.delenv(base_septiembre.VARIABLE, raising=False)
    assert not base_septiembre.aplicar(datos)
    assert (datos / 'base_septiembre_2026.json').read_text() == 'septiembre anterior'


@pytest.mark.parametrize('fallo', ['mes', 'nombre', 'duplicada', 'fecha', 'turno', 'vacio'])
def test_rechaza_actualizaciones_incompatibles_sin_escribir(datos, monkeypatch, fallo):
    base = contenido()
    if fallo == 'mes':
        base['periodo']['mes'] = 10
    elif fallo == 'nombre':
        base['empleados'][0]['nombre'] = 'Otra Persona'
    elif fallo == 'duplicada':
        base['empleados'].append(base['empleados'][0])
    elif fallo == 'fecha':
        base['empleados'][0]['turnos'].pop('2026-09-01')
    elif fallo == 'turno':
        base['empleados'][0]['turnos']['2026-09-01'] = 'INVENTADO'
    else:
        base['empleados'] = []
    secreto(monkeypatch, base)
    with pytest.raises(SystemExit):
        base_septiembre.aplicar(datos)
    assert (datos / 'base_septiembre_2026.json').read_text() == 'septiembre anterior'


def test_rechaza_secreto_corrupto(datos, monkeypatch):
    monkeypatch.setenv(base_septiembre.VARIABLE, 'esto no es base64')
    with pytest.raises(SystemExit, match='JSON en base64 válido'):
        base_septiembre.aplicar(datos)
