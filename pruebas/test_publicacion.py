# -*- coding: utf-8 -*-
"""Lo que se revisa antes de repartir un horario.

Publicar es el único paso que no se deshace del todo: a partir de ahí la oficina
tiene el papel en la mano. La revisión existe para que nadie llegue ahí sin
haber visto qué está aceptando.

Lo que estas pruebas vigilan es la distinción que la versión anterior no hacía:

* un hueco que **este mes sí puede arreglar** impide publicar;
* un hueco que **viene de un mes ya publicado** se enseña y se acepta a
  sabiendas, porque ya ocurrió y no hay nada que corregir;
* una alerta de una **semana cerrada** solo se informa.

Confundir las tres fue lo que dejó el viernes 2 de octubre sin cobertura en
Atención al Ciudadano durante meses sin que apareciera en ninguna pantalla.
"""
from __future__ import annotations

import json

import pytest

from gestor.servicios import publicacion


@pytest.fixture
def sembrada(base):
    from gestor.servicios import siembra
    siembra.sembrar()
    return base


def _horario(filas, anio=2026, mes=10, **extra):
    return {'id': 1, 'anio': anio, 'mes': mes, 'oficial': 1, 'publicado': 0,
            'datos': {'horario': filas, 'errores': [], **extra}}


def _persona(identificador, nombre, area, dias, **extra):
    return {'empleado_id': identificador, 'nombre': nombre, 'area': area,
            'dias': dias, **extra}


def _dia(fecha, turno, **extra):
    return {'fecha': fecha, 'turno': turno, 'mes_propio': True, **extra}


# ------------------------------------------------------- lo que sí bloquea

def test_un_hueco_de_cobertura_de_este_mes_impide_publicar(sembrada):
    """Atención al Ciudadano necesita al menos una persona cubriendo turno."""
    guardado = _horario([
        _persona(1, 'Una', 'atencion_ciudadano', [_dia('2026-10-06', 'D')]),
        _persona(2, 'Otra', 'atencion_ciudadano', [_dia('2026-10-06', 'D')]),
    ])
    revision = publicacion.revisar(guardado)
    assert revision['conteos']['dias_sin_cobertura'] == 1
    assert revision['bloqueado'] is True
    assert revision['listo'] is False
    assert 'cubriendo turno' in revision['cobertura_sin_am_pm'][0]['detalle']


def test_la_jornada_administrativa_de_ac_no_tapa_el_hueco(sembrada):
    """ADM-AC es el horario propio del área: no releva a nadie.

    Contarlo como «alguien trabajando» hacía que un día en el que toda Atención
    al Ciudadano descansa salvo la administrativa pasara la revisión, que es
    justo el día que hay que denunciar.
    """
    guardado = _horario([
        _persona(1, 'Una', 'atencion_ciudadano', [_dia('2026-10-06', 'ADM-AC')]),
        _persona(2, 'Otra', 'atencion_ciudadano', [_dia('2026-10-06', 'D')]),
    ])
    assert publicacion.revisar(guardado)['conteos']['dias_sin_cobertura'] == 1


def test_la_administrativa_general_sí_cubre_su_propia_franja(sembrada):
    """ADM-GS conserva la franja que esa persona tenía: cambia lo que hace."""
    guardado = _horario([
        _persona(1, 'Una', 'atencion_ciudadano',
                 [_dia('2026-10-06', 'ADM-GS', cobertura_operativa='AM')]),
        _persona(2, 'Otra', 'atencion_ciudadano', [_dia('2026-10-06', 'D')]),
    ])
    assert publicacion.revisar(guardado)['conteos']['dias_sin_cobertura'] == 0


def test_un_festivo_trabajado_sin_compensatorio_se_denuncia(sembrada):
    guardado = _horario([
        _persona(1, 'Una', 'gestion_social',
                 [_dia('2026-10-12', 'AM', es_festivo=True), _dia('2026-10-13', 'AM')]),
    ])
    revision = publicacion.revisar(guardado)
    assert revision['conteos']['compensatorios_pendientes'] == 1
    assert 'compensatorio' in revision['compensatorios_pendientes'][0]['detalle']


def test_con_su_compensatorio_no_se_denuncia(sembrada):
    guardado = _horario([
        _persona(1, 'Una', 'gestion_social', [
            _dia('2026-10-12', 'AM', es_festivo=True),
            _dia('2026-10-13', 'D', origen='compensatorio_festivo',
                 festivo_origen='2026-10-12')]),
    ])
    assert publicacion.revisar(guardado)['conteos']['compensatorios_pendientes'] == 0


def test_una_pareja_en_el_mismo_turno_se_denuncia(sembrada):
    guardado = _horario([
        _persona(1, 'Una', 'gestion_social', [_dia('2026-10-06', 'AM')], pareja_id=2),
        _persona(2, 'Otra', 'gestion_social', [_dia('2026-10-06', 'AM')], pareja_id=1),
    ])
    revision = publicacion.revisar(guardado)
    assert revision['conteos']['conflictos_pc'] == 1
    assert 'coinciden' in revision['conflictos_pareja'][0]['detalle']


# ---------------------------------------------- lo que se acepta a sabiendas

