# -*- coding: utf-8 -*-
"""Dos personas pulsando «aprobar» a la vez.

Aprobar una novedad son dos pasos: mirar con qué chocaría y, si no choca,
escribirla. Entre el primero y el segundo cabe otra petición que haga lo mismo,
y las dos se encuentran el terreno libre: dos solicitudes que se contradicen
quedan las dos aprobadas, cada una convencida de que era la única.

`BEGIN IMMEDIATE` no lo resuelve, y conviene saber por qué: serializa las
escrituras, no la pareja mirar-y-escribir. Las dos comprobaciones ya habían
pasado antes de que ninguna escribiera.
"""
from __future__ import annotations

import threading

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


def test_dos_aprobaciones_a_la_vez_no_dejan_las_dos_aprobadas(cliente):
    """El caso que el candado existe para impedir.

    Las dos solicitudes piden cosas distintas para el mismo día. Aprobadas por
    separado, la segunda se rechaza. Aprobadas a la vez, sin nada que
    serialice mirar-y-escribir, las dos pasaban.
    """
    persona = next(p for p in cliente.get('/api/empleados').json()
                   if not p.get('pareja_id'))
    unas = cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-14', 'fecha_fin': '2026-10-14'}).json()['id']
    otra = cliente.post('/api/solicitudes', json={
        'empleado_id': persona['id'], 'tipo': 'incapacidad',
        'fecha_inicio': '2026-10-14', 'fecha_fin': '2026-10-14'}).json()['id']

    resultados: dict[int, int] = {}
    listos = threading.Barrier(2)

    def aprobar(identificador: int) -> None:
        listos.wait()
        respuesta = cliente.patch(f'/api/solicitudes/{identificador}/aprobar')
        resultados[identificador] = respuesta.status_code

    hilos = [threading.Thread(target=aprobar, args=(x,)) for x in (unas, otra)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)

    aprobadas = [s for s in cliente.get('/api/solicitudes').json()
                 if int(s['id']) in (unas, otra) and s['estado'] == 'aprobada']
    assert len(aprobadas) == 1, (
        f'quedaron {len(aprobadas)} aprobadas para el mismo día; '
        f'las respuestas fueron {resultados}')
    assert sorted(resultados.values())[0] == 200
    assert sorted(resultados.values())[1] >= 400


def test_el_candado_se_puede_pedir_dos_veces_desde_el_mismo_hilo():
    """Reentrante a propósito.

    Una ruta que ya lo tiene puede llamar a otra que también lo pide —aprobar
    en grupo llama a aprobar— y quedarse esperándose a sí misma sería un
    cuelgue, no una protección.
    """
    from gestor.servicios import exclusion

    with exclusion.decidiendo(), exclusion.decidiendo():
        pass
