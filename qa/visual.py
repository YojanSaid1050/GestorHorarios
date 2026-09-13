# -*- coding: utf-8 -*-
"""Que la aplicación se lea, en claro y en oscuro, en todas sus pantallas.

Un fallo de color no rompe nada: simplemente deja un texto del mismo color que
su fondo, y quien lo sufre cree que la sección está vacía. No sale en ningún
registro y ninguna prueba de Python lo ve.

Lo que se mide aquí es el **contraste real que calcula el navegador**, elemento
por elemento, con la fórmula de la WCAG. Se recorre cada pestaña en cada modo y
se listan los elementos que no llegan al mínimo legible.

También se comprueba lo que es puramente estructural y falla igual de callado:
que ninguna tabla desborde su caja a lo ancho —eso deja columnas fuera de la
pantalla sin decirlo— y que ningún texto se salga de su contenedor.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from qa.servidor import Servidor, entrar_como_admin  # noqa: E402
from qa.uso import App  # noqa: E402

CAPTURAS = Path('/tmp/qa_visual')
NAVEGADOR = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

PESTANAS = ['personal', 'solicitudes', 'requerimientos', 'horario', 'modificar',
            'validacion', 'historial', 'configuracion']

#: El mínimo de la WCAG para texto normal. Es el objetivo, y lo que queda por
#: debajo se lista.
CONTRASTE_MINIMO = 4.5
#: El texto grande aguanta menos contraste sin dejar de leerse.
CONTRASTE_MINIMO_GRANDE = 3.0
#: Por debajo de esto el texto **no se lee**: es del color de su fondo o casi.
#: Eso sí es un fallo, y es lo único que hace fallar esta suite. Entre este
#: número y el de la WCAG hay un aviso: se ve, pero no tan bien como debería, y
#: quien decide si eso se cambia es quien eligió los colores de la aplicación,
#: no una herramienta.
CONTRASTE_ILEGIBLE = 2.5

MEDIR_CONTRASTE = """
() => {
  const luminancia = (c) => {
    const [r, g, b] = c.map(v => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const leer = (txt) => {
    const m = String(txt || '').match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x));
    return {rgb: p.slice(0, 3), alfa: p.length > 3 ? p[3] : 1};
  };
  // El fondo de verdad es el del primer antepasado que pinta algo: un elemento
  // transparente hereda el color de detrás, y compararlo contra «transparente»
  // daba contrastes inventados.
  //
  // Si por el camino aparece un degradado, se devuelve `null`: sobre un
  // degradado no hay **un** color de fondo, y medir contra el `background-color`
  // que hay debajo da un número que no significa nada. Midiéndolo así, esta
  // misma herramienta denunciaba la cabecera de la aplicación como ilegible con
  // un 1.1:1 cuando en realidad es texto blanco sobre morado, que se lee
  // perfectamente. Un medidor que inventa fallos es peor que no tenerlo: se
  // aprende a ignorar lo que dice.
  const fondoReal = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const estilo = getComputedStyle(n);
      if (estilo.backgroundImage && estilo.backgroundImage !== 'none') return null;
      const c = leer(estilo.backgroundColor);
      if (c && c.alfa > 0.5) return c.rgb;
      n = n.parentElement;
    }
    const c = leer(getComputedStyle(document.body).backgroundColor);
    return c ? c.rgb : [255, 255, 255];
  };
  const malos = [];
  let sinMedir = 0;
  const visto = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;
    const propio = [...el.childNodes]
      .filter(n => n.nodeType === 3 && n.textContent.trim().length > 1)
      .map(n => n.textContent.trim()).join(' ');
    if (!propio) continue;
    const estilo = getComputedStyle(el);
    if (estilo.visibility === 'hidden' || parseFloat(estilo.opacity) < 0.15) continue;
    const frente = leer(estilo.color);
    if (!frente || frente.alfa < 0.5) continue;
    const detras = fondoReal(el);
    if (!detras) { sinMedir += 1; continue; }
    const a = luminancia(frente.rgb), b = luminancia(detras);
    // Se redondea **antes** de comparar, no solo para enseñarlo. Comparando el
    // número crudo, un 4,4999 se listaba como «por debajo de 4,5» y en el
    // informe salía «4.5:1», que es exactamente el número que se pide. Un aviso
    // que se contradice a sí mismo se deja de leer.
    const razon = Math.round(
      ((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) * 100) / 100;
    const tam = parseFloat(estilo.fontSize) || 16;
    const grande = tam >= 24 || (tam >= 18.66 && parseInt(estilo.fontWeight, 10) >= 700);
    const minimo = grande ? %(grande)s : %(normal)s;
    if (razon < minimo) {
      const clave = propio.slice(0, 40) + '|' + estilo.color;
      if (visto.has(clave)) continue;
      visto.add(clave);
      malos.push({texto: propio.slice(0, 60), razon: razon,
                  color: estilo.color, fondo: 'rgb(' + detras.join(',') + ')',
                  ilegible: razon < %(ilegible)s,
                  etiqueta: el.tagName.toLowerCase(), clase: el.className});
    }
  }
  return {flojos: malos, ilegibles: malos.filter(x => x.ilegible),
          medidos: visto.size, sin_medir: sinMedir};
}
""" % {'grande': CONTRASTE_MINIMO_GRANDE, 'normal': CONTRASTE_MINIMO,
       'ilegible': CONTRASTE_ILEGIBLE}

DESBORDES = """
() => {
  const malos = [];
  for (const el of document.querySelectorAll('table, .card, .tab.active')) {
    if (!el.offsetParent) continue;
    const caja = el.parentElement;
    if (!caja) continue;
    const desborde = el.scrollWidth - caja.clientWidth;
    const scrollable = ['auto', 'scroll'].includes(getComputedStyle(caja).overflowX);
    if (desborde > 4 && !scrollable) {
      malos.push({etiqueta: el.tagName.toLowerCase(), clase: String(el.className).slice(0, 60),
                  sobra: desborde});
    }
  }
  return malos;
}
"""


def _linea(x) -> str:
    return (f'{x["razon"]}:1  «{x["texto"]}»  '
            f'({x["etiqueta"]}.{str(x["clase"])[:30]}  {x["color"]} sobre {x["fondo"]})')


class Acta:
    def __init__(self):
        self.pasos: list[tuple[bool, str, str]] = []
        #: Lo que se ve pero no llega al contraste recomendado. No hace fallar
        #: nada: es una lista para que quien eligió los colores decida.
        self.avisos: list[str] = []

    def anotar(self, texto: str) -> None:
        if texto not in self.avisos:
            self.avisos.append(texto)

    def comprobar(self, ok, que, detalle=''):
        self.pasos.append((bool(ok), que, str(detalle)))
        print(f'  [{"ok  " if ok else "FALLA"}] {que}'
              + (f'\n         {detalle}' if not ok and detalle else ''), flush=True)
        return bool(ok)

    def resumen(self) -> int:
        buenos = sum(1 for ok, _, _ in self.pasos if ok)
        print(f'\n{buenos}/{len(self.pasos)} comprobaciones correctas')
        malos = [(q, d) for ok, q, d in self.pasos if not ok]
        if malos:
            print('\nLo que falló:')
            for que, detalle in malos:
                print(f'  · {que}\n      {detalle}')
        if self.avisos:
            print(f'\n{len(self.avisos)} textos por debajo del contraste recomendado '
                  '(se leen, pero no tan bien como deberían):')
            for aviso in self.avisos[:25]:
                print(f'  · {aviso}')
            print('  No hacen fallar nada: quien decide si se cambian es quien '
                  'eligió los colores.')
        return 0 if not malos else 1


def _poner_modo(app, modo: str) -> None:
    app.pag.evaluate(
        "(m)=>{if (typeof aplicarModoApp === 'function') aplicarModoApp(m);}", modo)
    app.pag.wait_for_timeout(700)


def _revisar(app, acta, modo: str) -> None:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for pestana in PESTANAS:
        app.ir(pestana)
        app.pag.wait_for_timeout(500)
        medida = app.pag.evaluate(MEDIR_CONTRASTE)
        acta.comprobar(
            not medida['ilegibles'], f'{modo} · «{pestana}» se lee entera',
            '\n         '.join(_linea(x) for x in medida['ilegibles'][:6]))
        for flojo in medida['flojos']:
            if not flojo['ilegible']:
                acta.anotar(f'{modo} · «{pestana}»: {_linea(flojo)}')
        desbordes = app.pag.evaluate(DESBORDES)
        acta.comprobar(not desbordes, f'{modo} · «{pestana}» no se sale de la caja',
                       desbordes[:3])
        app.pag.screenshot(path=str(CAPTURAS / f'{modo}_{pestana}.png'), full_page=True)


def main() -> int:
    from playwright.sync_api import sync_playwright

    acta = Acta()
    with Servidor('/tmp/qa_visual_datos') as servidor:
        cabeceras = entrar_como_admin(servidor)
        # Un mes generado, para que las pantallas tengan datos de verdad que
        # enseñar: una tabla vacía no revela ningún problema de color.
        servidor.pedir('/api/horarios/generar', 'POST', {'mes': 10, 'anio': 2026},
                       cabeceras)
        print(f'Servidor en {servidor.base}\n')
        with sync_playwright() as guion:
            navegador = guion.chromium.launch(executable_path=NAVEGADOR,
                                              args=['--no-sandbox'])
            pagina = navegador.new_page(viewport={'width': 1600, 'height': 1000})
            app = App(pagina)
            app.entrar(servidor.base)
            for modo in ('claro', 'oscuro'):
                print(f'\n— en modo {modo}')
                _poner_modo(app, modo)
                _revisar(app, acta, modo)
            navegador.close()

    print(f'\nCapturas en {CAPTURAS}')
    return acta.resumen()


if __name__ == '__main__':
    raise SystemExit(main())
