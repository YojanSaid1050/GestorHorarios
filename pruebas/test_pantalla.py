# -*- coding: utf-8 -*-
"""Que la pantalla y el servidor hablen el mismo idioma.

Este archivo existe por el fallo más caro de la versión anterior, y el que más
costó ver: la pantalla llamaba a direcciones que el servidor ya no tenía, o las
llamaba con otro verbo. Nada fallaba al arrancar, nada salía en rojo en las
pruebas, y el usuario se encontraba con botones que no hacían nada y con un
aviso genérico de error. Cada pieza estaba bien por separado; lo que estaba mal
era el encaje entre las dos.

Aquí se leen las llamadas que hace la pantalla de verdad —del JavaScript, no de
una lista escrita a mano que se quedaría vieja— y se comprueba que el servidor
tenga cada una, con su verbo. Es la prueba que convierte «se me olvidó portar
esa ruta» en un fallo inmediato en vez de en una llamada de la oficina.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
PANTALLA = RAIZ / 'gestor' / 'pantalla'


def _entre_parentesis(texto: str, apertura: int) -> str:
    """El contenido de la llamada, contando paréntesis para no cortar a medias."""
    profundidad, i = 0, apertura
    while i < len(texto):
        if texto[i] == '(':
            profundidad += 1
        elif texto[i] == ')':
            profundidad -= 1
            if profundidad == 0:
                return texto[apertura + 1:i]
        i += 1
    return texto[apertura:apertura + 500]


def _primer_argumento(cuerpo: str) -> str:
    """Solo la dirección: se corta en la primera coma de nivel cero."""
    profundidad = 0
    comilla = ''
    for i, c in enumerate(cuerpo):
        if comilla:
            if c == comilla:
                comilla = ''
            continue
        if c in '\'"`':
            comilla = c
        elif c in '([{':
            profundidad += 1
        elif c in ')]}':
            profundidad -= 1
        elif c == ',' and profundidad == 0:
            return cuerpo[:i]
    return cuerpo


def direccion_de(argumento: str) -> str:
    """La dirección con un `*` donde el JavaScript mete una variable.

    Hay que reconstruirla en vez de leerla tal cual porque la pantalla la arma
    de tres maneras: literal, con plantilla (`${id}`) y concatenando con `+`.
    Quedarse solo con el primer trozo daba `/api/solicitudes/` y hacía creer que
    faltaba una ruta que sí existe.
    """
    trozos: list[str] = []
    i = 0
    while i < len(argumento):
        c = argumento[i]
        if c in '\'"`':
            fin = argumento.find(c, i + 1)
            if fin < 0:
                break
            trozos.append(re.sub(r'\$\{[^}]*\}', '*', argumento[i + 1:fin]))
            i = fin + 1
        elif c == '+':
            trozos.append('*')
            i += 1
        else:
            i += 1
    camino = ''.join(trozos).split('?')[0]
    camino = re.sub(r'\*+', '*', camino)
    return re.sub(r'/\*+/?$', '/*', camino) if camino.endswith('*') else camino


def llamadas_de_la_pantalla() -> set[tuple[str, str, str]]:
    """Verbo, dirección y archivo de cada `api('/api/...')` del JavaScript."""
    encontradas: set[tuple[str, str, str]] = set()
    for archivo in sorted((PANTALLA / 'js').glob('*.js')):
        texto = archivo.read_text(encoding='utf-8')
        for coincidencia in re.finditer(r'\bapi\(', texto):
            cuerpo = _entre_parentesis(texto, coincidencia.end() - 1)
            argumento = _primer_argumento(cuerpo)
            if not re.match(r"""\s*[`'"]/api/""", argumento):
                continue
            verbo = re.search(r"""method\s*:\s*['"](\w+)['"]""", cuerpo)
            encontradas.add(((verbo.group(1).upper() if verbo else 'GET'),
                             direccion_de(argumento), archivo.name))
    return encontradas


#: Lo que no es un verbo dentro de la descripción de un camino.
NO_SON_VERBOS = {'parameters', 'servers', 'summary', 'description', 'head', 'options'}


def rutas_del_servidor() -> set[tuple[str, str]]:
    """Las direcciones que el servidor sirve, preguntándoselo a él.

    Se lee del **esquema OpenAPI**, que es la descripción que FastAPI publica de
    sí mismo, y no recorriendo `aplicacion.routes` a mano. Recorrer esa lista
    funcionó durante meses y se rompió sin avisar: desde FastAPI 0.141,
    `include_router` ya no vuelca las rutas ahí dentro —mete un envoltorio que ni
    siquiera tiene `path`—, así que la lista salía con cero direcciones y esta
    prueba denunciaba que **toda** la pantalla llamaba a sitios inexistentes.

    Ochenta líneas de fallo apuntando a todas partes, o sea a ninguna. Y no
    apareció al programar: apareció al publicar, porque aquí las versiones
    estaban instaladas de hace meses y el flujo instala las últimas.

    El esquema es la respuesta oficial a «¿qué sirves?», existe desde siempre y
    no cambia de forma. Preguntar es mejor que deducir.
    """
    from gestor.web.aplicacion import crear_aplicacion
    esquema = crear_aplicacion().openapi()
    return {(verbo.upper(), re.sub(r'\{[^}]*\}', '*', camino))
            for camino, operaciones in (esquema.get('paths') or {}).items()
            if camino.startswith('/api')
            for verbo in operaciones
            if verbo.lower() not in NO_SON_VERBOS}


def _patron(direccion: str) -> list[str]:
    return [t for t in direccion.split('/') if t]


def _existe(verbo: str, direccion: str, rutas: set[tuple[str, str]]) -> bool:
    pedida = _patron(direccion)
    for otro_verbo, camino in rutas:
        if otro_verbo != verbo:
            continue
        trozos = [t for t in camino.split('/') if t]
        if len(trozos) != len(pedida):
            continue
        if all(a == '*' or b == '*' or a == b for a, b in zip(pedida, trozos, strict=False)):
            return True
    return False


def test_la_pantalla_llama_a_rutas_que_existen(carpeta_de_datos):
    """Ninguna llamada del JavaScript puede quedarse sin destino.

    Si esta prueba falla, la lista dice exactamente qué botón de la aplicación
    no hace nada y desde qué archivo se pulsa.
    """
    rutas = rutas_del_servidor()
    llamadas = llamadas_de_la_pantalla()

    # Antes de comparar, que haya **algo** de cada lado.
    #
    # Sin esto, que una de las dos listas saliera vacía se leía como «la pantalla
    # entera llama a direcciones que no existen»: ochenta líneas de fallo que
    # apuntan a todas partes, o sea a ninguna. Pasó de verdad, en una
    # publicación, y costó dos vueltas entender que lo que fallaba era la lectura
    # y no lo leído.
    assert len(rutas) > 50, (
        f'el servidor solo declaró {len(rutas)} direcciones, y tiene muchas más. '
        'Lo que falla no son las llamadas de la pantalla: es que las rutas no se '
        f'llegaron a leer.\n  Ejemplo de lo leído: {sorted(rutas)[:3]}')
    assert len(llamadas) > 50, (
        f'solo se leyeron {len(llamadas)} llamadas del JavaScript, y hay muchas '
        'más. Lo que falla es la lectura de los archivos, no la pantalla.')

    huerfanas = sorted(
        f'{verbo:6} {direccion}  (desde {archivo})'
        for verbo, direccion, archivo in llamadas
        if not _existe(verbo, direccion, rutas))
    assert not huerfanas, (
        f'la pantalla llama a {len(huerfanas)} direcciones que el servidor no '
        f'tiene (de {len(llamadas)} llamadas contra {len(rutas)} rutas):\n  '
        + '\n  '.join(huerfanas))


def test_se_están_leyendo_llamadas_de_verdad():
    """Si el lector se rompe, la prueba de arriba pasaría por no encontrar nada.

    Una comprobación que se queda sin datos que comprobar es peor que no
    tenerla: da luz verde sin haber mirado.
    """
    llamadas = llamadas_de_la_pantalla()
    assert len(llamadas) > 60, f'solo se leyeron {len(llamadas)} llamadas'
    assert {v for v, _, _ in llamadas} >= {'GET', 'POST', 'PUT', 'DELETE', 'PATCH'}


def test_la_pantalla_está_donde_la_aplicación_la_busca():
    from gestor import rutas
    assert rutas.PANTALLA.is_dir(), 'la aplicación serviría un 500 en la página inicial'
    assert (rutas.PANTALLA / 'index.html').is_file()


@pytest.mark.parametrize('archivo', sorted(p.name for p in (PANTALLA / 'js').glob('*.js')))
def test_ningún_archivo_de_la_pantalla_quedó_vacío(archivo):
    contenido = (PANTALLA / 'js' / archivo).read_text(encoding='utf-8')
    assert contenido.strip(), f'{archivo} está vacío'
