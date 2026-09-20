# -*- coding: utf-8 -*-
"""Construir el instalador de Windows, de principio a fin.

Se ejecuta en Windows —o en el flujo de trabajo de GitHub, que usa Windows— y
hace tres cosas en este orden:

1. escribe la **ficha de versión** que Windows enseña en las propiedades del
   archivo, tomando el número de `gestor.version` y no de una copia a mano;
2. llama a **PyInstaller** con la receta de `gestor.spec`, que deja una carpeta
   con el ejecutable y todo lo que necesita;
3. llama a **`vpk pack`**, que envuelve esa carpeta en el instalador y en el
   paquete de actualización.

El número de versión sale de un solo sitio. En la aplicación anterior estaba
escrito a mano en ocho, y llegó a pasar que el instalador anunciaba una versión
y el programa decía otra.

Uso:

    python empaquetado/construir.py            # todo
    python empaquetado/construir.py --solo-exe # sin empaquetar el instalador
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'empaquetado'))

import plantilla  # noqa: E402

from gestor import credenciales, version  # noqa: E402
from gestor.version import REPOSITORIO_PRIVADO  # noqa: E402

SALIDA = RAIZ / 'dist' / 'GestorHorarios'
PAQUETES = RAIZ / 'dist' / 'instalador'

FICHA = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeros}, prodvers={numeros},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([StringTable('040a04b0', [
      StringStruct('CompanyName', '{autor}'),
      StringStruct('FileDescription', '{nombre}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{id}'),
      StringStruct('OriginalFilename', '{id}.exe'),
      StringStruct('ProductName', '{nombre}'),
      StringStruct('ProductVersion', '{version}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1034, 1200])])
  ]
)
"""


def escribir_ficha_de_version() -> Path:
    """La versión que Windows enseña en las propiedades del archivo.

    El idioma es 1034 —español de España— para que quien mire las propiedades
    en un equipo de la oficina las vea en su idioma y no en inglés.
    """
    mayor, menor, parche = version.numeros()
    destino = RAIZ / 'empaquetado' / 'version_windows.txt'
    destino.write_text(FICHA.format(
        numeros=(mayor, menor, parche, 0), version=version.VERSION,
        nombre=version.NOMBRE, autor=version.AUTOR, id=version.ID_APLICACION),
        encoding='utf-8')
    return destino


def correr(orden: list[str]) -> None:
    print('·', ' '.join(orden), flush=True)
    resultado = subprocess.run(orden, cwd=RAIZ)
    if resultado.returncode != 0:
        raise SystemExit(
            f'Falló: {" ".join(orden)}\n'
            f'(código {resultado.returncode}). No se ha empaquetado nada.')


def nombre_del_ejecutable() -> str:
    """Cómo se llama el archivo que sale, según dónde se esté construyendo.

    En Windows lleva `.exe` y en cualquier otro sitio no. Estaba escrito con el
    `.exe` a mano, así que al construir fuera de Windows —que es como se valida
    la receta antes de gastar una vuelta en la máquina buena— la compilación
    terminaba bien y este script decía que había fallado.
    """
    return version.ID_APLICACION + ('.exe' if sys.platform == 'win32' else '')


def carpeta_que_lee_el_programa() -> Path:
    """La carpeta desde la que el programa instalado lee sus archivos.

    No es la carpeta del ejecutable: PyInstaller deja todo lo que acompaña al
    programa en `_internal/`, y eso es lo que el programa ve como su raíz. Dejar
    el permiso un nivel más arriba —donde está el .exe, que es donde parece que
    va— lo pondría en un sitio donde nadie lo busca: el instalador saldría bien,
    el programa arrancaría bien, y no volvería a enterarse de una actualización.

    Se comprueba que la carpeta exista en vez de darla por hecha, porque si
    PyInstaller cambiara de disposición esto tiene que fallar aquí y no en el
    equipo de la oficina dentro de tres meses.
    """
    dentro = SALIDA / '_internal'
    if not dentro.is_dir():
        raise SystemExit(
            f'No está {dentro}. PyInstaller no dejó la carpeta donde el programa '
            'busca sus archivos, así que no se sabe dónde poner el permiso de '
            'actualizaciones.')
    return dentro


