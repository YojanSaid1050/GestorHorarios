# -*- coding: utf-8 -*-
"""La plantilla de verdad de la oficina, que viaja fuera del repositorio.

El repositorio es público y dentro de esta aplicación viven los nombres, los
horarios y las reglas particulares de dieciocho personas. Lo que está escrito en
`datos_iniciales/` son dieciocho personas inventadas: sirve para que cualquiera
clone el proyecto y lo vea funcionar, y no dice nada de nadie.

Pero el instalador que llega a la oficina tiene que traer su gente. Si no, el
primer día habría que teclear dieciocho fichas y, peor, transcribir otra vez a
mano los dos meses base de agosto y septiembre, que son el punto de partida del
que cuelga todo lo demás.

Así que la plantilla real viaja en un **secreto del repositorio** y se aplica
justo antes de empaquetar. Conviene ver lo que esto **no** es:

* no es un token dentro del programa. El instalado no lleva ninguna credencial
  encima y no necesita identificarse para buscar versiones nuevas: el
  repositorio es público;
* no es un secreto contra quien tenga el programa. Quien lo instale verá la
  plantilla, claro: es la suya. Lo que se evita es que esté en internet, abierta,
  indexada y clonable por cualquiera.

## Cómo se prepara

En el equipo donde esté la carpeta `nomina/` —que está en `.gitignore`—:

    python empaquetado/plantilla.py --empaquetar

Escribe una línea larga en base64. Esa línea se guarda como el secreto
`GESTOR_NOMINA` del repositorio, y el flujo de publicación la aplica al
construir. La actualización opcional `GESTOR_BASE_SEPTIEMBRE` sustituye solo
el JSON de septiembre; conserva la plantilla original y agosto.

## Qué pasa si no está

La construcción de instaladores se detiene. Los datos inventados del repositorio
solo sirven como fixtures de desarrollo y pruebas; no son una alternativa para
la aplicación de la oficina. Para recuperar trabajo guardado se necesita una
base de datos o su copia: esta plantilla inicial no contiene las operaciones
posteriores del usuario.

"""
from __future__ import annotations

import argparse
import base64
import io
import os
import sys
import tarfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REAL = RAIZ / 'nomina'
VARIABLE = 'GESTOR_NOMINA'

#: La carpeta donde el programa busca sus datos iniciales. **Todo** va aquí
#: dentro, también las reglas internas.
#:
#: La primera versión de esto ponía las reglas en la raíz de la carpeta del
#: programa, que es donde parece que van, mientras el programa las busca en
#: `datos_iniciales/`. El instalador se construía, arrancaba y funcionaba, y las
#: reglas de la oficina no se aplicaban nunca: sin un error, sin un aviso. Es
#: exactamente el mismo sitio equivocado que ya se arregló una vez con el permiso
#: de actualizaciones, y por eso ahora es una condición comprobada y no una
#: costumbre.
DENTRO_DE = 'datos_iniciales/'

#: Lo que la plantilla real puede traer. Una lista cerrada a propósito: esto se
#: desempaqueta sobre el programa que se va a entregar, y un archivo cualquiera
#: colado ahí dentro acabaría dentro del instalador.
PERMITIDOS = {
    'datos_iniciales/empleados_iniciales.csv',
    'datos_iniciales/base_agosto_2026.json',
    'datos_iniciales/base_septiembre_2026.json',
    'datos_iniciales/exportaciones_registradas.json',
    'datos_iniciales/reglas_internas.json',
}

assert all(x.startswith(DENTRO_DE) for x in PERMITIDOS), (
    'todo lo que trae la plantilla tiene que ir en la carpeta donde el programa '
    'lo busca; fuera de ella se escribe, no falla nada y no se usa nunca')


