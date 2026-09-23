# -*- coding: utf-8 -*-
"""Segunda tanda del informe: lo que se guarda a medias o sin dueño.

Seis fallos que se parecen en algo incómodo: la aplicación contesta que todo
fue bien. Uno deja una novedad aprobada encima de otra; otro deja tres personas
con una asignación y la respuesta es un error; otro retira a alguien con una
fecha que no es una fecha; otro recrea mañana a la persona a la que hoy se le
corrigió el nombre; otro avisa solo a una de las tres áreas; y el último apunta
en el registro qué se hizo pero nunca quién.
"""
from __future__ import annotations

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


def _alguien(cliente) -> dict:
    return next(p for p in cliente.get('/api/empleados').json()
                if not p.get('pareja_id'))


# ------------------ H12 · una novedad no se vuelve aprobada por la puerta de atrás

def test_una_novedad_que_nace_aprobada_pasa_el_mismo_control(cliente):
    """La casilla «ya aprobada» se saltaba la comprobación de choques entera.

    El control vivía dentro de `prevalidar`, que recibe el identificador de algo
    ya guardado, así que solo lo veía quien pulsaba «aprobar». Nacer aprobada
    hace exactamente lo mismo al horario y no pasaba por ahí.
    """
    persona = _alguien(cliente)
    primera = cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-12', 'fecha_fin': '2026-10-16', 'aprobada': True})
    assert primera.status_code == 200, primera.text

    segunda = cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'incapacidad',
        'fecha_inicio': '2026-10-14', 'fecha_fin': '2026-10-15', 'aprobada': True})
    assert segunda.status_code >= 400, (
        'se aprobaron unas vacaciones y una incapacidad para el mismo día')
    assert 'ya tiene aprobado' in segunda.text


def test_corregir_una_aprobada_tampoco_se_salta_el_control(cliente):
    """`actualizar_solicitud` no toca la columna `estado` a propósito.

    Así que una aprobada se podía mover de fechas encima de otra aprobada, sin
    dejar de estarlo y sin que nadie volviera a mirar.
    """
    persona = _alguien(cliente)
    cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-12', 'fecha_fin': '2026-10-16', 'aprobada': True})
    otra = cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'permiso',
        'fecha_inicio': '2026-10-26', 'fecha_fin': '2026-10-26', 'aprobada': True})
    identificador = otra.json()['id']

    movida = cliente.put(f'/api/solicitudes/{identificador}', json={
        'empleado_id': persona['id'], 'tipo': 'permiso',
        'fecha_inicio': '2026-10-14', 'fecha_fin': '2026-10-14'})
    assert movida.status_code >= 400, 'se movió un permiso aprobado dentro de unas vacaciones'
    assert 'ya tiene aprobado' in movida.text


# ----------------------------- H17 · una asignación masiva se guarda entera o nada

def test_una_asignación_masiva_con_alguien_que_no_existe_no_guarda_a_nadie(cliente):
    """Se guardaba persona a persona, cada una con su transacción.

    Si la cuarta fallaba, las tres primeras quedaban confirmadas y la respuesta
    era un error: quien lo leía no tenía forma de saber que tres personas sí la
    tenían puesta, ni cuáles.
    """
    gente = cliente.get('/api/empleados').json()
    antes = len(cliente.get('/api/requerimientos').json())

    respuesta = cliente.post('/api/requerimientos/masivo', json={
        'empleado_ids': [gente[0]['id'], gente[1]['id'], 999_999],
        'alcance': 'todos',
        'requerimiento': {'empleado_id': gente[0]['id'], 'tipo': 'asignacion_administrativa',
        'horario_administrativo': 'ADM-GS',
                          'fechas': ['2026-10-14']},
    })
    assert respuesta.status_code >= 400, respuesta.text
    assert len(cliente.get('/api/requerimientos').json()) == antes, (
        'quedaron asignaciones guardadas de una operación que falló')


# --------------------------------- H18 · cancelar un grupo avisa a todas sus áreas

