# -*- coding: utf-8 -*-
"""La barra de título propia, conducida en un navegador de verdad.

Aquí no hay Windows ni escritorio, así que lo que **de verdad** hace una ventana
sin marco —moverse, ajustarse a los bordes, cambiar de tamaño de verdad— no se
puede comprobar y está en `empaquetado/EN_WINDOWS.md`, escrito para hacerlo a
mano.

Lo que sí se puede comprobar es todo lo demás, que es casi todo: se finge un
`window.pywebview` con la misma interfaz que el puente de Python y se conduce la
barra con el ratón. Así se ve si la barra aparece, si dice el nombre y la versión
correctos, si cada botón llama a lo que tiene que llamar, si el doble clic
maximiza, si los tiradores piden los tamaños correctos con el borde correcto, y
—lo más importante de todo— si la barra se puede usar **en la pantalla de
acceso**: una ventana sin marco cuya barra apareciera solo después de entrar
sería una ventana que no se puede cerrar ni mover hasta haber escrito la
contraseña.

Lo que se finge es solo el puente. La barra, el CSS, el orden de los avisos y la
lógica del JavaScript son los de verdad.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from qa.servidor import Servidor, entrar_como_admin  # noqa: E402
from qa.uso import App  # noqa: E402

NAVEGADOR = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
CAPTURAS = Path('/tmp/qa_ventana')

#: El puente de mentira. Tiene los mismos nombres que `gestor/escritorio.py` y
#: apunta todo lo que le piden, para poder comprobarlo después desde Python.
#: `barra_propia` contesta que sí, que es el caso que importa: la ventana se
#: abrió sin marco y la pantalla tiene que ponerle la barra.
PUENTE_DE_MENTIRA = """
window.__llamadas = [];
window.pywebview = {
  api: {
    barra_propia: () => { window.__llamadas.push(['barra_propia']); return Promise.resolve(true); },
    minimizar: () => { window.__llamadas.push(['minimizar']); return Promise.resolve(true); },
    cerrar: () => { window.__llamadas.push(['cerrar']); return Promise.resolve(true); },
    maximizar_o_restaurar: () => {
      window.__maximizada = !window.__maximizada;
      window.__llamadas.push(['maximizar_o_restaurar']);
      return Promise.resolve(true);
    },
    esta_maximizada: () => Promise.resolve(!!window.__maximizada),
    redimensionar: (ancho, alto, borde) => {
      window.__llamadas.push(['redimensionar', ancho, alto, borde]);
      return Promise.resolve(true);
    },
  },
};
"""


class Acta:
    def __init__(self):
        self.pasos: list[tuple[bool, str, str]] = []

    def comprobar(self, ok, que, detalle='') -> bool:
        self.pasos.append((bool(ok), que, str(detalle)))
        print(f'  [{"ok  " if ok else "FALLA"}] {que}'
              + (f'   -> {detalle}' if not ok and detalle else ''), flush=True)
        return bool(ok)

    def resumen(self) -> int:
        buenos = sum(1 for ok, _, _ in self.pasos if ok)
        print(f'\n{"=" * 72}\n{buenos}/{len(self.pasos)} comprobaciones correctas')
        malos = [(q, d) for ok, q, d in self.pasos if not ok]
        if malos:
            print('\nLo que falló:')
            for que, detalle in malos:
                print(f'  · {que}' + (f'   -> {detalle}' if detalle else ''))
        return 0 if not malos else 1


def _llamadas(pag, nombre=None) -> list:
    todas = pag.evaluate('() => window.__llamadas || []')
    return [x for x in todas if nombre is None or x[0] == nombre]


def _limpiar(pag) -> None:
    pag.evaluate('() => { window.__llamadas = []; }')


def _visible(pag, selector: str) -> bool:
    return bool(pag.evaluate(
        """(sel) => {
             const e = document.querySelector(sel);
             if (!e) return false;
             const c = getComputedStyle(e);
             return c.display !== 'none' && c.visibility !== 'hidden'
                    && e.getBoundingClientRect().height > 0;
           }""", selector))


# ------------------------------------------------- antes de iniciar sesión

def antes_de_entrar(app: App, acta: Acta) -> None:
    """La barra tiene que estar y tiene que poder pulsarse con el acceso echado.

    Es el caso que más importa y el que más fácil se rompe: la pantalla de acceso
    es una capa fija por encima de todo (`z-index: 20000`) y desenfoca lo que hay
    detrás. Una barra que se quedara debajo dejaría la ventana sin forma de
    moverse ni de cerrarse hasta después de escribir la contraseña.
    """
    pag = app.pag
    acta.comprobar(pag.evaluate("() => document.body.classList.contains('auth-locked')"),
                   'se empieza con el acceso echado, que es el caso difícil')
    acta.comprobar(_visible(pag, '#barra-ventana'),
                   'la barra de la ventana se ve antes de iniciar sesión')
    acta.comprobar(_visible(pag, '#tiradores-ventana span[data-borde="se"]'),
                   'y los tiradores del borde también están puestos')

    # Lo que decide si se puede pulsar no es que se vea, sino qué hay encima: se
    # le pregunta al navegador qué recibiría el clic en el centro del botón.
    encima = pag.evaluate(
        """() => {
             const b = document.getElementById('ventana-cerrar').getBoundingClientRect();
             const e = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2);
             return e ? (e.closest('#barra-ventana') ? 'la barra' : e.id || e.className) : 'nada';
           }""")
    acta.comprobar(encima == 'la barra',
                   'el botón de cerrar recibe el clic, no la pantalla de acceso',
                   f'quien lo recibe es «{encima}»')

    borroso = pag.evaluate(
        "() => getComputedStyle(document.getElementById('barra-ventana')).filter")
    acta.comprobar(borroso in ('none', ''),
                   'y la barra no queda desenfocada con el resto de la pantalla',
                   f'filter = {borroso}')

    _limpiar(pag)
    pag.evaluate("() => document.getElementById('ventana-minimizar').click()")
    pag.wait_for_timeout(300)
    acta.comprobar(bool(_llamadas(pag, 'minimizar')),
                   'minimizar funciona sin haber entrado')


# ---------------------------------------------------- ya dentro del programa

def el_titulo(app: App, acta: Acta) -> None:
    """La barra dice el nombre y la versión, que llegan del servidor."""
    pag = app.pag
    titulo, enLaBarra = pag.evaluate(
        "() => [document.title, document.getElementById('barra-ventana-titulo').textContent]")
    acta.comprobar(enLaBarra.strip() == titulo.strip(),
                   'la barra dice lo mismo que el título de la ventana',
                   f'barra «{enLaBarra}» contra título «{titulo}»')
    acta.comprobar('Gestor' in enLaBarra and any(c.isdigit() for c in enLaBarra),
                   'y trae el nombre y la versión, no el texto del archivo',
                   enLaBarra)


def los_tres_botones(app: App, acta: Acta) -> None:
    pag = app.pag
    _limpiar(pag)
    pag.evaluate("() => document.getElementById('ventana-minimizar').click()")
    pag.wait_for_timeout(250)
    acta.comprobar([x[0] for x in _llamadas(pag)] == ['minimizar'],
                   'el botón de minimizar llama a minimizar y a nada más',
                   str(_llamadas(pag)))

    _limpiar(pag)
    pag.evaluate("() => document.getElementById('ventana-cerrar').click()")
    pag.wait_for_timeout(250)
    acta.comprobar([x[0] for x in _llamadas(pag)] == ['cerrar'],
                   'el de cerrar llama a cerrar',
                   str(_llamadas(pag)))


def el_boton_del_medio(app: App, acta: Acta) -> None:
    """Maximizar y restaurar son el mismo botón y tiene que ir y volver.

    Y tiene que **enseñar** en cuál de los dos estados está: el icono de
    maximizar sobre una ventana ya maximizada es el que hace que alguien pulse
    dos veces creyendo que no funcionó.
    """
    pag = app.pag
    _limpiar(pag)
    pag.evaluate("() => document.getElementById('ventana-maximizar').click()")
    pag.wait_for_timeout(400)
    acta.comprobar(pag.evaluate(
        "() => document.getElementById('barra-ventana').classList.contains('maximizada')"),
        'al maximizar, la barra enseña el icono de restaurar')
    acta.comprobar(pag.evaluate(
        "() => document.getElementById('tiradores-ventana').classList.contains('quieta')"),
        'y los tiradores se retiran: no hay bordes que estirar')
    icono = pag.evaluate(
        """() => {
             const b = document.getElementById('ventana-maximizar');
             return [getComputedStyle(b.querySelector('.icono-maximizar')).display,
                     getComputedStyle(b.querySelector('.icono-restaurar')).display];
           }""")
    acta.comprobar(icono[0] == 'none' and icono[1] != 'none',
                   'y se ve un solo icono, el que toca', str(icono))

    pag.evaluate("() => document.getElementById('ventana-maximizar').click()")
    pag.wait_for_timeout(400)
    acta.comprobar(not pag.evaluate(
        "() => document.getElementById('barra-ventana').classList.contains('maximizada')"),
        'y el segundo clic restaura, no se queda pulsado')
    acta.comprobar(len(_llamadas(pag, 'maximizar_o_restaurar')) == 2,
                   'los dos clics llegaron a la ventana')

    _limpiar(pag)
    pag.dispatch_event('#barra-ventana-arrastre', 'dblclick')
    pag.wait_for_timeout(400)
    acta.comprobar(bool(_llamadas(pag, 'maximizar_o_restaurar')),
                   'el doble clic en la barra maximiza, como en cualquier ventana')
    # Se deja como estaba para no dejar la ventana maximizada al resto.
    pag.evaluate("() => document.getElementById('ventana-maximizar').click()")
    pag.wait_for_timeout(300)


def se_arrastra_solo_por_la_barra(app: App, acta: Acta) -> None:
    """Quien mueve la ventana es pywebview, mirando una clase en el HTML.

    Aquí no se puede mover nada, así que lo que se comprueba es lo que decide si
    se moverá: que la clase esté en la zona del título y **solo** ahí. Puesta en
    toda la barra, los botones moverían la ventana en vez de pulsarse; puesta en
    el `body`, la aplicación entera se movería al intentar seleccionar un texto.
    """
    pag = app.pag
    zonas = pag.evaluate(
        """() => [...document.querySelectorAll('.pywebview-drag-region')]
                 .map(e => e.id || e.className)""")
    acta.comprobar(zonas == ['barra-ventana-arrastre'],
                   'solo la zona del título arrastra la ventana', str(zonas))
    acta.comprobar(pag.evaluate(
        """() => {
             const b = document.getElementById('ventana-cerrar');
             return !b.closest('.pywebview-drag-region');
           }"""),
        'y los botones quedan fuera de esa zona, así que se pulsan')


def los_tiradores(app: App, acta: Acta) -> None:
    """Estirar por cada borde pide el tamaño correcto y nombra el borde correcto.

    El borde importa tanto como el tamaño: es lo que le dice a Python qué lado
    tiene que dejar quieto. Sin eso, estirar por la izquierda movería la ventana
    hacia la izquierda en vez de estrecharla.
    """
    pag = app.pag
    # El mismo punto de partida que usa la pantalla, o la comparación no
    # significaría nada.
    ancho, alto = pag.evaluate(
        '() => [window.outerWidth > 200 ? window.outerWidth : window.innerWidth,'
        ' window.outerHeight > 200 ? window.outerHeight : window.innerHeight]')

    for borde, (dx, dy), espera in (
            ('se', (120, 90), 'más ancha y más alta'),
            ('o', (-140, 0), 'más ancha al tirar hacia la izquierda'),
            ('n', (0, -110), 'más alta al tirar hacia arriba'),
            ('e', (-200, 0), 'más estrecha al tirar hacia dentro')):
        _limpiar(pag)
        caja = pag.evaluate(
            """(b) => {
                 const r = document.querySelector(`#tiradores-ventana [data-borde="${b}"]`)
                     .getBoundingClientRect();
                 return [r.x + r.width / 2, r.y + r.height / 2];
               }""", borde)
        pag.mouse.move(caja[0], caja[1])
        pag.mouse.down()
        pag.mouse.move(caja[0] + dx, caja[1] + dy, steps=6)
        pag.wait_for_timeout(350)
        pag.mouse.up()
        pag.wait_for_timeout(200)

        pedidas = _llamadas(pag, 'redimensionar')
        if not acta.comprobar(bool(pedidas),
                              f'arrastrar el tirador «{borde}» redimensiona la ventana'):
            continue
        acta.comprobar(all(p[3] == borde for p in pedidas),
                       f'y le dice a la ventana que el borde es «{borde}»',
                       str({p[3] for p in pedidas}))
        ultimo = pedidas[-1]
        acta.comprobar(ultimo[1] >= 1100 and ultimo[2] >= 700,
                       f'el tirador «{borde}» nunca pide menos del mínimo',
                       f'{ultimo[1]}×{ultimo[2]}')
        crece_ancho = ultimo[1] > ancho
        crece_alto = ultimo[2] > alto
        if borde in ('se',):
            bien = crece_ancho and crece_alto
        elif borde == 'o':
            bien = crece_ancho
        elif borde == 'n':
            bien = crece_alto
        else:
            bien = ultimo[1] <= ancho
        acta.comprobar(bien, f'y la ventana sale {espera}',
                       f'pedido {ultimo[1]}×{ultimo[2]} desde {ancho}×{alto}')

    # Que no inunde el puente: el ratón manda decenas de movimientos por segundo
    # y cada llamada cruza el puente de pywebview. Encolándolas todas, la ventana
    # se quedaba persiguiendo al ratón cientos de milisegundos por detrás.
    acta.comprobar(len(_llamadas(pag, 'redimensionar')) <= 12,
                   'y no se manda una llamada por cada pixel del arrastre',
                   f'{len(_llamadas(pag, "redimensionar"))} llamadas')


def el_interruptor(app: App, acta: Acta, servidor, cabeceras) -> None:
    """El interruptor de Configuración, que es la salida de emergencia.

    Si la barra propia se porta mal en algún equipo, esto es lo que devuelve la
    de Windows sin reinstalar nada. Tiene que guardar de verdad.
    """
    pag = app.pag
    pag.evaluate("() => document.querySelector('[data-tab=\"configuracion\"]').click()")
    pag.wait_for_timeout(600)
    # Configuración va por grupos y el que abre es el de las reglas, así que se
    # llega como llega una persona: por su entrada del menú de la izquierda. Eso
    # comprueba además que la entrada esté puesta y lleve a donde dice.
    acta.comprobar(bool(pag.query_selector('[data-ir-config="cfg-ventana"]')),
                   'el menú de Configuración tiene su entrada «Barra de la ventana»')
    pag.evaluate("() => document.querySelector('[data-ir-config=\"cfg-ventana\"]').click()")
    pag.wait_for_timeout(700)
    acta.comprobar(_visible(pag, '#cfg-ventana'),
                   'y lleva a la tarjeta, que está en el grupo de Apariencia')
    # La barra va pegada arriba: saltar a una tarjeta tiene que dejarle hueco, o
    # el título de la tarjeta queda medio tapado por la propia barra.
    tapado = pag.evaluate(
        """() => {
             const t = document.querySelector('#cfg-ventana h2').getBoundingClientRect();
             const b = document.getElementById('barra-ventana').getBoundingClientRect();
             return t.top < b.bottom;
           }""")
    acta.comprobar(not tapado,
                   'y el título de la tarjeta no queda tapado por la barra')

    # De fábrica va la de Windows: la propia se entrega apagada porque es lo
    # único que no se puede comprobar sin un escritorio delante.
    marcados = pag.evaluate(
        """() => [...document.querySelectorAll('[data-barra-opcion]')]
                 .filter(b => b.classList.contains('active'))
                 .map(b => b.dataset.barraOpcion)""")
    acta.comprobar(marcados == ['windows'],
                   'de fábrica enseña marcada la barra de Windows', str(marcados))

    pag.evaluate("() => document.querySelector('[data-barra-opcion=\"propia\"]').click()")
    pag.wait_for_timeout(900)
    estado, datos = servidor.pedir('/api/configuracion/barra-ventana', 'GET', None, cabeceras)
    acta.comprobar(estado == 200 and datos.get('propia') is True,
                   'encender la del programa queda guardado en la base',
                   f'{estado} {datos}')
    marcados = pag.evaluate(
        """() => [...document.querySelectorAll('[data-barra-opcion]')]
                 .filter(b => b.classList.contains('active'))
                 .map(b => b.dataset.barraOpcion)""")
    acta.comprobar(marcados == ['propia'], 'y la pantalla lo refleja', str(marcados))

    nota = pag.text_content('#barra-ventana-nota') or ''
    acta.comprobar('abr' in nota.lower(),
                   'y se dice que el cambio se ve al abrir de nuevo, no ahora', nota)

    # La barra que ya está puesta **no** se retira: el marco de una ventana se
    # decide al crearla. Retirarla ahora dejaría esta ventana sin barra ninguna.
    acta.comprobar(_visible(pag, '#barra-ventana'),
                   'y la barra de esta ventana sigue ahí: se decide al abrir')

    pag.evaluate("() => document.querySelector('[data-barra-opcion=\"windows\"]').click()")
    pag.wait_for_timeout(900)
    estado, datos = servidor.pedir('/api/configuracion/barra-ventana', 'GET', None, cabeceras)
    acta.comprobar(estado == 200 and datos.get('propia') is False,
                   'y se puede volver a la de Windows, que es la salida de emergencia',
                   f'{estado} {datos}')


def main() -> int:
    from playwright.sync_api import sync_playwright

    acta = Acta()
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    with Servidor('/tmp/qa_ventana_datos') as servidor:
        cabeceras = entrar_como_admin(servidor)
        print(f'Servidor en {servidor.base}\n')
        with sync_playwright() as guion:
            navegador = guion.chromium.launch(executable_path=NAVEGADOR,
                                              args=['--no-sandbox'])
            pagina = navegador.new_page(viewport={'width': 1400, 'height': 900})
            # El puente, antes de que cargue la página: la barra se enciende al
            # arrancar y tiene que encontrarlo ya puesto.
            pagina.add_init_script(PUENTE_DE_MENTIRA)
            app = App(pagina)
            try:
                pagina.goto(servidor.base, wait_until='networkidle')
                pagina.wait_for_timeout(1500)
                print('— con el acceso echado')
                antes_de_entrar(app, acta)
                pagina.screenshot(path=str(CAPTURAS / 'acceso.png'))

                print('\n— dentro de la aplicación')
                acta.comprobar(app.entrar(servidor.base), 'se entra como administrador')
                pagina.wait_for_timeout(1200)
                el_titulo(app, acta)
                se_arrastra_solo_por_la_barra(app, acta)
                los_tres_botones(app, acta)
                el_boton_del_medio(app, acta)
                los_tiradores(app, acta)
                el_interruptor(app, acta, servidor, cabeceras)
                pagina.screenshot(path=str(CAPTURAS / 'dentro.png'))

                acta.comprobar(not app.errores_js,
                               'ni un solo error de JavaScript en todo el recorrido',
                               ' | '.join(x[:120] for x in app.errores_js[:4]))
            finally:
                navegador.close()
    print(f'\nCapturas en {CAPTURAS}')
    return acta.resumen()


if __name__ == '__main__':
    raise SystemExit(main())
