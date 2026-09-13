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


# ------------------------------------------- lo que git se deja fuera

#: Lo que tiene que estar en el repositorio para que un `git clone` arranque.
CODIGO = ('gestor/**/*.py', 'pruebas/*.py', 'qa/*.py', 'empaquetado/*.py',
          'empaquetado/*.spec', 'gestor/pantalla/*.html', 'gestor/pantalla/*.css',
          'gestor/pantalla/js/*.js', 'datos_iniciales/*', 'requisitos.txt',
          'pyproject.toml')


def test_git_no_se_come_ningun_archivo_de_codigo():
    """La prueba que faltaba, escrita después de que pasara.

    `.gitignore` tenía `datos/` sin barra delante para no subir la carpeta de
    datos de una instalación de desarrollo. En git, un nombre sin barra se ignora
    **en cualquier nivel**, y el paquete `gestor/datos/` se llama igual: los seis
    archivos de SQLite y del esquema nunca se subieron.

    En el equipo donde se escribió todo funcionaba, porque los archivos estaban en
    el disco. Lo que salió publicado no arrancaba, y no se supo hasta que la
    publicación se paró en las pruebas con «No module named gestor.datos».

    Esto no se puede detectar leyendo el código ni ejecutándolo: hay que
    preguntarle a git. Se le pregunta por todo de una vez, y no por una lista de
    carpetas sospechosas, porque la próxima vez será otro nombre.
    """
    import subprocess

    archivos = sorted({str(p.relative_to(RAIZ)).replace('\\', '/')
                       for patrón in CODIGO for p in RAIZ.glob(patrón)
                       if p.is_file() and '__pycache__' not in p.parts})
    assert len(archivos) > 80, f'solo se encontraron {len(archivos)} archivos que mirar'

    ignorados = subprocess.run(
        ['git', 'check-ignore', '--stdin'], cwd=RAIZ, text=True,
        input='\n'.join(archivos), capture_output=True)
    fuera = [x for x in ignorados.stdout.splitlines() if x.strip()]
    assert not fuera, (
        'git deja fuera del repositorio archivos de código, y quien lo clone no '
        'podrá arrancarlo:\n  ' + '\n  '.join(fuera))


def test_todo_lo_que_importa_el_programa_esta_seguido_por_git():
    """Al revés que la anterior: no qué se ignora, sino qué está registrado.

    Un archivo puede quedarse fuera sin que `.gitignore` lo mencione —recién
    creado y sin añadir—, y el efecto es el mismo: en este equipo funciona y en
    un clon no existe.
    """
    import subprocess

    seguidos = set(subprocess.run(
        ['git', 'ls-files'], cwd=RAIZ, text=True,
        capture_output=True).stdout.splitlines())
    if not seguidos:
        pytest.skip('esto no es un repositorio de git')

    faltan = []
    for archivo in (RAIZ / 'gestor').rglob('*.py'):
        relativo = str(archivo.relative_to(RAIZ)).replace('\\', '/')
        if '__pycache__' in archivo.parts:
            continue
        if relativo not in seguidos:
            faltan.append(relativo)
    assert not faltan, (
        'estos archivos del programa no están en git:\n  ' + '\n  '.join(faltan))