def test_cancelar_un_grupo_de_varias_áreas_las_marca_todas(cliente):
    """Estaba escrito `afectadas[:1]`.

    Se cancelaba el grupo entero y solo se marcaba como desactualizada el área
    de la primera fila de la lista. Las demás se quedaban con un horario que ya
    no se corresponde con lo aprobado y sin nada que lo dijera.
    """
    import json

    from gestor.datos.base import transaccion
    from gestor.servicios import periodos

    # Los avisos solo se ponen en meses **ya generados**: avisar de que octubre
    # quedó viejo cuando octubre todavía no existe sería ruido. Se finge uno,
    # porque lo que se prueba aquí es la marca, no el reparto.
    with transaccion() as conexion:
        conexion.execute(
            'INSERT INTO horarios(anio, mes, datos_json, valido, grupo_id, oficial) '
            'VALUES(?,?,?,1,?,1)',
            (2026, 10, json.dumps({'horario': []}), '2026-10-prueba'))

    gente = cliente.get('/api/empleados').json()
    por_area = {}
    for persona in gente:
        por_area.setdefault(persona['area'], persona)
    if len(por_area) < 2:
        pytest.skip('la siembra no trae dos áreas')
    elegidas = list(por_area.values())[:2]

    creado = cliente.post('/api/requerimientos/masivo', json={
        'empleado_ids': [p['id'] for p in elegidas],
        'alcance': 'todos',
        'requerimiento': {'empleado_id': elegidas[0]['id'], 'tipo': 'asignacion_administrativa',
        'horario_administrativo': 'ADM-GS',
                          'fechas': ['2026-10-14']},
    })
    assert creado.status_code == 200, creado.text
    grupo = creado.json()['grupo_id']

    # Se limpia lo que dejó la creación, para ver solo lo que marca la cancelación.
    periodos.resolver(10, 2026, periodos.pendientes(10, 2026))
    for area in {p['area'] for p in elegidas}:
        periodos.resolver(10, 2026, periodos.pendientes(10, 2026, area=area), area=area)

    assert cliente.request(
        'PATCH', f'/api/requerimientos/grupo/{grupo}/cancelar').status_code == 200

    marcadas = set(periodos.estado(10, 2026)['areas'])
    assert marcadas == {p['area'] for p in elegidas}, (
        f'se marcaron {marcadas} de {[p["area"] for p in elegidas]}')


# ------------------------------------------- H22 · el registro dice también quién

def test_el_historial_guarda_quién_hizo_cada_cosa(cliente):
    """`actor_actual` existía, su comentario decía que se ponía al entrar, y no.

    Todas las anotaciones que no fueran de la pantalla de acceso se guardaban
    con el autor en blanco: el registro contaba qué pasó y no quién lo hizo, que
    es justo la mitad por la que se consulta.
    """
    persona = _alguien(cliente)
    cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'permiso',
        'fecha_inicio': '2026-10-14', 'fecha_fin': '2026-10-14'})

    registro = cliente.get('/api/operacion/auditoria').json()
    filas = registro if isinstance(registro, list) else registro.get('historial', registro)
    creacion = next(f for f in filas if f['accion'] == 'crear_solicitud')
    assert creacion['actor'], 'la anotación se guardó sin autor'
    assert 'admin' in creacion['actor']


# --------------------------------- H26 · una fecha de retiro inválida no retira

def test_una_fecha_de_retiro_inválida_no_llega_a_retirar_a_nadie(cliente):
    """Se comprobaba **después** de escribir.

    Se retiraba a la persona con el texto tal cual en `retirado_desde` y solo
    entonces se intentaba leer la fecha. El error saltaba, la respuesta era un
    fallo, y la persona se quedaba retirada con una fecha que no es una fecha.
    """
    persona = _alguien(cliente)
    respuesta = cliente.post(f'/api/empleados/{persona["id"]}/retirar',
                             json={'fecha_retiro': 'el mes que viene'})
    assert respuesta.status_code >= 400

    sigue = next(p for p in cliente.get('/api/empleados?incluir_retirados=true').json()
                 if int(p['id']) == int(persona['id']))
    assert sigue['activo'] is True, 'quedó retirada por una petición que falló'
    assert not sigue.get('retirado_desde')


# ----------------------------- H29 · renombrar a alguien no lo resucita al arrancar

def test_renombrar_a_alguien_no_lo_vuelve_a_crear_al_arrancar(carpeta_de_datos):
    """La siembra corre en cada arranque y la identidad era el nombre exacto.

    Corregirle una tilde a alguien hacía que al abrir el programa reapareciera
    la persona de antes: dos fichas para la misma persona, la nueva con su
    historia y la vieja recién nacida sin pareja.
    """
    from gestor.datos import personal
    from gestor.web.aplicacion import crear_aplicacion

    with TestClient(crear_aplicacion()):
        pass
    gente = personal.listar()
    cuantos = len(gente)
    alguien = next(p for p in gente if not p.get('pareja_id'))
    viejo = alguien['nombre']
    personal.actualizar(alguien['id'], {**alguien, 'nombre': viejo + ' (corregido)'})

    # Y se vuelve a abrir el programa, que es cuando pasaba.
    with TestClient(crear_aplicacion()):
        pass

    despues = personal.listar()
    assert len(despues) == cuantos, (
        f'la plantilla pasó de {cuantos} a {len(despues)} al reabrir')
    assert viejo not in {p['nombre'] for p in despues}
