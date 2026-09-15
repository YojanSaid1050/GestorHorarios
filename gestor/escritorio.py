# -*- coding: utf-8 -*-
"""La ventana de escritorio: cómo se crea y cómo la maneja la propia pantalla.

Aquí vive todo lo que sabe que existe pywebview. `principal.py` pide una ventana
y se le da; si no hay pywebview, no pasa nada y la aplicación se sigue pudiendo
abrir en un navegador.

## La barra de título propia

De fábrica la ventana va **sin marco de Windows** y la barra la pinta la propia
pantalla, con el color y el logo del programa. Se ve mejor y encaja con el resto.

Lo que se pierde al quitar el marco lo pone Windows gratis y hay que rehacerlo a
mano: arrastrar, el doble clic para maximizar, y el ajuste a los bordes. Por eso:

* la barra de título se arrastra porque lleva la clase `pywebview-drag-region`, y
  **solo ella**: con `easy_drag` se arrastraría la ventana entera y no se podría
  ni seleccionar un texto dentro de la aplicación;
* los botones de minimizar, maximizar y cerrar llaman a Python desde el
  JavaScript de la pantalla, y el doble clic en la barra maximiza igual que en
  cualquier ventana;
* **se puede redimensionar**, que es lo que más cuesta: un formulario sin marco
  pierde el borde que se agarra con el ratón, así que la pantalla pone ocho
  tiradores invisibles alrededor y llama a `redimensionar` mientras se arrastran;
* y **hay interruptor**. Es lo único del programa que no se puede comprobar sin
  un escritorio delante: si en algún equipo arrastra mal o no se deja
  redimensionar, se vuelve a la barra de Windows desde Configuración, sin
  reinstalar nada y sin esperar a una versión nueva.

## Por qué todo se llama con `getattr`

Porque de una librería externa se comprueba la forma, no la fe. Los nombres de
`minimize`, `maximize` y compañía cambian entre versiones de pywebview, y un
`AttributeError` dentro del manejador de un botón no se ve en ninguna parte: el
botón deja de funcionar y nadie se entera. Aquí, si un método no está, se dice en
el registro y el programa sigue abierto.

`pruebas/test_escritorio.py` comprueba que los nombres que se usan existen de
verdad en la versión instalada, que es la lección que costó la versión anterior:
se llamaba a `VelopackApp`, que no existía, y el `except` se lo tragaba.
"""
from __future__ import annotations

from typing import Optional

from gestor.registro import obtener
from gestor.servicios import marco

#: Los métodos de la ventana que este programa usa. La prueba de forma comprueba
#: que existan; el código los llama con `getattr` por si algún día no.
METODOS_DE_LA_VENTANA = ('minimize', 'maximize', 'restore', 'destroy', 'resize')

#: Los avisos a los que nos apuntamos para saber cómo quedó la ventana. No todos
#: existen en todas las versiones, así que se piden de uno en uno.
AVISOS = ('resized', 'moved', 'maximized', 'restored')

#: Las opciones de `create_window` que este programa usa. La prueba de forma
#: comprueba que la versión instalada las admita: pasar una que no existe es un
#: `TypeError` al abrir, o sea un programa que no arranca.
OPCIONES_DE_LA_VENTANA = ('width', 'height', 'x', 'y', 'min_size', 'resizable',
                          'confirm_close', 'js_api', 'frameless', 'easy_drag',
                          'maximized')


def pantallas_del_sistema() -> list[tuple[int, int, int, int]]:
    """Los rectángulos de las pantallas que hay **ahora**.

    Sirven para decidir si la posición guardada sigue siendo visible. Si no se
    pueden averiguar, se devuelve nada y la ventana se abre centrada, que es lo
    que no deja a nadie sin ver el programa.
    """
    try:
        import webview
        return [(int(p.x), int(p.y), int(p.width), int(p.height))
                for p in webview.screens]
    except Exception:                                              # noqa: BLE001
        obtener().info('no se pudieron leer las pantallas; la ventana irá centrada')
        return []


