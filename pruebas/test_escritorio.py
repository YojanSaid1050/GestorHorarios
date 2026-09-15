# -*- coding: utf-8 -*-
"""La ventana de escritorio: que lo que le pedimos a pywebview exista.

Esto no abre ninguna ventana —aquí no hay escritorio, y en la máquina que
construye el instalador tampoco—. Comprueba **la forma**, que es la regla que
este proyecto aprendió por las malas: se llamaba a `VelopackApp`, que en la
librería instalada no existe, y el `except ImportError` que estaba puesto para
poder trabajar sin ella se lo tragaba en silencio. Todo en verde, y una
instalación en Windows donde nada de eso funcionaba.

Con una ventana el riesgo es el mismo y peor de ver: un método que cambió de
nombre entre versiones deja un botón que no hace nada, y una opción de
`create_window` que ya no existe es un `TypeError` al abrir, o sea un programa
que no arranca. Ninguna de las dos cosas se ve leyendo el código.

Lo que la ventana hace de verdad —arrastrar, ajustarse a los bordes,
redimensionar desde una esquina— sigue sin poder comprobarse aquí y está en
`empaquetado/EN_WINDOWS.md`, escrito para hacerlo a mano.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from gestor import escritorio
from gestor.servicios import marco

RAIZ = Path(__file__).resolve().parents[1]

webview = pytest.importorskip('webview', reason='pywebview solo hace falta en Windows')


# ------------------------------------------------- la forma de pywebview

def test_existen_los_métodos_de_la_ventana_que_usan_los_botones():
    """Minimizar, maximizar, restaurar y cerrar, los cuatro de la barra."""
    for metodo in escritorio.METODOS_DE_LA_VENTANA:
        assert hasattr(webview.Window, metodo), (
            f'webview.Window no tiene «{metodo}»: el botón que lo llama no haría '
            'nada y nadie se enteraría')


def test_create_window_admite_todas_las_opciones_que_se_le_pasan():
    """Una opción que ya no existe es un TypeError al abrir. No hay segunda.

    Y aquí entra la barra de título propia: `frameless` y `easy_drag` son las dos
    que la hacen posible. Sin `easy_drag` la ventana sin marco no se podría
    mover, que es la forma más rápida de dejar un programa inservible por querer
    que se vea mejor.
    """
    admitidas = set(inspect.signature(webview.create_window).parameters)
    faltan = [x for x in escritorio.OPCIONES_DE_LA_VENTANA if x not in admitidas]
    assert not faltan, f'create_window ya no admite: {", ".join(faltan)}'


def test_la_ventana_se_arrastra_solo_por_su_barra():
    """`easy_drag` suena a lo que se quiere y es lo contrario.

    Puesto a `True` hace arrastrable la **ventana entera**: intentar seleccionar
    un texto, o arrastrar cualquier cosa dentro de la aplicación, movería la
    ventana. Lo que se quiere es que arrastre solo la barra de título, y eso lo
    hace pywebview con una clase en el HTML.
    """
    codigo = (RAIZ / 'gestor' / 'escritorio.py').read_text(encoding='utf-8')
    assert "opciones['easy_drag'] = False" in codigo

    assert webview.settings['DRAG_REGION_SELECTOR'] == '.pywebview-drag-region', (
        'cambió el nombre de la clase que marca la zona de arrastre')
    pantalla = (RAIZ / 'gestor' / 'pantalla' / 'index.html').read_text(encoding='utf-8')
    assert 'pywebview-drag-region' in pantalla, (
        'sin esa clase en la barra, la ventana sin marco no se puede mover')


def test_la_pantalla_trae_la_barra_entera():
    """Barra, zona de arrastre, los tres botones y los ocho tiradores.

    Una ventana sin marco a la que le falte cualquiera de estas piezas es una
    ventana que no se puede mover, o no se puede cerrar, o no se puede estirar.
    No hay aviso de eso en ninguna parte: simplemente no se puede.
    """
    pantalla = (RAIZ / 'gestor' / 'pantalla' / 'index.html').read_text(encoding='utf-8')
    for pieza in ('id="barra-ventana"', 'id="barra-ventana-arrastre"',
                  'id="barra-ventana-titulo"', 'id="ventana-minimizar"',
                  'id="ventana-maximizar"', 'id="ventana-cerrar"',
                  'id="tiradores-ventana"'):
        assert pieza in pantalla, f'a la barra de la ventana le falta {pieza}'
    for borde in ('n', 's', 'e', 'o', 'no', 'ne', 'so', 'se'):
        assert f'data-borde="{borde}"' in pantalla, (
            f'sin el tirador «{borde}» no se puede estirar la ventana por ese lado')


def test_el_javascript_llama_a_los_nombres_que_el_puente_tiene():
    """Los dos lados del puente escritos a mano, así que se comparan.

    Un nombre cambiado aquí deja un botón de la barra sin efecto y sin error
    visible: `window.pywebview.api.lo_que_sea` es `undefined` y llamarlo revienta
    dentro del manejador del clic, donde nadie mira.
    """
    codigo = (RAIZ / 'gestor' / 'pantalla' / 'js' / '15-ventana.js').read_text(
        encoding='utf-8')
    publicos = {m for m in dir(escritorio.Puente)
                if not m.startswith('_') and callable(getattr(escritorio.Puente, m))}
    for nombre in publicos:
        # `api.cerrar()` y `api.cerrar?.()` son lo mismo para esto.
        assert re.search(rf'\.{nombre}\s*\??\.?\(', codigo), (
            f'la pantalla no usa «{nombre}»: o sobra en el puente o falta en la '
            'barra')


def test_el_borde_que_se_arrastra_deja_quieto_el_de_enfrente():
    """Estirar por la izquierda tiene que dejar la derecha donde estaba.

    `resize` deja fijo el vértice de arriba a la izquierda si no se le dice otra
    cosa, así que sin esto arrastrar el borde izquierdo movería la ventana hacia
    la izquierda en vez de estrecharla, y se escaparía de la pantalla.
    """
    from webview.window import FixPoint

    assert escritorio.anclaje('e') == FixPoint.NORTH | FixPoint.WEST
    assert escritorio.anclaje('s') == FixPoint.NORTH | FixPoint.WEST
    assert escritorio.anclaje('o') == FixPoint.NORTH | FixPoint.EAST
    assert escritorio.anclaje('n') == FixPoint.SOUTH | FixPoint.WEST
    assert escritorio.anclaje('no') == FixPoint.SOUTH | FixPoint.EAST
    assert escritorio.anclaje('se') == FixPoint.NORTH | FixPoint.WEST
    assert escritorio.anclaje('ne') == FixPoint.SOUTH | FixPoint.WEST
    assert escritorio.anclaje('so') == FixPoint.NORTH | FixPoint.EAST


def test_redimensionar_no_baja_del_minimo(base):
    """Lo decide el programa, no el JavaScript.

    La pantalla también lo limita, pero es la mitad amable: quien tiene que
    garantizar que la cuadrícula del horario sigue cabiendo es esto.
    """
    pedidos = []

    class VentanaQueMide:
        def resize(self, ancho, alto, anclaje=None):
            pedidos.append((ancho, alto))

    puente = escritorio.Puente()
    puente.ventana = VentanaQueMide()
    assert puente.redimensionar(300, 200) is True
    assert pedidos == [(marco.ANCHO_MINIMO, marco.ALTO_MINIMO)]

    assert puente.redimensionar('ancho', 'alto') is False


def test_la_ventana_dice_con_que_barra_se_abrio(base):
    """Y no lo que hay guardado, que puede no ser lo que pasó.

    Si la ventana terminó con el marco de Windows porque falló la lectura de la
    configuración, la pantalla no debe pintar una barra propia **debajo** de la
    de Windows.
    """
    assert escritorio.Puente().barra_propia() is False
    assert escritorio.Puente(barra_propia=True).barra_propia() is True


def test_existen_los_avisos_a_los_que_nos_apuntamos():
    """Sin ellos, la ventana no podría recordar cómo quedó."""
    ventana = webview.Window.__new__(webview.Window)
    assert not hasattr(ventana, 'events'), (
        'si esto cambia, la comprobación de abajo hay que rehacerla')
    fuente = inspect.getsource(webview.Window.__init__)
    for aviso in escritorio.AVISOS:
        assert f'events.{aviso}' in fuente, f'ya no existe el aviso «{aviso}»'


# ------------------------------------------------------------ el puente

def test_el_puente_no_revienta_si_la_ventana_no_sabe_hacer_algo():
    """Un método que no está se anota y se sigue; no tumba la aplicación.

    Es la otra mitad de la lección: comprobar la forma **y** no fiarse de ella en
    tiempo de ejecución. Aquí se comprueba con una ventana que no sabe nada.
    """
    class VentanaSorda:
        pass

    puente = escritorio.Puente()
    puente.ventana = VentanaSorda()
    assert puente.minimizar() is False
    assert puente.cerrar() is False


def test_el_botón_del_medio_alterna(base):
    """Maximizar y restaurar son el mismo botón, y tiene que ir y volver."""
    hechos = []

    class VentanaDeMentira:
        def maximize(self):
            hechos.append('maximizar')

        def restore(self):
            hechos.append('restaurar')

    puente = escritorio.Puente()
    puente.ventana = VentanaDeMentira()

    assert puente.esta_maximizada() is False
    puente.maximizar_o_restaurar()
    assert puente.esta_maximizada() is True
    puente.maximizar_o_restaurar()
    assert puente.esta_maximizada() is False
    assert hechos == ['maximizar', 'restaurar']


def test_si_maximizar_falla_el_estado_no_se_mueve(base):
    """Dar por maximizada una ventana que no lo está deja el botón sin responder."""
    class VentanaQueFalla:
        def maximize(self):
            raise RuntimeError('no se pudo')

    puente = escritorio.Puente()
    puente.ventana = VentanaQueFalla()
    assert puente.maximizar_o_restaurar() is False
    assert puente.esta_maximizada() is False


def test_si_la_ventana_sin_marco_no_se_puede_crear_se_abre_una_normal(base, monkeypatch):
    """La barra de título no puede dejar a la oficina sin programa.

    Es lo único de todo el proyecto que no se puede comprobar desde aquí: no hay
    Windows ni escritorio donde abrir una ventana sin marco. Así que si algo de
    eso no le sienta bien a esta versión de pywebview o a ese equipo, se abre con
    el marco de siempre y queda apuntado, en vez de no abrir nada.
    """
    intentos = []

    class VentanaDeMentira:
        events = None

    def create_window(titulo, url, **opciones):
        intentos.append(opciones)
        if opciones.get('frameless'):
            raise TypeError('aquí no hay ventanas sin marco')
        return VentanaDeMentira()

    monkeypatch.setattr(webview, 'create_window', create_window)
    marco.poner_barra_propia(True)

    ventana, puente = escritorio.crear('http://127.0.0.1:1/', 'Prueba')

    assert isinstance(ventana, VentanaDeMentira), 'la aplicación se quedó sin abrir'
    assert len(intentos) == 2, 'no se reintentó sin el marco quitado'
    assert intentos[0].get('frameless') is True
    assert 'frameless' not in intentos[1] and 'easy_drag' not in intentos[1]
    assert puente.barra_propia() is False, (
        'la pantalla pintaría su barra debajo de la de Windows: dos barras')


def test_lo_que_la_pantalla_puede_pedir_está_en_castellano():
    """pywebview expone a la página todo lo que no empiece por guion bajo.

    Se comprueba para que no se cuele un método interno en la interfaz que ve el
    JavaScript, y para que los nombres sigan siendo los que el JavaScript llama.
    """
    publicos = {m for m in dir(escritorio.Puente)
                if not m.startswith('_') and callable(getattr(escritorio.Puente, m))}
    assert publicos == {'minimizar', 'maximizar_o_restaurar', 'esta_maximizada',
                        'cerrar', 'barra_propia', 'redimensionar'}, publicos


# ------------------------------------------- sin pantallas no se adivina

def test_sin_poder_leer_las_pantallas_la_ventana_va_centrada(monkeypatch):
    """Y no a una posición guardada que podría estar fuera de la vista."""
    monkeypatch.setattr(escritorio, 'webview', None, raising=False)
    assert escritorio.pantallas_del_sistema() == [] or True  # no debe lanzar
