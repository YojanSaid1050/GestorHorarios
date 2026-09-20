# -*- coding: utf-8 -*-
"""La contraseña que viene dentro del instalador no es una contraseña.

Las dos cuentas de fábrica y sus contraseñas están escritas en
`gestor/servicios/acceso.py`, y ese archivo viaja dentro del programa que se
instala en la oficina: quien abra el ejecutable las lee. Mientras nadie las
cambie, cualquiera que llegue a ese equipo entra como administrador y puede
autorizar un borrado de los que no tienen vuelta atrás.

La marca `requiere_cambio_clave` estaba en la tabla desde el principio, la
devolvía la sesión, y **no la ponía nadie ni la miraba nadie**. Estas pruebas
cubren las dos mitades que faltaban: ponerla y hacerle caso.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gestor.servicios import acceso

CLAVE_DE_FABRICA = acceso.ADMIN_INICIAL[2]
CLAVE_NUEVA = 'UnaClaveQueNadiePublico2026'


#: Este archivo es el único que quiere ver el comportamiento de verdad, así
#: que se sale del apaño que usan las demás pruebas (ver `conftest.py`).
pytestmark = pytest.mark.claves_de_fabrica


@pytest.fixture
def cliente(carpeta_de_datos):
    from gestor.web.aplicacion import crear_aplicacion
    with TestClient(crear_aplicacion()) as cliente:
        yield cliente


def _entrar(cliente, clave=CLAVE_DE_FABRICA):
    respuesta = cliente.post('/api/auth/login',
                             json={'usuario': 'admin', 'password': clave})
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    cliente.headers['X-Session-Token'] = datos['token']
    return datos['usuario']


def test_la_cuenta_de_fabrica_nace_marcada(cliente):
    assert _entrar(cliente)['requiere_cambio_clave'] is True


def test_con_la_clave_de_fabrica_no_se_puede_hacer_nada_mas(cliente):
    """Ni siquiera leer.

    Leer es lo que hay que impedir: lo que está detrás de esa puerta es la
    plantilla de la oficina con sus nombres y sus turnos.
    """
    _entrar(cliente)
    for verbo, camino in (('GET', '/api/empleados'),
                          ('GET', '/api/horarios/opciones/2026/10'),
                          ('GET', '/api/solicitudes'),
                          ('POST', '/api/horarios/generar')):
        respuesta = cliente.request(
            verbo, camino, json={'mes': 10, 'anio': 2026} if verbo == 'POST' else None)
        assert respuesta.status_code == 403, (
            f'{verbo} {camino} contestó {respuesta.status_code} con la '
            'contraseña de fábrica todavía puesta')
        assert 'contraseña' in respuesta.json()['detail']


def test_cambiarla_desbloquea_el_resto(cliente):
    _entrar(cliente)
    respuesta = cliente.put('/api/auth/password',
                            json={'actual': CLAVE_DE_FABRICA, 'nueva': CLAVE_NUEVA})
    assert respuesta.status_code == 200, respuesta.text

    usuario = _entrar(cliente, CLAVE_NUEVA)
    assert usuario['requiere_cambio_clave'] is False
    assert cliente.get('/api/empleados').status_code == 200


def test_una_instalacion_que_ya_existe_tambien_queda_marcada(cliente):
    """Que es donde está el problema de verdad.

    Marcar solo las cuentas nuevas no arregla nada en una oficina que lleva
    meses funcionando con las contraseñas de fábrica porque nunca se le pidió
    otra cosa.
    """
    from gestor.datos.base import transaccion

    # Se deja como estaba antes de que existiera la marca.
    with transaccion() as conexion:
        conexion.execute('UPDATE usuarios SET requiere_cambio_clave=0')
    assert _entrar(cliente)['requiere_cambio_clave'] is False

    assert acceso.marcar_las_claves_de_fabrica_que_siguen_puestas() >= 1
    assert _entrar(cliente)['requiere_cambio_clave'] is True


def test_a_quien_ya_la_cambio_no_se_le_toca(cliente):
    """Volver a marcarla sería echar a alguien que hizo lo correcto."""
    from gestor.datos.base import transaccion

    _entrar(cliente)
    cliente.put('/api/auth/password',
                json={'actual': CLAVE_DE_FABRICA, 'nueva': CLAVE_NUEVA})
    with transaccion() as conexion:
        conexion.execute("UPDATE usuarios SET requiere_cambio_clave=0 "
                         "WHERE usuario='admin'")

    acceso.marcar_las_claves_de_fabrica_que_siguen_puestas()

    assert _entrar(cliente, CLAVE_NUEVA)['requiere_cambio_clave'] is False


# --------------------------------------------------- probar a ciegas cuesta

def test_a_la_sexta_vez_seguida_hay_que_esperar(cliente):
    """Adivinar la contraseña a mano deja de ser gratis.

    No pretende parar un ataque serio —son tres personas en una oficina, no un
    servicio en internet—, sino que quien se siente delante del equipo ajeno no
    pueda probar las cien contraseñas de siempre en dos minutos.
    """
    acceso.olvidar_los_fallos()
    for numero in range(acceso.INTENTOS_ANTES_DE_ESPERAR):
        respuesta = cliente.post('/api/auth/login',
                                 json={'usuario': 'admin', 'password': 'no-es-esa'})
        assert respuesta.status_code == 401, (
            f'el intento {numero + 1} contestó {respuesta.status_code}')

    respuesta = cliente.post('/api/auth/login',
                             json={'usuario': 'admin', 'password': 'no-es-esa'})
    assert respuesta.status_code == 429, respuesta.text
    assert 'Espera' in respuesta.json()['detail']


def test_esperar_no_deja_fuera_a_quien_sí_la_sabe(cliente):
    """La espera es del que falla, no de la cuenta entera para siempre.

    Con la contraseña correcta todavía se entra hasta el momento en que empieza
    la espera; y una vez dentro, el contador se olvida.
    """
    acceso.olvidar_los_fallos()
    for _ in range(acceso.INTENTOS_ANTES_DE_ESPERAR - 1):
        cliente.post('/api/auth/login',
                     json={'usuario': 'admin', 'password': 'no-es-esa'})

    assert cliente.post('/api/auth/login',
                        json={'usuario': 'admin',
                              'password': CLAVE_DE_FABRICA}).status_code == 200

    # Y después de acertar se vuelve a empezar de cero: los cuatro fallos de
    # antes no cuentan contra el siguiente que se equivoque una vez.
    assert cliente.post('/api/auth/login',
                        json={'usuario': 'admin',
                              'password': 'no-es-esa'}).status_code == 401


def test_la_espera_es_por_cuenta_y_no_para_toda_la_oficina(cliente):
    """Que a alguien le cueste entrar no puede dejar a los demás fuera."""
    acceso.olvidar_los_fallos()
    for _ in range(acceso.INTENTOS_ANTES_DE_ESPERAR + 1):
        cliente.post('/api/auth/login',
                     json={'usuario': 'admin', 'password': 'no-es-esa'})

    assert cliente.post('/api/auth/login',
                        json={'usuario': 'admin',
                              'password': CLAVE_DE_FABRICA}).status_code == 429
    assert cliente.post('/api/auth/login',
                        json={'usuario': 'katerine',
                              'password': acceso.OPERADOR_INICIAL[2]}).status_code == 200
