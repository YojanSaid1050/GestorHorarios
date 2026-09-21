"""Prueba de escritorio real en un proceso y una carpeta de datos desechables."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


def comprobar() -> int:
    if sys.platform != 'win32':
        print('La comprobación de WebView2 necesita Windows.')
        return 2
    from gestor import rutas

    rutas.RAIZ_DATOS.mkdir(parents=True, exist_ok=True)
    destino = rutas.RAIZ_DATOS / 'comprobacion-ventana.json'
    with tempfile.TemporaryDirectory(prefix='gestor-ventana-') as temporal:
        orden = ([sys.executable] if getattr(sys, 'frozen', False)
                 else [sys.executable, '-m', 'gestor.principal'])
        entorno = {**os.environ, 'GESTOR_DATOS': temporal}
        estado = {'ok': False, 'error': 'La ventana no dejó resultado.'}
        codigo = 1
        try:
            hijo = subprocess.run(  # noqa: S603
                [*orden, '--sonda-ventana'], env=entorno, timeout=75,
                capture_output=True, text=True)
            codigo = hijo.returncode
            resultado = Path(temporal) / 'sonda-ventana.json'
            if resultado.is_file():
                estado = json.loads(resultado.read_text(encoding='utf-8'))
        except subprocess.TimeoutExpired:
            estado['error'] = 'La ventana no terminó en 75 s.'
        finally:
            # El ejecutable no tiene consola: conservar el resultado antes de
            # borrar la carpeta temporal, incluso cuando el hijo se bloquea.
            estado['codigo_proceso'] = codigo
            destino.write_text(json.dumps(estado, ensure_ascii=False, indent=2),
                               encoding='utf-8')
            registro = Path(temporal) / 'registro.log'
            if registro.is_file():
                (rutas.RAIZ_DATOS / 'comprobacion-ventana.log').write_bytes(
                    registro.read_bytes())
            print(destino.read_text(encoding='utf-8'))
        return 0 if codigo == 0 and estado.get('ok') is True else 1


def ejecutar() -> int:
    import webview

    from gestor import diagnostico_ventana, escritorio, rutas
    from gestor.servidor_local import ServidorLocal

    estado = {'ok': False, 'error': 'La ventana no terminó su carga.'}
    terminado = threading.Event()

    with ServidorLocal() as servidor:
        ventana, _ = escritorio.crear(servidor.url, 'Comprobando Gestor de Horarios', segura=True)
        diagnostico_ventana.conectar(ventana)

        def recibir(datos):
            if isinstance(datos, dict):
                estado.update(datos)
            terminado.set()

        def probar():
            try:
                if not ventana.events.loaded.wait(25):
                    raise RuntimeError('No terminó la inyección de la API de ventana.')
                ventana.evaluate_js('''(async () => {
                    const r = await fetch('/api/auth/cuentas-login');
                    if (!r.ok) throw new Error('HTTP ' + r.status);
                    const cuentas = await r.json();
                    const barra = await window.pywebview.api.barra_propia();
                    for (let i = 0; i < 100; i++) {
                        const select = document.getElementById('login-usuario');
                        if (select?.options[0]?.value) {
                            return {ok: cuentas.cuentas.length > 0, error: null,
                                    cuentas: cuentas.cuentas.length, barra: barra};
                        }
                        await new Promise(r => setTimeout(r, 100));
                    }
                    return {ok: false, error: 'El selector sigue sin cuentas.'};
                })().catch(e => ({ok: false, error: String(e)}))''', callback=recibir)
                if not terminado.wait(20):
                    raise RuntimeError('El JavaScript o el puente no devolvieron el resultado.')
            except Exception as exc:  # noqa: BLE001
                estado.update(ok=False, error=str(exc))
            finally:
                (rutas.RAIZ_DATOS / 'sonda-ventana.json').write_text(
                    json.dumps(estado, ensure_ascii=False), encoding='utf-8')
                ventana.destroy()

        webview.start(probar, gui='edgechromium')
    return 0 if estado['ok'] else 1
