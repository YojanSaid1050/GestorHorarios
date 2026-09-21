"""Regresión del instalador que intentó reemplazar C:\\Windows."""
import json
from pathlib import Path

import pytest

from empaquetado import comprobar_instalador, motor_prueba

RAIZ = Path(__file__).resolve().parents[1]


def test_inno_conserva_la_pagina_y_la_constante_de_destino():
    # CreateAppDir=no hace que Inno oculte wpSelectDir y resuelva {app} a {win}.
    texto = (RAIZ / 'empaquetado' / 'asistente.iss').read_text(encoding='utf-8-sig')
    setup = texto.split('[Setup]', 1)[1].split('[Languages]', 1)[0]
    opciones = dict(linea.split('=', 1) for linea in setup.splitlines()
                    if '=' in linea and not linea.startswith(';'))
    assert opciones['CreateAppDir'].lower() == 'yes'
    assert opciones['DisableDirPage'].lower() == 'no'
    assert opciones['PrivilegesRequired'].lower() == 'lowest'


@pytest.mark.parametrize('ubicacion', ['base', 'fuera', 'dentro'])
def test_doble_del_motor_solo_escribe_en_su_temporal(tmp_path, monkeypatch, ubicacion):
    base = tmp_path / 'permitido'
    base.mkdir()
    destino = {'base': base, 'fuera': tmp_path / 'ajeno',
               'dentro': base / 'Carpeta á con espacios'}[ubicacion]
    llamada = tmp_path / 'llamada.json'
    monkeypatch.setenv('GESTOR_PRUEBA_RAIZ', str(base))
    monkeypatch.setenv('GESTOR_PRUEBA_LLAMADA', str(llamada))
    monkeypatch.setattr('sys.argv', ['motor', '--silent', '--installto', str(destino)])
    assert motor_prueba.main() == (0 if ubicacion == 'dentro' else 91)
    assert json.loads(llamada.read_text())['destino'] == str(destino.resolve())
    assert (destino / 'current' / 'GestorHorarios.exe').exists() is (ubicacion == 'dentro')
    if ubicacion == 'fuera':
        assert not destino.exists()


def test_prueba_nativa_no_instala_en_un_equipo_de_usuario(monkeypatch):
    monkeypatch.setattr(comprobar_instalador.sys, 'platform', 'win32')
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    monkeypatch.setattr(comprobar_instalador, 'probar',
                        lambda *_: pytest.fail('No debe instalar fuera del runner.'))
    assert comprobar_instalador.main() == 2


@pytest.mark.parametrize('nombre', ['asistente.iss', 'destino_seguro.iss'])
def test_los_comentarios_del_codigo_usan_sintaxis_pascal(nombre):
    texto = (RAIZ / 'empaquetado' / nombre).read_text(encoding='utf-8-sig')
    if nombre == 'asistente.iss':
        texto = texto.split('[Code]', 1)[1]
    incorrectas = [numero for numero, linea in enumerate(texto.splitlines(), 1)
                   if linea.lstrip().startswith(';')]
    assert not incorrectas, (
        f'{nombre}: comentarios de Inno dentro de Pascal en líneas {incorrectas}; usar //')