def anclaje(borde: str):
    """El borde que se queda quieto mientras se arrastra `borde`.

    Sin esto, estrechar la ventana por el lado izquierdo la movería hacia la
    izquierda en vez de estrecharla: `resize` deja fijo el vértice de arriba a la
    izquierda salvo que se le diga otra cosa. `borde` viene de la pantalla como
    `'n'`, `'s'`, `'e'`, `'o'` o una esquina (`'no'`, `'se'`…).
    """
    from webview.window import FixPoint  # noqa: PLC0415
    borde = (borde or 'se').lower()
    vertical = FixPoint.SOUTH if 'n' in borde else FixPoint.NORTH
    horizontal = FixPoint.EAST if 'o' in borde else FixPoint.WEST
    return vertical | horizontal


class Puente:
    """Lo que la pantalla puede pedirle a la ventana.

    Se expone a la página como `window.pywebview.api`. Los nombres están en
    castellano como todo lo demás: los lee quien mantiene el JavaScript.
    """

    def __init__(self, barra_propia: bool = False) -> None:
        self.ventana = None
        self._maximizada = False
        self._barra_propia = bool(barra_propia)

    def barra_propia(self) -> bool:
        """¿Tiene que pintar la pantalla su propia barra de título?

        Lo pregunta el JavaScript al arrancar, y se contesta desde aquí y no con
        una llamada al servidor **a propósito**: la pantalla de acceso se ve antes
        de iniciar sesión, y todo lo que está bajo `/api/configuracion/` pide
        sesión. Preguntándolo por ahí, una ventana sin marco se abriría sin barra
        y sin forma de moverla ni de cerrarla hasta después de entrar.

        Y además dice la verdad en vez de lo guardado: si la ventana terminó
        creándose con el marco de Windows porque algo falló al leer la
        configuración, aquí se contesta `False` y la pantalla no pinta una barra
        de más debajo de la de Windows.
        """
        return self._barra_propia

    def _hacer(self, metodo: str) -> bool:
        accion = getattr(self.ventana, metodo, None)
        if accion is None:
            obtener().warning('la ventana no tiene «%s» en esta versión de '
                              'pywebview', metodo)
            return False
        try:
            accion()
        except Exception:                                          # noqa: BLE001
            obtener().exception('falló «%s» de la ventana', metodo)
            return False
        return True

    def minimizar(self) -> bool:
        return self._hacer('minimize')

    def maximizar_o_restaurar(self) -> bool:
        """El botón del medio, que hace las dos cosas según cómo esté.

        El estado se lleva aquí porque preguntárselo a la ventana no es fiable
        entre versiones, y equivocarse significa que el botón deja de responder
        al segundo clic.
        """
        quiere_maximizar = not self._maximizada
        if not self._hacer('maximize' if quiere_maximizar else 'restore'):
            return False
        self._maximizada = quiere_maximizar
        marco.recordar(maximizada=quiere_maximizar)
        return True

    def esta_maximizada(self) -> bool:
        return self._maximizada

    def redimensionar(self, ancho, alto, borde: str = 'se') -> bool:
        """Cambiar el tamaño arrastrando un borde, que es lo que quita el marco.

        Una ventana sin marco **no se puede redimensionar arrastrando los
        bordes**: quitarle el marco a un formulario de Windows le quita también el
        borde que se agarra. Es el precio de la barra propia, y no pagarlo es de
        lo poco que hay que rehacer a mano: la pantalla pone ocho tiradores
        invisibles alrededor y llama aquí mientras se arrastran.

        El mínimo se respeta aquí y no solo en la pantalla, porque quien decide
        cuánto puede encogerse esta ventana es el programa y no el JavaScript.
        """
        if self.ventana is None:
            return False
        try:
            ancho = max(int(ancho), marco.ANCHO_MINIMO)
            alto = max(int(alto), marco.ALTO_MINIMO)
        except (TypeError, ValueError):
            obtener().warning('la pantalla pidió un tamaño que no son números: '
                              '%r×%r', ancho, alto)
            return False
        cambiar = getattr(self.ventana, 'resize', None)
        if cambiar is None:
            obtener().warning('la ventana no tiene «resize» en esta versión de '
                              'pywebview: no se podrá redimensionar sin marco')
            return False
        try:
            cambiar(ancho, alto, anclaje(borde))
        except Exception:                                          # noqa: BLE001
            obtener().exception('no se pudo redimensionar la ventana')
            return False
        marco.recordar(ancho=ancho, alto=alto)
        return True

    def cerrar(self) -> bool:
        return self._hacer('destroy')


