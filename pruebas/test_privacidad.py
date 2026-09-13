# -*- coding: utf-8 -*-
"""Que no se cuele en el repositorio el nombre de nadie de la oficina.

Este repositorio es **público**, y dentro de esta aplicación viven los nombres y
los horarios de dieciocho personas. La plantilla de verdad viaja aparte —en un
secreto del repositorio, que el empaquetado aplica al construir— y lo que está
escrito aquí son dieciocho personas inventadas.

La costumbre no basta para sostener eso. Un nombre real se cuela con toda
naturalidad: en el comentario que explica por qué existe una regla, en el nombre
de una persona de mentira de una prueba, en el ejemplo de un mensaje de error.
Y una vez empujado a un repositorio público, borrarlo después **no lo deshace**:
queda en el historial de git y en las copias que ya se hayan hecho.

Así que se comprueba, y se comprueba contra la lista de verdad —que está fuera
del repositorio— cuando existe. Donde no exista, se comprueban al menos las
formas que ya se colaron una vez.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
NOMINA_REAL = RAIZ / 'nomina' / 'datos_iniciales' / 'empleados_iniciales.csv'

#: Lo que se mira. No se mira `nomina/`, que es justo lo que está fuera de git.
MIRADOS = ('*.py', '*.js', '*.md', '*.csv', '*.json', '*.html', '*.css',
           '*.spec', '*.yml', '*.toml', '*.txt')
SALTADOS = ('nomina', 'dist', 'build', '.git', '.ruff_cache', '.pytest_cache',
            'datos', '__pycache__')


def _archivos_del_repositorio() -> list[Path]:
    salida = []
    for patrón in MIRADOS:
        for archivo in RAIZ.rglob(patrón):
            if any(parte in SALTADOS for parte in archivo.relative_to(RAIZ).parts):
                continue
            salida.append(archivo)
    return salida


#: Palabras que coinciden con un nombre real y **no** son ese nombre. Cada una
#: con su motivo escrito, porque una lista de excepciones sin motivos acaba
#: tragándose justo lo que esta prueba busca.
PERMITIDAS = {
    'Abril': 'el mes, en la lista de meses de la pantalla',
    'España': 'el país, en «español de España» del empaquetado',
    # El autor firma el programa. Su nombre está en `version.AUTOR`, en el
    # instalador y en las credenciales de prueba, y está ahí porque él lo puso.
    'Yojan': 'el autor, que firma el programa',
    'Said': 'el autor, que firma el programa',
    'Salazar': 'el autor, que firma el programa',
    'Poveda': 'el autor, que firma el programa',
}


def _palabras_reales() -> set[str]:
    """Cada palabra de cada nombre real, de más de cuatro letras.

    Por palabras y no por nombres completos a propósito: nadie escribe el nombre
    entero de un compañero en un comentario. Escribe «el caso de Fulano», que es
    exactamente como se coló la primera vez.
    """
    with NOMINA_REAL.open(encoding='utf-8') as fila:
        filas = list(csv.DictReader(fila))
    return {trozo for f in filas for trozo in f['nombre'].split()
            if len(trozo) > 4 and trozo not in PERMITIDAS}


@pytest.mark.skipif(not NOMINA_REAL.is_file(),
                    reason='la nómina real no está en este equipo, que es lo normal')
def test_ningún_nombre_de_la_oficina_está_escrito_en_el_repositorio():
    apariciones = []
    for palabra in sorted(_palabras_reales()):
        for archivo in _archivos_del_repositorio():
            texto = archivo.read_text(encoding='utf-8', errors='ignore')
            if palabra in texto:
                apariciones.append(f'{archivo.relative_to(RAIZ)}: «{palabra}»')
    assert not apariciones, (
        'hay nombres de la oficina escritos en el repositorio público:\n  '
        + '\n  '.join(apariciones[:15]))


@pytest.mark.skipif(not NOMINA_REAL.is_file(), reason='la nómina real no está aquí')
def test_los_nombres_inventados_no_comparten_ni_una_palabra_con_los_reales():
    """Dos nombres que comparten el de pila se leen como la misma persona.

    Coincidir en un nombre de pila no publica a nadie, pero deshace la única
    cosa que la plantilla inventada tiene que conseguir: que nadie pueda mirarla
    y reconocer a un compañero.
    """
    with (RAIZ / 'datos_iniciales' / 'empleados_iniciales.csv').open(
            encoding='utf-8') as fila:
        inventados = {t.lower() for f in csv.DictReader(fila)
                      for t in f['nombre'].split()}
    reales = {p.lower() for p in _palabras_reales()}
    assert not (inventados & reales), sorted(inventados & reales)


def test_la_nómina_real_nunca_entra_en_git():
    ignorados = (RAIZ / '.gitignore').read_text(encoding='utf-8')
    assert 'nomina/' in ignorados, 'la carpeta de la nómina real no está ignorada'


def test_las_reglas_sobre_personas_no_viven_en_el_código():
    """Una regla interna dice quién no coincide con quién, y **por qué**.

    Eso es asunto de la oficina. Estuvieron escritas en `internas.py` con
    nombres y apellidos hasta que el repositorio pasó a ser público; ahora se
    leen de un archivo que viaja con la nómina.
    """
    codigo = (RAIZ / 'gestor' / 'dominio' / 'internas.py').read_text(encoding='utf-8')
    assert 'reglas_internas.json' in codigo
    assert 'REGLAS: tuple[Regla, ...] = (' not in codigo, (
        'vuelven a estar escritas a mano en el código')


def test_de_fábrica_no_hay_ninguna_regla_interna(base):
    """Quien clone el proyecto no hereda las preferencias de esta oficina."""
    from gestor.dominio import internas

    assert internas.reglas_activas() == ()
