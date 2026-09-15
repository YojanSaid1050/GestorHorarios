# -*- coding: utf-8 -*-
"""Que lo que viaja traiga dentro lo que la pantalla lee.

`test_pantalla.py` comprueba que cada dirección que llama el JavaScript exista
en el servidor. No bastó, y esta es la prueba que faltaba.

Las direcciones estaban todas. Lo que no estaba era **el contenido**: la
respuesta llegaba con 200, con su `ok: true`, y sin la mitad de los campos que
la pantalla iba a leer. Y como el JavaScript los lee a la defensiva —`|| 0`,
`?? '—'`, `|| []`— no fallaba nada: enseñaba un cero, un guion o una lista vacía
**con la misma pinta que un dato de verdad**.

Así estuvo la aplicación entregada:

* la columna de horas del horario marcando «0 h» y «0 de —» para toda la
  oficina, mes tras mes, con las estadísticas bien calculadas y guardadas;
* Validación diciendo «Sin fallos ni advertencias» en meses que tenían nueve;
* la tabla de Personal con la columna «Turno base» en blanco para todos;
* tres de las cuatro rutas de «Archivos y datos» vacías;
* y cuatro botones de «Modificar horario» apagados para siempre, con el globo
  de ayuda diciendo que no había cambios pendientes mientras la pestaña de al
  lado avisaba de que sí los había.

Cuarenta agujeros, cero pruebas en rojo. Por eso esto se comprueba **campo a
campo contra el servidor de verdad**, y no leyendo el código.

## Cómo se mantiene

La lista de abajo es el contrato. Cuando la pantalla empiece a leer un campo
nuevo, se añade aquí. Es trabajo a mano, sí; el que no se hizo.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

#: Qué campos tiene que traer cada respuesta. `'@campo'` significa «en cada
#: elemento de la lista que devuelve», y `'alternativas[].campo'`, «en cada
#: elemento de esa lista de dentro».
CONTRATO = {
    ('GET', '/api/salud'): ('ok', 'version', 'edicion', 'problemas'),
    ('GET', '/api/empleados'): (
        '@id', '@nombre', '@area', '@tipo_turno', '@cobertura_texto',
        # Las dos columnas de la tabla de Personal que salían vacías.
        '@turno_base_mostrado', '@descanso_mostrado'),
    ('GET', '/api/configuracion/rutas'): (
        'programa', 'datos', 'base_de_datos', 'exportaciones', 'copias', 'registro'),
    ('GET', '/api/horarios/opciones/2026/9'): (
        'ok', 'cantidad', 'alternativas', 'oficial_id', 'publicado', 'publicado_id',
        'grupo_id', 'horario_actual', 'horario_publicado', 'hay_opciones_pendientes',
        # Lo que pinta la cuadrícula y las cinco columnas de la derecha.
        'alternativas[].horario_id', 'alternativas[].horario',
        'alternativas[].valido', 'alternativas[].oficial', 'alternativas[].publicado',
        'alternativas[].estadisticas', 'alternativas[].advertencias',
        'alternativas[].errores', 'alternativas[].validaciones',
        'alternativas[].resumen_validacion', 'alternativas[].reglas'),
    ('GET', '/api/configuracion/modo-app'): ('ok', 'modo', 'opciones'),
    ('GET', '/api/configuracion/tema-app'): ('ok', 'tema', 'opciones'),
    ('GET', '/api/configuracion/barra-ventana'): ('ok', 'propia', 'aviso'),
    ('GET', '/api/solicitudes'): ('@id', '@estado', '@estado_efectivo', '@aprobada'),
}

#: Campos de cada fila del horario que la cuadrícula pinta. `turno_base` va aquí
#: porque llegó a enseñar la palabra «null» en siete filas del mes de verdad.
CAMPOS_DE_UNA_FILA = ('empleado_id', 'nombre', 'area', 'turno_base', 'dias')

#: Y de cada persona en las estadísticas. Son las cinco columnas de la derecha.
CAMPOS_DE_UNA_ESTADISTICA = (
    'empleado_id', 'horas_mes', 'horas_periodo', 'domingos_trabajados',
    'festivos_trabajados', 'especiales_trabajados', 'objetivo_especiales')


@pytest.fixture
def cliente(carpeta_de_datos):
    from gestor.web.aplicacion import crear_aplicacion
    aplicacion = crear_aplicacion()
    with TestClient(aplicacion) as cliente:
        respuesta = cliente.post('/api/auth/login', json={
            'usuario': 'admin', 'password': 'xYojanSaidx1050'})
        assert respuesta.status_code == 200, respuesta.text
        cliente.headers['X-Session-Token'] = respuesta.json()['token']
        cliente.post('/api/horarios/generar', json={'mes': 9, 'anio': 2026})
        # Una novedad, para que la lista de solicitudes tenga algo que enseñar:
        # un contrato que se comprueba sobre una lista vacía no comprueba nada.
        personas = cliente.get('/api/empleados').json()
        cliente.post('/api/solicitudes', json={
            'empleado_id': personas[0]['id'], 'tipo': 'vacaciones',
            'fecha_inicio': '2026-09-10', 'fecha_fin': '2026-09-12'})
        yield cliente


def _hay(datos, campo: str) -> tuple[bool, str]:
    """¿Está ese campo? Devuelve también dónde se buscó, para el mensaje."""
    if campo.startswith('@'):
        if not isinstance(datos, list) or not datos:
            return False, 'la respuesta no es una lista con algo dentro'
        return campo[1:] in datos[0], 'en cada elemento'
    if '[].' in campo:
        lista_nombre, dentro = campo.split('[].', 1)
        lista = (datos or {}).get(lista_nombre)
        if not isinstance(lista, list) or not lista:
            return False, f'«{lista_nombre}» no trae nada'
        return dentro in lista[0], f'dentro de «{lista_nombre}»'
    return campo in (datos or {}), 'en la respuesta'


@pytest.mark.parametrize(('verbo', 'camino'), sorted(CONTRATO))
def test_la_respuesta_trae_lo_que_la_pantalla_lee(cliente, verbo, camino):
    """Un campo que falta aquí es un cero de mentira en la pantalla."""
    respuesta = cliente.request(verbo, camino)
    assert respuesta.status_code == 200, f'{camino} contestó {respuesta.status_code}'
    datos = respuesta.json()

    faltan = []
    for campo in CONTRATO[(verbo, camino)]:
        esta, donde = _hay(datos, campo)
        if not esta:
            faltan.append(f'{campo} ({donde})')
    assert not faltan, (
        f'{verbo} {camino} no manda: {", ".join(faltan)}.\n'
        '  La pantalla los lee igualmente y enseña un cero, un guion o una lista '
        'vacía en su lugar, sin que falle nada.')


def test_cada_fila_del_horario_trae_lo_que_pinta_la_cuadricula(cliente):
    datos = cliente.get('/api/horarios/opciones/2026/9').json()
    fila = datos['alternativas'][0]['horario'][0]
    faltan = [c for c in CAMPOS_DE_UNA_FILA if c not in fila]
    assert not faltan, f'a cada fila del horario le falta: {", ".join(faltan)}'


def test_ninguna_fila_del_horario_enseñaria_la_palabra_null(cliente):
    """La columna «Base» llegó a decir «null» en el mes de verdad de la oficina.

    Pasaba porque el turno base se calculaba de dos maneras distintas: el motor
    ponía «AM/PM» a quien rota, y la siembra de los meses transcritos copiaba
    `turno_fijo` a secas, que para quien rota vale `None`.
    """
    datos = cliente.get('/api/horarios/opciones/2026/9').json()
    for alternativa in datos['alternativas']:
        sin_base = [f['nombre'] for f in alternativa['horario']
                    if f.get('turno_base') in (None, '', 'null')]
        assert not sin_base, (
            'estas personas saldrían con «null» en la columna Base: '
            + ', '.join(sin_base))


def test_las_estadisticas_llegan_con_numeros_de_verdad(cliente):
    """Y no vacías, que es como la pantalla enseñaba 0 h para todo el mundo."""
    datos = cliente.get('/api/horarios/opciones/2026/9').json()
    alternativa = datos['alternativas'][0]
    estadisticas = alternativa['estadisticas']
    assert len(estadisticas) == len(alternativa['horario']), (
        'hay que mandar una estadística por persona; si no, la pantalla busca '
        'la suya, no la encuentra y pinta ceros')
    for persona in estadisticas:
        faltan = [c for c in CAMPOS_DE_UNA_ESTADISTICA if c not in persona]
        assert not faltan, f'{persona.get("nombre")}: falta {", ".join(faltan)}'
    assert any(p['horas_periodo'] for p in estadisticas), (
        'nadie trabaja ninguna hora en todo el período: eso no es un horario')


def test_la_pantalla_de_acceso_puede_pintarse_sin_haber_entrado(carpeta_de_datos):
    """El color y el modo se leen sin sesión, y solo se leen.

    Sin esto, la pantalla de acceso se quedaba sin los colores del tema. En
    oscuro eso dejaba su fondo **transparente** —la regla de CSS depende de dos
    variables que pone el JavaScript con esos datos— y la aplicación entera se
    veía por debajo, borrosa pero legible, con los nombres de la oficina a la
    vista sin que nadie hubiera entrado.
    """
    from gestor.web.aplicacion import crear_aplicacion
    with TestClient(crear_aplicacion()) as cliente:
        for camino in ('/api/configuracion/modo-app', '/api/configuracion/tema-app'):
            assert cliente.get(camino).status_code == 200, (
                f'{camino} pide sesión, y la pantalla de acceso lo necesita antes')
        # Y cambiarlo sigue pidiéndola: se abre para leer, no para tocar.
        assert cliente.put('/api/configuracion/modo-app',
                           json={'modo': 'oscuro'}).status_code == 401