def test_lo_heredado_se_informa_pero_no_bloquea(sembrada):
    """El fallo por el que el viernes 2 de octubre estuvo meses sin aparecer.

    Un día que viene de un mes ya publicado no se puede arreglar desde aquí,
    pero **sí se dice**. Callarlo era la versión anterior; bloquear por él
    dejaría octubre sin poder publicarse nunca.
    """
    guardado = _horario([
        _persona(1, 'Una', 'atencion_ciudadano',
                 [_dia('2026-10-02', 'D', origen='base_septiembre', heredado=True)]),
        _persona(2, 'Otra', 'atencion_ciudadano',
                 [_dia('2026-10-02', 'D', origen='base_septiembre', heredado=True)]),
    ])
    revision = publicacion.revisar(guardado)
    assert revision['bloqueado'] is False
    assert revision['conteos']['dias_sin_cobertura'] == 0
    assert len(revision['incidencias_aceptadas']) == 1
    aceptada = revision['incidencias_aceptadas'][0]
    assert aceptada['motivo'] == 'Viene de un mes ya publicado'
    assert '2026-10-02' in aceptada['detalle']
    assert revision['requiere_confirmacion'] is True, (
        'se enseña y se acepta a propósito, no se publica sin mirarlo')


def test_un_cambio_manual_autorizado_se_acepta_con_su_motivo(sembrada):
    guardado = _horario([
        _persona(1, 'Una', 'atencion_ciudadano',
                 [_dia('2026-10-06', 'D', excepcion_forzada=True,
                       justificacion='Lo pidió la coordinación')]),
        _persona(2, 'Otra', 'atencion_ciudadano', [_dia('2026-10-06', 'D')]),
    ])
    revision = publicacion.revisar(guardado)
    assert revision['bloqueado'] is False
    assert revision['excepciones_manuales'] == [
        'Una · 2026-10-06 · D · Lo pidió la coordinación']
    assert revision['requiere_confirmacion'] is True


def test_las_semanas_cerradas_solo_informan(sembrada, base):
    guardado = _horario([
        _persona(1, 'Una', 'atencion_ciudadano', [_dia('2026-10-06', 'D')]),
        _persona(2, 'Otra', 'atencion_ciudadano', [_dia('2026-10-06', 'D')]),
    ])
    with base.transaccion() as conexion:
        conexion.execute('INSERT INTO semanas(anio, mes, lunes, cerrada) '
                         'VALUES(2026, 10, ?, 1)', ('2026-10-05',))
    revision = publicacion.revisar(guardado)
    assert revision['conteos']['dias_sin_cobertura'] == 0
    assert len(revision['problemas_ignorados_semanas_bloqueadas']) == 1
    assert revision['bloqueado'] is False


# ------------------------------------------------------------- publicar

def _guardar(base, anio, mes, filas, oficial=1):
    with base.transaccion() as conexion:
        cursor = conexion.execute(
            'INSERT INTO horarios(anio, mes, datos_json, valido, oficial) '
            'VALUES(?,?,?,1,?)',
            (anio, mes, json.dumps({'horario': filas, 'errores': []}), oficial))
        return int(cursor.lastrowid)


def test_no_se_publica_una_propuesta_que_no_es_la_oficial(sembrada, base):
    identificador = _guardar(base, 2026, 10, [
        _persona(1, 'Una', 'gestion_social', [_dia('2026-10-06', 'AM')])], oficial=0)
    with pytest.raises(ValueError, match='horario oficial'):
        publicacion.publicar(identificador)


def test_publicar_limpio_no_pide_confirmar_nada(sembrada, base):
    identificador = _guardar(base, 2026, 10, [
        _persona(1, 'Una', 'gestion_social', [_dia('2026-10-06', 'AM')]),
        _persona(2, 'Otra', 'gestion_social', [_dia('2026-10-06', 'PM')]),
    ])
    resultado = publicacion.publicar(identificador)
    assert 'publicado' in resultado['mensaje']
    assert resultado['resumen']['publicado'] is True


def test_lo_que_hay_que_aceptar_se_confirma_expresamente(sembrada, base):
    identificador = _guardar(base, 2026, 10, [
        _persona(1, 'Una', 'atencion_ciudadano',
                 [_dia('2026-10-02', 'D', origen='base_septiembre', heredado=True)]),
        _persona(2, 'Otra', 'atencion_ciudadano',
                 [_dia('2026-10-02', 'D', origen='base_septiembre', heredado=True)]),
    ])
    with pytest.raises(ValueError, match='expresamente'):
        publicacion.publicar(identificador)
    resultado = publicacion.publicar(identificador, confirmar_excepciones=True)
    assert resultado['resumen']['publicado'] is True


def test_publicar_deja_al_día_el_mes(sembrada, base):
    """Publicar es rehacer la foto: los avisos de «conviene regenerar» sobran."""
    from gestor.servicios import periodos
    identificador = _guardar(base, 2026, 10, [
        _persona(1, 'Una', 'gestion_social', [_dia('2026-10-06', 'AM')]),
        _persona(2, 'Otra', 'gestion_social', [_dia('2026-10-06', 'PM')]),
    ])
    periodos.marcar(['2026-10-06'], 'algo cambió')
    assert periodos.estado(10, 2026)['desactualizado'] is True
    publicacion.publicar(identificador)
    assert periodos.estado(10, 2026)['desactualizado'] is False


def test_publicar_desplaza_al_anterior(sembrada, base):
    """Solo puede haber un horario publicado por mes: el que la gente tiene."""
    primero = _guardar(base, 2026, 10, [
        _persona(1, 'Una', 'gestion_social', [_dia('2026-10-06', 'AM')])])
    publicacion.publicar(primero)
    segundo = _guardar(base, 2026, 10, [
        _persona(1, 'Una', 'gestion_social', [_dia('2026-10-06', 'PM')])])
    publicacion.publicar(segundo)

    with base.abierta() as conexion:
        publicados = [int(f['id']) for f in conexion.execute(
            'SELECT id FROM horarios WHERE anio=2026 AND mes=10 AND publicado=1')]
    assert publicados == [segundo]
