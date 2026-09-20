# -*- coding: utf-8 -*-
"""Los cuatro fallos graves que encontró la auditoría, y que no pueden volver.

Cada uno se vio reproduciéndolo contra la aplicación de verdad, no leyendo el
código. Los cuatro tienen la misma forma: la aplicación contesta que todo fue
bien y por dentro ha perdido algo.
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cliente(carpeta_de_datos):
    from gestor.web.aplicacion import crear_aplicacion
    with TestClient(crear_aplicacion()) as cliente:
        respuesta = cliente.post('/api/auth/login', json={
            'usuario': 'admin', 'password': 'xYojanSaidx1050'})
        cliente.headers['X-Session-Token'] = respuesta.json()['token']
        yield cliente


# ------------------------------------------------------- M01 · retiro futuro

def test_quien_se_retira_el_mes_que_viene_sigue_en_la_plantilla(cliente):
    """Un retiro se avisa con semanas; hasta el día, esa persona trabaja.

    `retirar()` marca `activo=0` en el acto —así queda escrito que la salida
    está decidida— y eso la sacaba de la plantilla al instante. El mes en curso
    se volvía a generar sin ella y sus turnos se repartían entre los demás. El
    motor sabe dejarla en NV a partir del día exacto; el problema era que nunca
    la recibía.
    """
    gente = cliente.get('/api/empleados').json()
    alguien = next(p for p in gente if not p.get('pareja_id'))

    cliente.post(f'/api/empleados/{alguien["id"]}/retirar',
                 json={'fecha_retiro': '2099-12-31'})

    siguen = {p['id'] for p in cliente.get('/api/empleados').json()}
    assert alguien['id'] in siguen, (
        'se fue de la plantilla el día que se registró el retiro, no el día del '
        'retiro: el horario se rehace sin esa persona')


# --------------------------------------------------- M02 · pareja que se queda

def test_retirar_a_media_pareja_no_deja_el_mes_en_blanco(cliente):
    """Nadie puede quedarse apuntando a quien ya no está.

    Quien se quedaba huérfano dejaba una pareja a medias, la comprobación de
    parejas la daba por rota, y el mes entero salía con **cero filas** —sin una
    sola persona— y aun así se podía marcar como oficial y publicar. El mes
    siguiente partía de ese vacío.
    """
    gente = cliente.get('/api/empleados').json()
    uno = next(p for p in gente if p.get('pareja_id'))

    cliente.post(f'/api/empleados/{uno["id"]}/retirar',
                 json={'fecha_retiro': '2026-09-01'})

    despues = cliente.get('/api/empleados?incluir_inactivos=true').json()
    huerfanas = [p['nombre'] for p in despues if p.get('pareja_id') == uno['id']]
    assert not huerfanas, f'siguen emparejadas con quien se fue: {huerfanas}'

    respuesta = cliente.post('/api/horarios/generar', json={'mes': 10, 'anio': 2026})
    assert respuesta.status_code == 200, respuesta.text
    propuesta = respuesta.json()['alternativas'][0]
    assert propuesta['horario'], 'el mes salió sin una sola persona dentro'


def test_una_propuesta_sin_nadie_no_se_ofrece_como_propuesta(cliente):
    """Y si la plantilla no cuadra, se dice qué pasa en vez de ofrecer el vacío.

    Cuando la configuración no cuadra, el motor contesta con el horario vacío y
    el motivo dentro. Eso se guardaba como propuesta, cinco veces, y la pantalla
    invitaba a marcar una como oficial.
    """
    gente = cliente.get('/api/empleados').json()
    rotativo = next(p for p in gente if p['tipo_turno'] == 'rotativo')
    # Se le quita el lunes de referencia: configuración rotativa incompleta.
    from gestor.datos.base import transaccion
    with transaccion() as conexion:
        conexion.execute(
            'UPDATE empleados SET fecha_ancla_rotacion=NULL, inicio_rotacion=NULL '
            'WHERE id=?', (rotativo['id'],))

    respuesta = cliente.post('/api/horarios/generar', json={'mes': 10, 'anio': 2026})
    assert respuesta.status_code != 200, 'ofreció propuestas vacías como si valieran'
    detalle = respuesta.json()['detail']
    assert rotativo['nombre'] in detalle and 'Personal' in detalle, (
        f'no dice a quién le falta qué ni dónde arreglarlo: {detalle}')


# ------------------------------------------------ D01 · la fecha de alta

def test_corregir_una_ficha_no_reescribe_la_fecha_de_alta(cliente):
    """«Rige desde» no es «entró el».

    Corregirle el turno a alguien poniendo que rige desde noviembre le cambiaba
    el alta de agosto a noviembre y la borraba de todos los meses anteriores.
    Un mes ya entregado cambiaba solo por haber corregido una ficha.
    """
    gente = cliente.get('/api/empleados').json()
    alguien = next(p for p in gente if p['tipo_turno'] == 'fijo')
    alta = alguien['alta_desde']
    assert alta, 'la prueba necesita alguien con fecha de alta'

    ficha = {**alguien, 'vigente_desde': '2026-11-16',
             'observacion': 'corrección de prueba'}
    ficha.pop('pareja_id', None)
    respuesta = cliente.put(f'/api/empleados/{alguien["id"]}', json=ficha)
    assert respuesta.status_code == 200, respuesta.text

    despues = next(p for p in cliente.get('/api/empleados').json()
                   if p['id'] == alguien['id'])
    assert despues['alta_desde'] == alta, (
        f'la fecha de alta pasó de {alta} a {despues["alta_desde"]}: esa persona '
        'desaparece de todos los meses anteriores')


# ------------------------------------------- D03 · una copia que no lo es

def test_no_se_restaura_un_archivo_que_dejaria_sin_cuentas(cliente, tmp_path):
    """Comprobar tres nombres de tabla no basta.

    Se aceptaba cualquier archivo que los tuviera, aunque estuvieran vacíos: se
    arrasaba la base de la oficina y la aplicación quedaba **sin una sola
    cuenta**. Nadie podía volver a entrar, y desde fuera no hay forma de
    deshacerlo.
    """
    impostora = tmp_path / 'parece_una_copia.db'
    conexion = sqlite3.connect(impostora)
    for tabla in ('empleados', 'horarios', 'solicitudes'):
        conexion.execute(f'CREATE TABLE {tabla}(id INTEGER PRIMARY KEY)')
    conexion.commit()
    conexion.close()

    with impostora.open('rb') as archivo:
        respuesta = cliente.post(
            '/api/operacion/restore',
            files={'archivo': ('parece_una_copia.db', archivo,
                               'application/octet-stream')},
            headers={'X-Admin-Password': 'xYojanSaidx1050'})
    assert respuesta.status_code >= 400, 'la aceptó y se llevó la base por delante'
    assert 'cuenta' in respuesta.json()['detail'], respuesta.json()['detail']

    # Y sobre todo: no tocó nada.
    assert cliente.post('/api/auth/login', json={
        'usuario': 'admin', 'password': 'xYojanSaidx1050'}).status_code == 200
    assert cliente.get('/api/empleados').json(), 'se quedó sin plantilla'
