# -*- coding: utf-8 -*-
"""La aplicación por donde la usa la pantalla: entrar, pedir y que conteste bien.

Aquí no se comprueba el motor —para eso está `test_generacion.py`— sino el
contrato con la pantalla: qué hace falta para entrar, qué contesta cada
dirección y, sobre todo, **qué se dice cuando algo no se puede**. Un mensaje que
solo dice «no se puede» deja a quien lo lee sin nada que hacer.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

ADMIN = ('admin', 'xYojanSaidx1050')
OPERADORA = ('katerine', 'Kate2026*')


@pytest.fixture
def servidor(base):
    from gestor.servicios import reglas_cobertura, reglas_operacion
    reglas_cobertura.olvidar_lo_leido()
    reglas_operacion.invalidar_cache()
    from gestor.web.aplicacion import app
    with TestClient(app) as cliente:
        yield cliente


def _entrar(cliente, credenciales=ADMIN) -> dict:
    respuesta = cliente.post('/api/auth/login',
                             json={'usuario': credenciales[0], 'password': credenciales[1]})
    assert respuesta.status_code == 200, respuesta.text
    return {'X-Session-Token': respuesta.json()['token']}


@pytest.fixture
def admin(servidor):
    return _entrar(servidor)


# ------------------------------------------------------------------ la puerta

def test_la_salud_se_puede_preguntar_sin_entrar(servidor):
    """Es lo primero que carga la pantalla y lo primero que se pregunta al llamar."""
    datos = servidor.get('/api/salud').json()
    assert datos['ok'] is True
    assert datos['version']
    assert datos['problemas'] == []


def test_una_instalacion_nueva_no_arranca_con_problemas(servidor):
    assert servidor.get('/api/salud').json()['problemas'] == []


def test_sin_sesion_no_se_ve_nada(servidor):
    for camino in ('/api/empleados', '/api/solicitudes', '/api/operacion/auditoria'):
        respuesta = servidor.get(camino)
        assert respuesta.status_code == 401, camino
        assert 'Inicia sesión' in respuesta.json()['detail']


def test_las_cuentas_se_ofrecen_para_no_tener_que_escribirlas(servidor):
    """Son tres personas en una oficina, no un servicio público.

    Escribir mal el usuario era el motivo más común de «no me deja entrar».
    """
    cuentas = servidor.get('/api/auth/cuentas-login').json()['cuentas']
    assert {c['usuario'] for c in cuentas} == {'admin', 'katerine'}


def test_una_contrasena_equivocada_no_dice_de_mas(servidor):
    """El mismo mensaje que si el usuario no existiera.

    Decir cuál de las dos cosas falló es decirle a quien lo intenta qué usuarios
    hay.
    """
    uno = servidor.post('/api/auth/login', json={'usuario': 'admin', 'password': 'xxxxxxxx'})
    otro = servidor.post('/api/auth/login', json={'usuario': 'nadie', 'password': 'xxxxxxxx'})
    assert uno.status_code == otro.status_code == 401
    assert uno.json()['detail'] == otro.json()['detail']


def test_salir_invalida_la_sesion(servidor, admin):
    assert servidor.get('/api/empleados', headers=admin).status_code == 200
    servidor.post('/api/auth/logout', headers=admin)
    assert servidor.get('/api/empleados', headers=admin).status_code == 401


def test_la_operadora_trabaja_pero_no_toca_la_instalacion(servidor):
    """La diferencia entre perfiles es de responsabilidad, no de confianza.

    Si la operadora tuviera que pedir permiso para trabajar, acabaría usando la
    cuenta del administrador para todo y no habría perfiles.
    """
    cabeceras = _entrar(servidor, OPERADORA)
    assert servidor.get('/api/empleados', headers=cabeceras).status_code == 200
    assert servidor.get('/api/solicitudes', headers=cabeceras).status_code == 200

    prohibido = servidor.get('/api/auth/usuarios', headers=cabeceras)
    assert prohibido.status_code == 403
    assert 'administrador' in prohibido.json()['detail']


def test_no_hay_ninguna_puerta_trasera_para_las_pruebas():
    """La versión anterior tenía una variable de entorno que saltaba el acceso.

    Viajaba compilada dentro del ejecutable y ponerla era tan fácil como editar
    un acceso directo: con ella, cualquiera entraba como administrador y el
    historial dejaba de significar nada.
    """
    import ast
    import inspect

    from gestor.servicios import acceso

    fuente = inspect.getsource(acceso)
    arbol = ast.parse(fuente)
    sospechosas = [n for n in ast.walk(arbol)
                   if isinstance(n, ast.Attribute) and n.attr in ('getenv', 'environ')]
    assert not sospechosas, 'el acceso no puede depender de una variable de entorno'


# ------------------------------------------------------------------ personal

def test_se_listan_las_personas_con_su_cobertura_en_castellano(servidor, admin):
    gente = servidor.get('/api/empleados', headers=admin).json()
    assert len(gente) == 17
    assert all('cobertura_texto' in p for p in gente)
    assert gente[0]['cobertura_texto'] == 'todos los días'


def test_se_puede_dar_de_alta_a_alguien(servidor, admin):
    respuesta = servidor.post('/api/empleados', headers=admin, json={
        'nombre': 'Persona Nueva', 'area': 'gestion_social',
        'tipo_turno': 'fijo', 'turno_fijo': 'AM', 'alta_desde': '2026-10-01'})
    assert respuesta.status_code == 200, respuesta.text
    nombres = {p['nombre'] for p in servidor.get('/api/empleados', headers=admin).json()}
    assert 'Persona Nueva' in nombres


def test_un_alta_sin_nombre_se_rechaza_explicandolo(servidor, admin):
    respuesta = servidor.post('/api/empleados', headers=admin, json={
        'nombre': '   ', 'area': 'gestion_social', 'tipo_turno': 'fijo', 'turno_fijo': 'AM'})
    assert respuesta.status_code == 400
    assert 'nombre' in respuesta.json()['detail'].lower()


def test_un_turno_fijo_sin_franja_se_rechaza_explicandolo(servidor, admin):
    respuesta = servidor.post('/api/empleados', headers=admin, json={
        'nombre': 'Sin Franja', 'area': 'gestion_social', 'tipo_turno': 'fijo'})
    assert respuesta.status_code == 400
    assert 'mañana o de tarde' in respuesta.json()['detail']


def test_retirar_no_borra_y_lo_dice(servidor, admin):
    """Retirarse no es desaparecer, y el día importa.

    Esta prueba daba por bueno justo el fallo: retiraba con una fecha **futura**
    y exigía que la persona se fuera de la plantilla en ese mismo instante. Así
    era, y por eso el mes en curso se volvía a generar sin ella y sus turnos se
    repartían entre los demás semanas antes de que se marchara.

    Lo correcto son los dos casos: con la fecha aún por llegar sigue dentro, y
    con la fecha cumplida ya no. En los dos, su rastro se conserva.
    """
    gente = servidor.get('/api/empleados', headers=admin).json()
    # Sin pareja de PC: retirar a media pareja deshace el emparejamiento, y eso
    # se comprueba en `pruebas/test_auditoria.py`, no aquí.
    quien = next(p for p in gente if not p.get('pareja_id'))

    respuesta = servidor.post(f'/api/empleados/{quien["id"]}/retirar',
                              headers=admin,
                              json={'fecha_retiro': '2099-12-31',
                                    'motivo': 'renuncia'})
    assert respuesta.status_code == 200
    assert 'publicados' in respuesta.json()['mensaje']

    activos = {p['id'] for p in servidor.get('/api/empleados', headers=admin).json()}
    todos = {p['id'] for p in servidor.get(
        '/api/empleados?incluir_inactivos=true', headers=admin).json()}
    assert quien['id'] in activos, (
        'se fue de la plantilla el día que se registró el retiro, no el día del '
        'retiro: hasta esa fecha sigue trabajando y el horario la necesita')
    assert quien['id'] in todos

    # Y con la fecha ya cumplida, fuera.
    otro = next(p for p in gente
                if not p.get('pareja_id') and p['id'] != quien['id'])
    servidor.post(f'/api/empleados/{otro["id"]}/retirar', headers=admin,
                  json={'fecha_retiro': '2020-01-01', 'motivo': 'renuncia'})
    activos = {p['id'] for p in servidor.get('/api/empleados', headers=admin).json()}
    todos = {p['id'] for p in servidor.get(
        '/api/empleados?incluir_inactivos=true', headers=admin).json()}
    assert otro['id'] not in activos and otro['id'] in todos


def test_un_formulario_incompleto_se_explica_en_castellano(servidor, admin):
    """Sin esto llega «Field required», en inglés y con el nombre técnico."""
    respuesta = servidor.post('/api/empleados', headers=admin, json={'nombre': 'A'})
    assert respuesta.status_code == 422
    detalle = respuesta.json()['detail']
    assert 'falta' in detalle.lower()
    assert 'required' not in detalle.lower(), 'el mensaje sigue en inglés'


# --------------------------------------------------------------- el ciclo

@pytest.mark.lenta
def test_el_ciclo_completo_de_un_mes(servidor, admin):
    """Generar, elegir, publicar. Los cuatro pasos, en orden y sin saltarse ninguno."""
    generado = servidor.post('/api/horarios/generar', headers=admin,
                             json={'mes': 10, 'anio': 2026})
    assert generado.status_code == 200, generado.text
    datos = generado.json()
    assert datos['cantidad'] == 5
    assert datos['nombre_periodo'] == 'octubre de 2026'

    assert servidor.get('/api/horarios/oficial/2026/10',
                        headers=admin).json()['hay_oficial'] is False

    elegido = datos['alternativas'][0]['horario_id']
    assert servidor.patch(f'/api/horarios/{elegido}/oficial', headers=admin).status_code == 200
    assert servidor.get('/api/horarios/oficial/2026/10',
                        headers=admin).json()['hay_oficial'] is True

    # Se publica **la propuesta**, no «el mes»: es la que la oficina tiene en la
    # mano, y es lo que envía la pantalla.
    publicado = servidor.post(f'/api/operacion/publicacion/{elegido}', headers=admin,
                              json={'confirmar_excepciones': True})
    assert publicado.status_code == 200, publicado.text
    assert 'publicado' in publicado.json()['mensaje']

    estado = servidor.get('/api/operacion/periodo/2026/10', headers=admin).json()
    assert estado['publicado'] is True


@pytest.mark.lenta
def test_publicar_sin_elegir_se_explica(servidor, admin):
    """Publicar una propuesta que todavía no es la buena repartiría otro papel."""
    generado = servidor.post('/api/horarios/generar', headers=admin,
                             json={'mes': 10, 'anio': 2026}).json()
    sin_elegir = generado['alternativas'][0]['horario_id']
    respuesta = servidor.post(f'/api/operacion/publicacion/{sin_elegir}', headers=admin,
                              json={'confirmar_excepciones': True})
    assert respuesta.status_code == 400
    assert 'oficial' in respuesta.json()['detail']


def test_generar_un_mes_sin_el_anterior_dice_que_hacer(servidor, admin):
    """El caso que dejó un botón muerto durante una versión entera.

    Lo importante no es que se niegue: es que diga qué mes hay que preparar.
    """
    respuesta = servidor.post('/api/horarios/generar', headers=admin,
                              json={'mes': 12, 'anio': 2026})
    assert respuesta.status_code == 409
    detalle = respuesta.json()['detail']
    assert 'noviembre de 2026' in detalle
    assert 'marca como oficial' in detalle


def test_el_estado_del_periodo_dice_si_se_puede_generar(servidor, admin):
    """La pantalla lo pregunta para avisar antes, sin desactivar el botón.

    Desactivarlo fue el error de la versión anterior: el aviso era correcto y
    dejaba al usuario sin ninguna forma de insistir.
    """
    octubre = servidor.get('/api/operacion/periodo/2026/10', headers=admin).json()
    assert octubre['se_puede_generar'] is True and octubre['aviso'] == ''

    diciembre = servidor.get('/api/operacion/periodo/2026/12', headers=admin).json()
    assert diciembre['se_puede_generar'] is False
    assert 'noviembre de 2026' in diciembre['aviso']


def test_un_mes_imposible_se_rechaza(servidor, admin):
    respuesta = servidor.post('/api/horarios/generar', headers=admin,
                              json={'mes': 13, 'anio': 2026})
    assert respuesta.status_code == 400
    assert 'entre 1 y 12' in respuesta.json()['detail']


# --------------------------------------------------------------- las reglas

def test_las_reglas_de_cobertura_se_ven_y_se_explican(servidor, admin):
    datos = servidor.get('/api/configuracion/reglas-cobertura', headers=admin).json()
    assert {a['area'] for a in datos['areas']} == {
        'gestion_social', 'atencion_ciudadano', 'comunicaciones'}
    for area in datos['areas']:
        assert area['vigente'], f'{area["area"]} se quedaría sin regla vigente'
        assert area['vigente']['id'], 'la pantalla necesita poder señalar cuál borrar'
        assert area['nombre'] != area['area'], 'el área no se nombra en castellano'
    for area, frase in datos['nombres'].items():
        assert frase and frase != area, f'{area} no se explica en castellano'


def test_una_regla_con_un_minimo_negativo_se_rechaza(servidor, admin):
    respuesta = servidor.put('/api/configuracion/reglas-cobertura', headers=admin, json={
        'area': 'gestion_social', 'vigente_desde': '2026-11-01', 'am_minimo': -1})
    assert respuesta.status_code == 400
    assert 'negativo' in respuesta.json()['detail']


def test_no_se_puede_dejar_un_area_sin_ninguna_regla(servidor, admin):
    datos = servidor.get('/api/configuracion/reglas-cobertura', headers=admin).json()
    social = next(a for a in datos['areas'] if a['area'] == 'gestion_social')
    assert len(social['historial']) == 1, 'la prueba se apoya en que solo hay una'
    respuesta = servidor.delete(
        f'/api/configuracion/reglas-cobertura/{social["vigente"]["id"]}', headers=admin)
    assert respuesta.status_code == 400
    assert 'sin ninguna regla' in respuesta.json()['detail']


def test_los_festivos_del_ano_se_listan_con_los_movidos_marcados(servidor, admin):
    festivos = servidor.get('/api/configuracion/festivos?anio=2026', headers=admin).json()
    fechas = {f['fecha_original'] for f in festivos['festivos']}
    assert '2026-10-12' in fechas

    servidor.put('/api/configuracion/festivos', headers=admin, json={
        'fecha_original': '2026-10-12', 'fecha_nueva': '2026-10-13', 'nombre': 'Movido'})
    despues = servidor.get('/api/configuracion/festivos?anio=2026', headers=admin).json()
    movido = next(f for f in despues['festivos'] if f['fecha_original'] == '2026-10-12')
    assert movido['modificado'] is True and movido['fecha_efectiva'] == '2026-10-13'


# ------------------------------------------------------------- los reinicios

def test_reiniciar_pide_la_contrasena(servidor, admin):
    respuesta = servidor.post('/api/configuracion/reiniciar-programacion',
                              headers=admin, json={'mes': 10, 'anio': 2026})
    assert respuesta.status_code == 401
    assert 'contraseña' in respuesta.json()['detail']


def test_las_programaciones_base_no_se_reinician(servidor, admin):
    cabeceras = {**admin, 'X-User-Password': ADMIN[1]}
    respuesta = servidor.post('/api/configuracion/reiniciar-programacion',
                              headers=cabeceras, json={'mes': 9, 'anio': 2026})
    assert respuesta.status_code == 400
    assert 'programaciones base' in respuesta.json()['detail']


@pytest.mark.lenta
def test_reiniciar_borra_tambien_lo_que_reconstruye_el_mes(servidor, admin):
    """El fallo por el que reiniciar parecía no hacer nada.

    Los cambios manuales se vuelven a aplicar en cada generación: si sobreviven
    al reinicio, el mes que se genera después sale idéntico al que se borró.
    """
    from gestor.datos.base import abierta, transaccion

    servidor.post('/api/horarios/generar', headers=admin, json={'mes': 10, 'anio': 2026})
    with transaccion() as conexion:
        conexion.execute("INSERT INTO semanas(anio, mes, lunes, cerrada) "
                         "VALUES(2026,10,'2026-10-12',1)")
        conexion.execute("INSERT INTO ajustes_manuales(empleado_id, fecha, turno) "
                         "SELECT id,'2026-10-13','PM' FROM empleados LIMIT 1")

    cabeceras = {**admin, 'X-User-Password': ADMIN[1]}
    respuesta = servidor.post('/api/configuracion/reiniciar-programacion',
                              headers=cabeceras, json={'mes': 10, 'anio': 2026})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()['ajustes_manuales_eliminados'] == 1

    with abierta() as conexion:
        for tabla in ('horarios', 'ajustes_manuales', 'semanas'):
            quedan = conexion.execute(
                f'SELECT COUNT(*) n FROM {tabla} '
                f'{"WHERE anio=2026 AND mes=10" if tabla != "ajustes_manuales" else ""}'
            ).fetchone()['n']
            assert quedan == 0, f'sobrevivieron filas en {tabla}'


def test_reiniciar_no_toca_lo_que_pertenece_al_mes_anterior(servidor, admin):
    """Los períodos se solapan: el de septiembre llega hasta el 4 de octubre."""
    from gestor.datos.base import abierta, transaccion
    with transaccion() as conexion:
        conexion.execute("INSERT INTO ajustes_manuales(empleado_id, fecha, turno) "
                         "SELECT id,'2026-10-04','PM' FROM empleados LIMIT 1")

    cabeceras = {**admin, 'X-User-Password': ADMIN[1]}
    servidor.post('/api/configuracion/reiniciar-programacion',
                  headers=cabeceras, json={'mes': 10, 'anio': 2026})

    with abierta() as conexion:
        quedan = conexion.execute(
            "SELECT COUNT(*) n FROM ajustes_manuales WHERE fecha='2026-10-04'").fetchone()['n']
    assert quedan == 1, 'se borró un cambio manual que todavía pertenece a septiembre'


# ------------------------------------------------------------- el historial

def test_lo_que_se_hace_queda_anotado(servidor, admin):
    servidor.post('/api/empleados', headers=admin, json={
        'nombre': 'Anotada', 'area': 'comunicaciones', 'tipo_turno': 'rotativo'})
    registro = servidor.get('/api/operacion/auditoria', headers=admin).json()['historial']
    assert any(x['accion'] == 'alta_personal' for x in registro)
    assert any(x['detalle'].get('nombre') == 'Anotada' for x in registro)


def test_el_historial_no_lo_puede_vaciar_la_operadora(servidor):
    """Era el agujero más incómodo: podía borrar el registro de lo que hizo."""
    cabeceras = _entrar(servidor, OPERADORA)
    respuesta = servidor.request('DELETE', '/api/operacion/auditoria', headers=cabeceras)
    assert respuesta.status_code == 403
