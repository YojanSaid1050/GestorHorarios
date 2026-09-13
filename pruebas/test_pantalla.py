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


def rutas_del_servidor() -> set[tuple[str, str]]:
    from gestor.web.aplicacion import crear_aplicacion
    aplicacion = crear_aplicacion()
    return {(verbo, re.sub(r'\{[^}]*\}', '*', ruta.path))
            for ruta in aplicacion.routes
            if getattr(ruta, 'path', '').startswith('/api')
            for verbo in (getattr(ruta, 'methods', set()) - {'HEAD', 'OPTIONS'})}


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
    huerfanas = sorted(
        f'{verbo:6} {direccion}  (desde {archivo})'
        for verbo, direccion, archivo in llamadas_de_la_pantalla()
        if not _existe(verbo, direccion, rutas))
    assert not huerfanas, (
        'la pantalla llama a direcciones que el servidor no tiene:\n  '
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