def poner_la_plantilla_de_la_oficina() -> bool:
    """Cambiar las dieciocho personas inventadas por las de verdad.

    El repositorio es público, así que lo que está escrito en él es una plantilla
    inventada. La real llega en el secreto `GESTOR_NOMINA` y se escribe aquí,
    después de construir y **antes** de empaquetar: los datos iniciales viajan
    dentro del programa.

    Sin el secreto se construye igual, con la gente inventada, y se dice en voz
    alta. Quien clone el proyecto tiene que poder compilarlo sin pedirle nada a
    nadie; lo que no puede pasar es publicar para la oficina una versión con
    dieciocho desconocidos dentro sin que nadie se entere.
    """
    puesta = plantilla.aplicar(carpeta_que_lee_el_programa())
    if puesta:
        print('Plantilla de la oficina puesta en el paquete')
    else:
        print('AVISO: se construye con la plantilla inventada. Este instalador no '
              'sirve para la oficina: no trae a su gente ni sus dos meses base.',
              file=sys.stderr)
    return puesta


#: El secreto del que sale el permiso de lectura para las actualizaciones.
#: Se escribe `token|AAAA-MM-DD`, con la fecha en que caduca.
VARIABLE_PERMISO = 'GESTOR_PERMISO'


def poner_el_permiso_de_actualizaciones() -> bool:
    """Escribir dentro del paquete el permiso con el que se buscan versiones.

    Con el repositorio privado, una copia instalada **no puede preguntar a
    GitHub si hay algo nuevo** sin identificarse: contesta que ese repositorio
    no existe —no que no hay permiso—, así que el programa se quedaría diciendo
    para siempre que ya está al día. Sin un error, sin un aviso, y sin que nadie
    lo note hasta que alguien pregunte por qué la oficina sigue con una versión
    de hace medio año.

    Esta función faltaba. `credenciales.Permiso.escribir()` estaba escrita desde
    el principio y no la llamaba nadie; `carpeta_que_lee_el_programa()` se
    escribió para esto —lo dice su propio docstring— y solo se usaba para la
    plantilla. Estaba todo hecho menos conectarlo.
    """
    crudo = os.environ.get(VARIABLE_PERMISO, '').strip()
    if not crudo:
        if REPOSITORIO_PRIVADO:
            raise SystemExit(
                f'Falta el secreto {VARIABLE_PERMISO} y el repositorio es privado. '
                'Sin él, la copia instalada no se enteraría nunca de una versión '
                'nueva. Escríbelo como «token|AAAA-MM-DD».')
        print('Sin permiso de actualizaciones, que con el repositorio público es '
              'lo normal')
        return False
    if '|' not in crudo:
        raise SystemExit(
            f'{VARIABLE_PERMISO} mal escrito. Va «token|AAAA-MM-DD», con la fecha '
            'en la que caduca el permiso.')
    token, caduca = (x.strip() for x in crudo.split('|', 1))
    destino = credenciales.Permiso.escribir(
        token, caduca, carpeta_que_lee_el_programa() / credenciales.ARCHIVO.name)
    print(f'Permiso de actualizaciones puesto en el paquete (caduca el {caduca})')
    return destino.is_file()


def construir_ejecutable() -> None:
    escribir_ficha_de_version()
    if SALIDA.exists():
        # Una carpeta vieja mezclada con la nueva deja archivos de dos versiones
        # conviviendo, y el que gana no siempre es el nuevo.
        shutil.rmtree(SALIDA)
    correr([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
            str(RAIZ / 'empaquetado' / 'gestor.spec')])

    ejecutable = SALIDA / nombre_del_ejecutable()
    if not ejecutable.is_file():
        raise SystemExit(f'PyInstaller terminó pero no dejó {ejecutable}.')

    # Lo que de verdad rompe una entrega no es que falte el ejecutable: es que
    # esté y le falte lo que necesita para arrancar. Se comprueba aquí, cuando
    # todavía se puede arreglar, y no en el equipo de la oficina.
    faltan = [str(c) for c in (
        SALIDA / '_internal' / 'gestor' / 'pantalla' / 'index.html',
        SALIDA / '_internal' / 'datos_iniciales' / 'empleados_iniciales.csv',
    ) if not c.is_file()]
    if faltan:
        raise SystemExit(
            'El ejecutable se construyó pero le faltan archivos que necesita '
            'para funcionar:\n  ' + '\n  '.join(faltan))
    # Después de comprobar la carpeta y antes de empaquetarla: los datos
    # iniciales viajan **dentro** del paquete.
    poner_la_plantilla_de_la_oficina()
    poner_el_permiso_de_actualizaciones()
    print(f'Ejecutable listo en {SALIDA}')
    autocomprobar()


