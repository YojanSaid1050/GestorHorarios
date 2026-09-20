# -*- coding: utf-8 -*-
"""La copia de seguridad y, sobre todo, restaurarla.

Estas dos cosas se usan **el peor día**: alguien restaura una copia porque algo
ya salió mal. Un segundo problema justo ahí no es un fallo más, es el que deja a
la oficina sin el trabajo de meses y sin manera de recuperarlo.

Y no había ni una prueba. Restaurar estaba declarado como

    def restaurar(peticion: Request, archivo: str)

que en FastAPI significa «un dato escrito en la dirección», mientras la pantalla
mandaba el archivo subido. **Nunca funcionó**: contestaba «Falta “archivo”» y ya.
Nadie lo notó porque no había ningún camino que pasara por ese botón, ni en las
pruebas ni en la QA.

Se comprueban tres cosas, y la tercera es la que más importa:

* que la copia se cree y contenga lo que había;
* que restaurarla devuelva lo que se había perdido;
* que un archivo que no es una copia de este programa **no se aplique**.
  Restaurar sobrescribe la base entera: con una foto o un Excel por delante, el
  trabajo de la oficina se iría y la pantalla diría «restaurada correctamente».
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

ADMIN = ('admin', 'xYojanSaidx1050')


@pytest.fixture
def servidor(base):
    from gestor.servicios import reglas_cobertura, reglas_operacion
    reglas_cobertura.olvidar_lo_leido()
    reglas_operacion.invalidar_cache()
    from gestor.web.aplicacion import app
    with TestClient(app) as cliente:
        yield cliente


def _entrar(cliente) -> dict:
    respuesta = cliente.post('/api/auth/login',
                             json={'usuario': ADMIN[0], 'password': ADMIN[1]})
    return {'X-Session-Token': respuesta.json()['token'],
            'X-Admin-Password': ADMIN[1]}


def _copiar(cliente, cabeceras):
    respuesta = cliente.post('/api/operacion/backup', headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    from gestor import rutas
    return rutas.COPIAS / respuesta.json()['archivo'].split('/')[-1]


def _cuanta_gente(cliente, cabeceras) -> int:
    respuesta = cliente.get('/api/empleados', headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    return len(respuesta.json())


# ------------------------------------------------------------- crear la copia

def test_la_copia_se_crea_y_es_una_base_de_datos_de_verdad(servidor):
    cabeceras = _entrar(servidor)
    copia = _copiar(servidor, cabeceras)
    assert copia.is_file() and copia.stat().st_size > 1000

    # No basta con que exista un archivo: tiene que traer dentro lo que había.
    conexion = sqlite3.connect(copia)
    try:
        cuantos = conexion.execute('SELECT COUNT(*) FROM empleados').fetchone()[0]
    finally:
        conexion.close()
    assert cuantos > 0, 'la copia se creó vacía'


def test_la_copia_pide_la_contraseña_de_administrador(servidor):
    respuesta = servidor.post('/api/operacion/backup')
    assert respuesta.status_code in (401, 403)


# --------------------------------------------------------------- restaurarla

def test_restaurar_devuelve_lo_que_se_había_perdido(servidor):
    """El camino entero, tal como lo hace una persona: subiendo el archivo."""
    cabeceras = _entrar(servidor)
    antes = _cuanta_gente(servidor, cabeceras)
    copia = _copiar(servidor, cabeceras)

    from gestor.datos.base import transaccion
    with transaccion() as conexion:
        conexion.execute('DELETE FROM empleados')
    assert _cuanta_gente(servidor, cabeceras) == 0

    respuesta = servidor.post(
        '/api/operacion/restore', headers=cabeceras,
        files={'archivo': (copia.name, copia.read_bytes(), 'application/octet-stream')})
    assert respuesta.status_code == 200, respuesta.text

    # Y se vuelve a entrar, porque restaurar cierra todas las sesiones: las
    # fichas abiertas venían dentro de la copia y volvían a valer solas. Es lo
    # que el propio mensaje de la respuesta pide hacer.
    assert _cuanta_gente(servidor, _entrar(servidor)) == antes


def test_restaurar_guarda_antes_lo_que_había(servidor):
    """Restaurar no se deshace, así que lo de ahora se guarda primero.

    Es para el caso de siempre: la copia elegida no era la que se creía.
    """
    from gestor import rutas

    cabeceras = _entrar(servidor)
    copia = _copiar(servidor, cabeceras)
    servidor.post('/api/operacion/restore', headers=cabeceras,
                  files={'archivo': (copia.name, copia.read_bytes(),
                                     'application/octet-stream')})
    respaldos = list(rutas.COPIAS.glob('antes_de_restaurar_*.db'))
    assert len(respaldos) == 1, 'no quedó copia de lo que había antes de restaurar'


def test_un_archivo_que_no_es_una_copia_no_se_aplica(servidor):
    """La comprobación que evita el desastre de verdad.

    Alguien elige el archivo equivocado —una foto, un Excel, la copia de otro
    programa— y restaurar sobrescribe la base entera con él. Sin mirar antes qué
    trae dentro, el trabajo de la oficina se iría y la pantalla diría
    «restaurada correctamente».
    """
    cabeceras = _entrar(servidor)
    antes = _cuanta_gente(servidor, cabeceras)

    respuesta = servidor.post(
        '/api/operacion/restore', headers=cabeceras,
        files={'archivo': ('vacaciones.jpg', b'\xff\xd8\xff\xe0 esto es una foto',
                           'image/jpeg')})
    assert respuesta.status_code >= 400
    assert 'no es una copia de seguridad' in respuesta.json()['detail']
    assert _cuanta_gente(servidor, cabeceras) == antes, (
        'se aplicó un archivo que no era una copia')


def test_una_base_de_datos_de_otro_programa_tampoco(servidor, tmp_path):
    """SQLite válido, pero de otra cosa. Es el caso que más fácil se cuela."""
    ajena = tmp_path / 'otra_cosa.db'
    conexion = sqlite3.connect(ajena)
    conexion.execute('CREATE TABLE facturas(id INTEGER)')
    conexion.commit()
    conexion.close()

    cabeceras = _entrar(servidor)
    antes = _cuanta_gente(servidor, cabeceras)
    respuesta = servidor.post(
        '/api/operacion/restore', headers=cabeceras,
        files={'archivo': (ajena.name, ajena.read_bytes(), 'application/octet-stream')})
    assert respuesta.status_code >= 400
    assert 'empleados' in respuesta.json()['detail']
    assert _cuanta_gente(servidor, cabeceras) == antes


def test_un_archivo_vacío_se_rechaza_con_palabras(servidor):
    cabeceras = _entrar(servidor)
    respuesta = servidor.post(
        '/api/operacion/restore', headers=cabeceras,
        files={'archivo': ('copia.db', b'', 'application/octet-stream')})
    assert respuesta.status_code >= 400
    assert 'vacío' in respuesta.json()['detail']


def test_restaurar_pide_la_contraseña_de_administrador(servidor):
    """Es la operación más destructiva que hay: reemplaza la base entera."""
    copia = _copiar(servidor, _entrar(servidor))
    respuesta = servidor.post(
        '/api/operacion/restore',
        files={'archivo': (copia.name, copia.read_bytes(), 'application/octet-stream')})
    assert respuesta.status_code in (401, 403)


# ----------------------------------------------------- borrar el historial

def test_borrar_el_historial_pide_la_contraseña_y_borra_de_verdad(servidor):
    """Este botón tampoco había funcionado nunca.

    La ruta pide la contraseña de administrador y la pantalla no la mandaba, así
    que contestaba «La contraseña no es correcta» siempre. Y el texto de la
    confirmación prometía que los registros se conservaban «en la base para la
    trazabilidad técnica»: no es verdad, se borran. Alguien podía aceptar
    creyendo que el rastro quedaba, y el rastro es justo lo que se pierde.
    """
    cabeceras = _entrar(servidor)
    assert servidor.get('/api/operacion/auditoria',
                        headers=cabeceras).json()['historial']

    assert servidor.delete('/api/operacion/auditoria').status_code in (401, 403)

    respuesta = servidor.delete('/api/operacion/auditoria', headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    assert 'borradas' in respuesta.json(), (
        'la pantalla lee «borradas»; si cambia de nombre, dirá «undefined»')
    assert not servidor.get('/api/operacion/auditoria',
                            headers=cabeceras).json()['historial']


# ------------------------------- lo que se colaba aunque el archivo pareciera bueno

def test_una_base_con_las_tablas_de_aquí_y_las_columnas_de_otra_cosa(servidor, tmp_path):
    """El caso que se colaba entero: nombres correctos, dentro otra cosa.

    Se comprobaban solo los nombres de las tablas. Una base con `empleados`,
    `horarios`, `solicitudes` y `usuarios` —con un admin y alguna fila, para
    pasar las dos comprobaciones que sí había— pero con las columnas
    equivocadas se aceptaba con «ok», arrasaba la base de la oficina, y la
    primera pantalla que intentara leer la plantilla devolvía un 500. Queda la
    copia de antes, sí, pero quien restauró se encuentra con una instalación
    que no abre y un archivo que no sabe cómo devolver a su sitio.
    """
    falsa = tmp_path / 'parece_una_copia.db'
    conexion = sqlite3.connect(falsa)
    conexion.executescript("""
        CREATE TABLE empleados(id INTEGER PRIMARY KEY, apodo TEXT);
        CREATE TABLE horarios(id INTEGER PRIMARY KEY, cosa TEXT);
        CREATE TABLE solicitudes(id INTEGER PRIMARY KEY, cosa TEXT);
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY, rol TEXT);
        INSERT INTO empleados(apodo) VALUES('alguien');
        INSERT INTO usuarios(rol) VALUES('admin');
    """)
    conexion.commit()
    conexion.close()

    cabeceras = _entrar(servidor)
    antes = _cuanta_gente(servidor, cabeceras)
    respuesta = servidor.post(
        '/api/operacion/restore', headers=cabeceras,
        files={'archivo': (falsa.name, falsa.read_bytes(), 'application/octet-stream')})

    assert respuesta.status_code >= 400, respuesta.text
    assert 'columnas' in respuesta.json()['detail']
    assert _cuanta_gente(servidor, cabeceras) == antes, (
        'se aplicó una base que no era la de este programa')


def test_restaurar_cierra_las_sesiones_que_venían_dentro(servidor):
    """La tabla `sesiones` viaja en la copia, y con ella fichas ya cerradas.

    Al restaurar volvían a valer: cualquiera que tuviera guardada una de
    entonces volvía a estar dentro sin escribir nada. El mensaje ya pedía
    volver a entrar, pero era solo un texto y nada lo obligaba.
    """
    cabeceras = _entrar(servidor)
    copia = _copiar(servidor, cabeceras)

    respuesta = servidor.post(
        '/api/operacion/restore', headers=cabeceras,
        files={'archivo': (copia.name, copia.read_bytes(), 'application/octet-stream')})
    assert respuesta.status_code == 200, respuesta.text

    # La misma ficha con la que se acaba de restaurar ya no vale.
    assert servidor.get('/api/empleados', headers=cabeceras).status_code == 401


def test_restaurar_olvida_las_reglas_que_tenía_en_memoria(servidor):
    """Se leen una vez y se guardan en caché indexada por la ruta del archivo.

    Esa ruta no cambia al restaurar, así que después de volver a una copia de
    hace tres meses el programa seguía repartiendo con el tope de hoy, sin
    decirlo, hasta que alguien lo cerrara.
    """
    from gestor.servicios import reglas_operacion

    cabeceras = _entrar(servidor)
    copia = _copiar(servidor, cabeceras)
    reglas_operacion.regla()  # deja la caché llena
    assert reglas_operacion._CACHE, 'la caché no se llenó: la prueba no probaría nada'

    respuesta = servidor.post(
        '/api/operacion/restore', headers=cabeceras,
        files={'archivo': (copia.name, copia.read_bytes(), 'application/octet-stream')})
    assert respuesta.status_code == 200, respuesta.text

    assert not reglas_operacion._CACHE, (
        'las reglas de la base anterior siguen en memoria después de restaurar')