def _apuntarse_a_los_avisos(ventana, puente: Puente) -> None:
    """Guardar el tamaño y la posición cada vez que cambian.

    Se hace desde Python y no desde el JavaScript a propósito: el JavaScript no
    sabe dónde está la ventana en la pantalla, solo lo grande que es por dentro.
    """
    avisos = getattr(ventana, 'events', None)
    if avisos is None:
        obtener().info('esta versión de pywebview no avisa de los cambios de la '
                       'ventana; no se podrá recordar cómo quedó')
        return

    def al_cambiar_el_tamaño(ancho, alto):
        marco.recordar(ancho=ancho, alto=alto)

    def al_moverse(x, y):
        marco.recordar(x=x, y=y)

    def al_maximizar():
        puente._maximizada = True
        marco.recordar(maximizada=True)

    def al_restaurar():
        puente._maximizada = False
        marco.recordar(maximizada=False)

    for nombre, manejador in (('resized', al_cambiar_el_tamaño),
                              ('moved', al_moverse),
                              ('maximized', al_maximizar),
                              ('restored', al_restaurar)):
        aviso = getattr(avisos, nombre, None)
        if aviso is None:
            continue
        try:
            aviso += manejador
        except Exception:                                          # noqa: BLE001
            obtener().exception('no se pudo escuchar el aviso «%s»', nombre)


def crear(url: str, titulo: str, puente: Optional[Puente] = None):
    """La ventana, con las medidas de la última vez y la barra que toque.

    Devuelve la ventana y el puente. Que falle algo de aquí no puede impedir
    abrir: ante cualquier duda se cae a una ventana normal, con marco y centrada,
    que es lo que siempre funciona.
    """
    import webview

    try:
        puesta = marco.como_abrir(pantallas_del_sistema())
    except Exception:                                              # noqa: BLE001
        obtener().exception('no se pudo leer cómo quedó la ventana la última vez')
        puesta = {'ancho': marco.ANCHO_POR_DEFECTO, 'alto': marco.ALTO_POR_DEFECTO,
                  'x': None, 'y': None, 'maximizada': False, 'barra_propia': False}

    puente = puente or Puente()
    puente._barra_propia = bool(puesta['barra_propia'])

    opciones = {
        'width': puesta['ancho'],
        'height': puesta['alto'],
        'min_size': (marco.ANCHO_MINIMO, marco.ALTO_MINIMO),
        'resizable': True,
        'confirm_close': False,
        'js_api': puente,
    }
    if puesta['x'] is not None and puesta['y'] is not None:
        opciones['x'], opciones['y'] = puesta['x'], puesta['y']
    if puesta['maximizada']:
        opciones['maximized'] = True
    if puesta['barra_propia']:
        # Sin marco, y arrastrable **solo por la barra**.
        #
        # `easy_drag=True` suena a lo que se quiere y es justo lo contrario: hace
        # arrastrable la ventana entera, así que cualquier intento de seleccionar
        # un texto o de arrastrar algo dentro de la aplicación movería la ventana.
        # Con `False`, pywebview solo arrastra desde lo que lleve la clase
        # `pywebview-drag-region`, que es la que tiene la barra de título de la
        # pantalla y nada más.
        opciones['frameless'] = True
        opciones['easy_drag'] = False

    try:
        ventana = webview.create_window(titulo, url, **opciones)
    except Exception:                                              # noqa: BLE001
        # Última red, y la única que este proyecto no puede comprobar desde aquí:
        # no hay Windows ni escritorio donde probarlo. Si algo de la ventana sin
        # marco no le sienta bien a esta versión de pywebview o a este equipo, lo
        # que **no** puede pasar es que la oficina se quede sin programa por una
        # barra de título. Se abre con el marco de Windows, que es lo que siempre
        # funciona, y queda apuntado en el registro.
        obtener().exception('no se pudo crear la ventana con %r; se abre normal',
                            opciones)
        for solo_estetico in ('frameless', 'easy_drag', 'maximized', 'x', 'y'):
            opciones.pop(solo_estetico, None)
        puente._barra_propia = False
        ventana = webview.create_window(titulo, url, **opciones)
    puente.ventana = ventana
    # De `opciones` y no de `puesta`: si hubo que caer a la ventana normal, la
    # maximización se quedó por el camino y el botón tiene que saberlo, o el
    # primer clic no haría nada.
    puente._maximizada = bool(opciones.get('maximized'))
    _apuntarse_a_los_avisos(ventana, puente)
    return ventana, puente
