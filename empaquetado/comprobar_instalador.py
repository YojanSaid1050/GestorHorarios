"""Prueba el asistente compilado y la instalación real en el runner Windows.

Primero sustituye el motor por un doble que no puede cerrar procesos ni escribir
fuera de su temporal. Solo si respeta el destino y rechaza todas las rutas
inválidas se permite ejecutar el instalador real. Uso exclusivo de CI desechable.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIAGNOSTICO = RAIZ / 'dist' / 'diagnostico' / 'instalador'
CLAVE = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\GestorHorarios'


def ejecutar(orden: list[str], entorno: dict[str, str], nombre: str,
             timeout: int = 180) -> int:
    with (DIAGNOSTICO / f'{nombre}-salida.log').open('w', encoding='utf-8') as salida:
        proceso = subprocess.Popen(orden, env=entorno, stdout=salida, stderr=salida)  # noqa: S603
        try:
            return proceso.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # El asistente puede estar esperando a un hijo: cerrar el árbol completo.
            subprocess.run(['taskkill', '/PID', str(proceso.pid), '/T', '/F'],  # noqa: S603,S607
                           capture_output=True, timeout=15, check=False)
            proceso.wait(timeout=15)
            raise


def probar(temporal: Path, estado: dict) -> None:
    import winreg

    sys.path.insert(0, str(RAIZ))
    from gestor.version import VERSION

    # No sobrescribir un registro preexistente, incluso en una máquina de CI.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE):
            pass
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError('El runner ya tiene GestorHorarios instalado; se requiere uno limpio.')
    casos = temporal / 'casos'
    casos.mkdir()
    datos = temporal / 'datos'
    datos.mkdir()
    testigo = datos / 'conservar-datos.txt'
    testigo.write_text('Estos datos deben conservarse.', encoding='utf-8')
    original = testigo.read_bytes()
    llamada = temporal / 'llamada.json'
    entorno = {**os.environ, 'GESTOR_DATOS': str(datos),
               'GESTOR_PRUEBA_RAIZ': str(casos), 'GESTOR_PRUEBA_LLAMADA': str(llamada)}
    compilador = shutil.which('ISCC')
    if not compilador:
        raise RuntimeError('No está disponible ISCC en PATH.')
    codigo = ejecutar([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                       '--onefile', '--name', 'MotorPrueba',
                       '--distpath', str(temporal / 'bin'),
                       '--workpath', str(temporal / 'build'),
                       '--specpath', str(temporal), str(RAIZ / 'empaquetado' / 'motor_prueba.py')],
                      entorno, 'construir-doble', timeout=240)
    if codigo:
        raise RuntimeError('No se pudo construir el doble inofensivo del motor.')
    codigo = ejecutar([compilador, f'/DVersionApp={VERSION}',
                       f'/DInstaladorBase={temporal / "bin" / "MotorPrueba.exe"}',
                       f'/O{temporal}', '/FAsistentePrueba',
                       str(RAIZ / 'empaquetado' / 'asistente.iss')], entorno, 'compilar-asistente')
    if codigo:
        raise RuntimeError('No se pudo compilar el asistente de prueba.')
    asistente = temporal / 'AsistentePrueba.exe'

    def instalar(exe: Path, destino: Path, nombre: str) -> int:
        return ejecutar([str(exe), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-',
                         '/TASKS=', f'/DIR={destino}',
                         f'/LOG={DIAGNOSTICO / (nombre + "-inno.log")}'], entorno, nombre)

    def caso(destino: Path, nombre: str, permitido: bool) -> None:
        llamada.unlink(missing_ok=True)
        codigo = instalar(asistente, destino, nombre)
        if permitido:
            if codigo or not llamada.is_file():
                raise RuntimeError(f'{nombre}: no se instaló en la carpeta solicitada ({codigo}).')
            recibido = Path(json.loads(llamada.read_text())['destino']).resolve()
            if recibido != destino.resolve():
                raise RuntimeError(f'{nombre}: el motor recibió otro destino: {recibido}')
        elif codigo == 0 or llamada.exists():
            raise RuntimeError(f'{nombre}: no se rechazó el destino antes de llamar al motor.')
        estado['casos'].append(nombre)
        print(f'Correcto: {nombre}', flush=True)

    elegido = casos / 'Carpeta con espacios y acentos á'
    caso(elegido, 'destino-elegido', True)
    caso(elegido, 'reinstalacion-reconocida', True)
    vacia = casos / 'Vacia'
    vacia.mkdir()
    caso(vacia, 'carpeta-vacia-existente', True)
    ocupada = casos / 'Documentos ajenos'
    ocupada.mkdir()
    archivo = ocupada / 'no-borrar.txt'
    archivo.write_text('conservar', encoding='utf-8')
    caso(ocupada, 'carpeta-ajena', False)
    if archivo.read_text(encoding='utf-8') != 'conservar':
        raise RuntimeError('Se alteró una carpeta ajena.')
    caso(Path(os.environ['WINDIR']), 'windows', False)
    caso(Path(os.environ['WINDIR']) / 'System32', 'system32', False)
    caso(Path(os.environ['PROGRAMFILES']), 'program-files', False)
    caso(Path(os.environ['USERPROFILE']), 'perfil', False)
    caso(Path(os.environ['LOCALAPPDATA']), 'localappdata', False)
    caso(datos, 'datos', False)
    caso(temporal, 'padre-de-datos', False)
    caso(Path(Path(os.environ['WINDIR']).anchor), 'raiz-disco', False)
    union = casos / 'Union'
    codigo = ejecutar(['cmd', '/c', 'mklink', '/J', str(union), os.environ['WINDIR']],
                      entorno, 'crear-union')
    if codigo:
        raise RuntimeError('No se pudo preparar el caso de unión de carpetas.')
    try:
        caso(union / 'Subcarpeta', 'union-a-windows', False)
    finally:
        # Eliminar solo el enlace, nunca recorrer su destino.
        union.rmdir()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLAVE) as clave:
        winreg.SetValueEx(clave, 'InstallLocation', 0, winreg.REG_SZ, os.environ['WINDIR'])
    try:
        caso(casos / 'Registro invalido', 'registro-invalido-ignorado', True)
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, CLAVE)

    # Solo se llega al motor real tras comprobar el mismo código Pascal con el doble.
    real = RAIZ / 'dist' / 'instalador' / f'GestorHorarios-Instalar-{VERSION}.exe'
    destino = casos / 'Gestor instalado'
    for nombre in ('instalacion-real', 'reinstalacion-real'):
        if instalar(real, destino, nombre):
            raise RuntimeError(f'Falló {nombre}; consulta el registro de Inno.')
        instalado = destino / 'current' / 'GestorHorarios.exe'
        if not instalado.is_file():
            raise RuntimeError('La aplicación no está en la ruta elegida.')
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE) as clave:
            registrada = Path(winreg.QueryValueEx(clave, 'InstallLocation')[0]).resolve()
        if registrada != destino.resolve():
            raise RuntimeError('La ruta registrada no coincide con la instalación de prueba.')
        if testigo.read_bytes() != original:
            raise RuntimeError('No se conservaron los datos externos.')
        estado['casos'].append(nombre)
    if ejecutar([str(instalado), '--comprobar-ventana'], entorno, 'ventana-instalada', timeout=100):
        raise RuntimeError('Falló la ventana del programa ya instalado.')
    informe = datos / 'comprobacion-ventana.json'
    if (not informe.is_file()
            or json.loads(informe.read_text(encoding='utf-8')).get('ok') is not True):
        raise RuntimeError('La ventana instalada no dejó un resultado válido.')
    shutil.copy2(informe, DIAGNOSTICO / informe.name)
    estado['casos'].append('ventana-instalada')
    estado['ok'] = True


def main() -> int:
    if sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true':
        print('Esta prueba instala en un runner Windows desechable de GitHub Actions.')
        return 2
    DIAGNOSTICO.mkdir(parents=True, exist_ok=True)
    estado = {'ok': False, 'casos': []}
    # El runner elimina esta carpeta al terminar. No recorrer instalaciones ni
    # enlaces al limpiar desde Python; conservarlos también facilita el diagnóstico.
    temporal = Path(tempfile.mkdtemp(prefix='gestor-instalador-', dir=os.environ['RUNNER_TEMP']))
    try:
        probar(temporal, estado)
    except Exception as exc:  # noqa: BLE001
        estado['error'] = str(exc)
        print(f'Error de aceptación del instalador: {exc}', flush=True)
    finally:
        registro = Path(os.environ['LOCALAPPDATA']) / 'GestorHorarios-datos' / 'instalacion.log'
        if registro.is_file():
            shutil.copy2(registro, DIAGNOSTICO / 'motor-instalacion.log')
        (DIAGNOSTICO / 'resultado.json').write_text(
            json.dumps(estado, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if estado['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
