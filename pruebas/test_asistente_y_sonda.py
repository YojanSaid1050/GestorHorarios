"""Conservar diagnóstico y motor de instalación cuando una etapa falla."""
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from gestor import rutas, sonda_ventana


@pytest.mark.parametrize('bloqueado', [False, True])
def test_sonda_conserva_resultado_fuera_de_la_carpeta_temporal(tmp_path, monkeypatch, bloqueado):
    monkeypatch.setattr(sonda_ventana.sys, 'platform', 'win32')
    monkeypatch.setattr(rutas, 'RAIZ_DATOS', tmp_path / 'datos')

    def ejecutar(orden, **opciones):
        temporal = Path(opciones['env']['GESTOR_DATOS'])
        (temporal / 'registro.log').write_text('registro de diagnóstico', encoding='utf-8')
        if bloqueado:
            raise subprocess.TimeoutExpired(orden, 75)
        (temporal / 'sonda-ventana.json').write_text('{"ok": true}', encoding='utf-8')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sonda_ventana.subprocess, 'run', ejecutar)
    assert sonda_ventana.comprobar() == (1 if bloqueado else 0)
    resultado = json.loads((rutas.RAIZ_DATOS / 'comprobacion-ventana.json').read_text())
    assert resultado['ok'] is not bloqueado
    assert (rutas.RAIZ_DATOS / 'comprobacion-ventana.log').is_file()


@pytest.mark.parametrize('resultado', ['correcto', 'error', 'sin_archivo'])
def test_solo_se_retira_el_motor_tras_compilar_el_asistente(tmp_path, monkeypatch, resultado):
    archivo = Path(__file__).resolve().parents[1] / 'empaquetado' / 'construir.py'
    spec = importlib.util.spec_from_file_location('construir_prueba', archivo)
    construir = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(construir)
    compilador = tmp_path / 'ISCC.exe'
    compilador.touch()
    base = tmp_path / 'GestorHorarios-win-Setup.exe'
    base.write_bytes(b'motor')
    paquete = tmp_path / 'actualizacion.nupkg'
    paquete.write_bytes(b'actualizacion')
    monkeypatch.setattr(construir, 'PAQUETES', tmp_path)
    monkeypatch.setattr(construir.shutil, 'which', lambda _: str(compilador))

    def compilar(_):
        if resultado == 'error':
            raise SystemExit('falló ISCC')
        if resultado == 'correcto':
            (tmp_path / f'GestorHorarios-Instalar-{construir.version.VERSION}.exe').touch()

    monkeypatch.setattr(construir, 'correr', compilar)
    if resultado == 'correcto':
        construir.construir_asistente()
        assert not base.exists()
    else:
        with pytest.raises(SystemExit):
            construir.construir_asistente()
        assert base.read_bytes() == b'motor'
    assert paquete.read_bytes() == b'actualizacion'