def empaquetar(origen: Path = REAL) -> str:
    """La carpeta `nomina/` convertida en una línea que se pueda guardar."""
    if not origen.is_dir():
        raise SystemExit(f'No está {origen}. Es la carpeta con la plantilla real.')
    encontrados = sorted(
        str(p.relative_to(origen)).replace(os.sep, '/')
        for p in origen.rglob('*') if p.is_file())
    sobran = [x for x in encontrados if x not in PERMITIDOS]
    if sobran:
        raise SystemExit(
            'En la plantilla real hay archivos que no se esperan y que acabarían '
            'dentro del instalador:\n  ' + '\n  '.join(sobran))
    if 'datos_iniciales/empleados_iniciales.csv' not in encontrados:
        raise SystemExit('Falta datos_iniciales/empleados_iniciales.csv.')

    fardo = io.BytesIO()
    with tarfile.open(fileobj=fardo, mode='w:gz') as tar:
        for relativo in encontrados:
            tar.add(origen / relativo, arcname=relativo)
    return base64.b64encode(fardo.getvalue()).decode()


def aplicar(destino: Path, texto: str = '') -> bool:
    """Escribir la plantilla real encima de la inventada. Devuelve si lo hizo.

    `destino` es la carpeta del programa ya construido. Se escribe **después** de
    construir y antes de empaquetar: los datos iniciales viajan dentro del
    programa, así que tienen que estar en su sitio cuando `vpk` envuelve la
    carpeta.
    """
    texto = (texto or os.environ.get(VARIABLE, '')).strip()
    if not texto:
        return False
    try:
        fardo = io.BytesIO(base64.b64decode(texto))
    except Exception as fallo:                                     # noqa: BLE001
        raise SystemExit(f'El secreto {VARIABLE} no se pudo descifrar: {fallo}') from fallo

    with tarfile.open(fileobj=fardo, mode='r:gz') as tar:
        miembros = [m for m in tar.getmembers() if m.isfile()]
        sobran = [m.name for m in miembros if m.name not in PERMITIDOS]
        if sobran:
            raise SystemExit(
                f'El secreto {VARIABLE} trae archivos que no se esperan:\n  '
                + '\n  '.join(sobran))
        for miembro in miembros:
            salida = destino / miembro.name
            salida.parent.mkdir(parents=True, exist_ok=True)
            datos = tar.extractfile(miembro)
            if datos is not None:
                salida.write_bytes(datos.read())
    return True


def desempaquetar(texto: str = '', destino: Path = REAL) -> Path:
    """La operación contraria: de la línea en base64, otra vez a `nomina/`.

    Hace falta cuando se cambia de equipo o se pierde la carpeta. El secreto de
    GitHub **no se puede volver a leer** una vez guardado —eso es lo que lo hace
    un secreto—, así que la línea tiene que venir de donde se guardara: la
    variable de entorno, o pegada por la entrada estándar.

    Escribe en `nomina/`, que está en `.gitignore`. Nunca en `datos_iniciales/`,
    que sí está en git: esa confusión es de las que no se deshacen.
    """
    texto = (texto or os.environ.get(VARIABLE, '')).strip()
    if not texto and not sys.stdin.isatty():
        texto = sys.stdin.read().strip()
    if not texto:
        raise SystemExit(
            f'No hay nada que desempaquetar. Pon la línea en {VARIABLE} o pégala '
            f'por la entrada: python empaquetado/plantilla.py --desempaquetar < linea.txt')
    destino.mkdir(parents=True, exist_ok=True)
    aplicar(destino, texto)
    return destino


def main() -> int:
    partes = argparse.ArgumentParser(description=__doc__)
    partes.add_argument('--empaquetar', action='store_true',
                        help='escribir la plantilla real como una línea en base64')
    partes.add_argument('--desempaquetar', action='store_true',
                        help=f'reconstruir {REAL.name}/ desde esa línea')
    opciones = partes.parse_args()
    if opciones.desempaquetar:
        carpeta = desempaquetar()
        print(f'Plantilla real escrita en {carpeta}', file=sys.stderr)
        print('Esa carpeta está en .gitignore. No la copies a datos_iniciales/.',
              file=sys.stderr)
        return 0
    if not opciones.empaquetar:
        partes.print_help()
        return 1
    linea = empaquetar()
    print(linea)
    print(f'\n{len(linea)} caracteres. Guárdalo como el secreto {VARIABLE} del '
          'repositorio, en Settings → Secrets and variables → Actions.',
          file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
