"""Regresiones de carga y credenciales, usando la página y Chromium reales."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from playwright.sync_api import sync_playwright  # noqa: E402

from qa.navegador import abrir  # noqa: E402
from qa.servidor import Servidor  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix='gestor-arranque-qa-') as carpeta:  # noqa: SIM117
        with Servidor(carpeta) as servidor, sync_playwright() as guion:
            navegador = abrir(guion)
            pagina = navegador.new_page()
            pagina.add_init_script('''
                localStorage.setItem('gestorhorarios_claves_recordadas', '{"admin":"antigua"}');
                const original = window.fetch.bind(window);
                window.fetch = (url, opciones) => {
                    if (/configuracion\\/(modo|tema)-app/.test(String(url))) {
                        return new Promise((resolve, reject) => {
                            opciones?.signal?.addEventListener('abort', () =>
                                reject(new DOMException('Tiempo agotado', 'AbortError')));
                        });
                    }
                    return original(url, opciones);
                };
            ''')
            pagina.goto(servidor.base)
            pagina.wait_for_function(
                "document.querySelector('#login-usuario').options[0]?.value", timeout=2500)
            print('[ok] Las cuentas cargan aunque la apariencia no responda.')
            assert pagina.evaluate(
                "localStorage.getItem('gestorhorarios_claves_recordadas')") is None
            print('[ok] Se elimina el respaldo antiguo de claves en texto legible.')
            pagina.wait_for_timeout(300)
            resultado = pagina.evaluate('''async () => {
                const original = fetch;
                let abortado = false;
                window.fetch = (url, opciones) => Promise.resolve({ok: true,
                    json: () => new Promise((resolve, reject) => {
                        opciones.signal.addEventListener('abort', () => {
                            abortado = true; reject(new DOMException('Abortado', 'AbortError'));
                        });
                    })});
                try { await leerAlArrancar('/cuerpo-bloqueado', 50); return false; }
                catch (_) { return abortado; }
                finally { window.fetch = original; }
            }''')
            assert resultado
            print('[ok] El límite también cancela una respuesta cuyo cuerpo se bloquea.')
            assert pagina.evaluate('''async () => {
                window.pywebview = {api: {leer_clave: () => new Promise(() => {}),
                    guardar_clave: () => new Promise(() => {}),
                    olvidar_clave: () => new Promise(() => {})}};
                document.querySelector('#login-recordar').checked = true;
                try { await guardarClaveRecordada('admin', 'prueba'); return false; }
                catch (error) { return error.message.includes('3 segundos'); }
            }''')
            print('[ok] Recordar una clave no espera indefinidamente al puente.')
            assert pagina.evaluate('''async () => {
                let devolver;
                window.pywebview.api.leer_clave = () => new Promise(r => { devolver = r; });
                const campo = document.querySelector('#login-password');
                campo.dataset.escrito = '';
                const tarea = rellenarClaveRecordada();
                await new Promise(r => setTimeout(r, 0));
                campo.value = 'escrita-por-la-persona'; campo.dataset.escrito = '1';
                devolver({ok: true, recordada: true, password: 'antigua'});
                await tarea;
                return campo.value === 'escrita-por-la-persona';
            }''')
            print('[ok] Una respuesta tardía no sobrescribe lo que escribe la persona.')
            assert pagina.evaluate('''async () => {
                let devolver;
                window.pywebview.api.leer_clave = () => new Promise(r => { devolver = r; });
                const campo = document.querySelector('#login-password');
                const usuario = document.querySelector('#login-usuario');
                usuario.value = 'katerine'; campo.value = ''; campo.dataset.escrito = '';
                const tarea = rellenarClaveRecordada();
                await new Promise(r => setTimeout(r, 0));
                usuario.value = 'admin';
                devolver({ok: true, recordada: true, password: 'otra-cuenta'});
                await tarea;
                return campo.value === '';
            }''')
            print('[ok] Una clave tardía no se rellena en otra cuenta.')
            navegador.close()
    print('6/6 comprobaciones correctas')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
