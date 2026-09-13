# -*- coding: utf-8 -*-
"""Mirar de cerca una pantalla concreta cuando algo se atasca.

No comprueba nada: solo abre la aplicación, va a donde se le diga y cuenta qué
hay. Sirve para lo que ninguna traza de Python resuelve —«el recorrido se para
aquí y no sé por qué»— y para ver el estado de un botón sin adivinarlo.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from qa.servidor import Servidor  # noqa: E402
from qa.uso import App  # noqa: E402

NAVEGADOR = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
CAPTURAS = Path('/tmp/qa_capturas')


def estado_del_boton(app, identificador: str) -> dict | None:
    return app.pag.evaluate(
        "(id)=>{const b=document.getElementById(id);"
        " return b ? {texto:b.innerText.trim(), apagado:b.disabled,"
        "             invisible:b.offsetParent===null} : null;}", identificador)


def main() -> int:
    from playwright.sync_api import sync_playwright

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    with Servidor('/tmp/qa_diagnostico') as servidor:
        print(f'servidor: {servidor.base}', flush=True)
        with sync_playwright() as guion:
            navegador = guion.chromium.launch(executable_path=NAVEGADOR,
                                              args=['--no-sandbox'])
            pagina = navegador.new_page(viewport={'width': 1600, 'height': 1000})
            app = App(pagina)
            print('entrar:', app.entrar(servidor.base), flush=True)

            app.ir('horario')
            print('periodo que trae:', app.valor('#periodo'), flush=True)
            print('hay selector de fecha:',
                  bool(pagina.query_selector('#periodo + .date-select-group')), flush=True)
            app.periodo(2026, 10)
            print('periodo tras cambiarlo:', app.valor('#periodo'), flush=True)
            print('botón generar:', estado_del_boton(app, 'generar'), flush=True)
            print('modales abiertos:', app.modales(), flush=True)
            print('aviso de estado:', app.alerta('#estado-periodo')[:200], flush=True)
            print('errores de javascript:', app.errores_js[:5], flush=True)
            pagina.screenshot(path=str(CAPTURAS / 'diagnostico.png'), full_page=True)
            navegador.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