def autocomprobar() -> None:
    """Arrancar el ejecutable recién hecho y preguntarle si está entero.

    Que los archivos estén no significa que el programa arranque, y hay una
    familia entera de fallos que solo se ve así: PyInstaller no encuentra una
    pieza que se carga por nombre, escribe una línea de error entre veinte mil de
    registro, **termina con éxito**, y el ejecutable no abre. Pasó con las piezas
    de uvicorn. Estuvo a punto de volver a pasar con `python-multipart`, que
    además cambió de nombre entre versiones.

    Comprobarlo aquí cuesta veinte segundos. No comprobarlo cuesta una vuelta
    entera y un instalador publicado que no abre.
    """
    ejecutable = SALIDA / nombre_del_ejecutable()
    print('\nComprobando el ejecutable recién construido…', flush=True)
    try:
        resultado = subprocess.run([str(ejecutable), '--comprobar'], cwd=SALIDA,
                                   capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as agotado:
        # Lo que llevara dicho antes de colgarse, que es lo único que dice dónde.
        #
        # Con `capture_output` no se ve nada hasta que el proceso termina, así
        # que un cuelgue dejaba en el registro de la publicación un `Traceback`
        # de Python y ni una línea de la comprobación: ni por dónde iba, ni qué
        # había pasado ya. La última línea que aparece aquí **es** la última que
        # llegó a pasar.
        def _texto(crudo) -> str:
            if not crudo:
                return ''
            return crudo if isinstance(crudo, str) else crudo.decode('utf-8', 'replace')

        print(_texto(agotado.stdout), end='')
        print(_texto(agotado.stderr), end='', file=sys.stderr)
        raise SystemExit(
            f'\nLa comprobación del ejecutable no terminó en {agotado.timeout:.0f} '
            'segundos y se ha parado. Lo de arriba es lo que llevaba dicho: la '
            'última línea es lo último que llegó a pasar.\nNo se empaqueta: un '
            'instalador que no abre es peor que ninguno.') from None
    print(resultado.stdout or '', end='')
    if resultado.returncode != 0:
        raise SystemExit(
            (resultado.stderr or '')[-1500:]
            + '\nEl ejecutable se construyó pero no pasa su propia comprobación. '
              'No se empaqueta: un instalador que no abre es peor que ninguno.')


def empaquetar() -> None:
    """`vpk pack`: el instalador y el paquete de actualización.

    `--packDir` es la carpeta entera, no el .exe suelto: Velopack necesita todo
    lo que acompaña al programa para poder reemplazar una versión por otra
    completa.
    """
    if shutil.which('vpk') is None:
        raise SystemExit(
            'No se encuentra «vpk». Instálalo con:\n'
            '    dotnet tool install -g vpk\n'
            'y vuelve a ejecutar esto.')
    PAQUETES.mkdir(parents=True, exist_ok=True)
    correr(['vpk', 'pack',
            '--packId', version.ID_APLICACION,
            '--packVersion', version.VERSION,
            '--packDir', str(SALIDA),
            '--mainExe', nombre_del_ejecutable(),
            '--packTitle', version.NOMBRE,
            '--packAuthors', version.AUTOR,
            '--outputDir', str(PAQUETES)])
    print(f'Instalador y paquete de actualización en {PAQUETES}')


def main() -> int:
    partes = argparse.ArgumentParser(description=__doc__)
    partes.add_argument('--solo-exe', action='store_true',
                        help='construir el ejecutable y parar ahí')
    opciones = partes.parse_args()

    if sys.platform != 'win32':
        print('Aviso: esto se construye en Windows. Fuera de Windows el ejecutable '
              'que salga no sirve para la oficina.', file=sys.stderr)

    print(f'{version.NOMBRE} {version.VERSION}')
    construir_ejecutable()
    if not opciones.solo_exe:
        empaquetar()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
