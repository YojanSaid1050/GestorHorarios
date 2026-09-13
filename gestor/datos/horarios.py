# -*- coding: utf-8 -*-
"""Guardar y leer los horarios generados.

Cada generación deja **cinco propuestas** del mismo mes para poder compararlas.
Una de ellas se marca como oficial, y solo la oficial cuenta: es la que se
publica, la que hereda el mes siguiente y la que se mide.

Tres reglas que se imponen aquí y no en quien llama, porque dejarlas fuera fue
lo que permitió que una base quedara con dos oficiales del mismo mes:

* de un mes hay **como mucho una** propuesta oficial;
* marcar una como oficial **desmarca** a sus hermanas;
* publicar exige que antes esté marcada como oficial.
"""
from __future__ import annotations

import json
from typing import Optional

from gestor.datos.base import abierta, transaccion


def _como_dict(fila) -> dict:
    datos = json.loads(fila['datos_json'])
    return {
        'id': int(fila['id']),
        'anio': int(fila['anio']),
        'mes': int(fila['mes']),
        'grupo_id': fila['grupo_id'],
        'alternativa': int(fila['alternativa']),
        'oficial': bool(fila['oficial']),
        'publicado': bool(fila['publicado']),
        'fuente': str(fila['fuente']),
        'valido': bool(fila['valido']),
        'errores': json.loads(fila['errores_json'] or '[]'),
        'creado_en': fila['creado_en'],
        'publicado_en': fila['publicado_en'],
        'horario': datos.get('horario') or [],
        'datos': datos,
    }


def guardar_propuestas(anio: int, mes: int, grupo_id: str,
                       resultados: list[dict], fuente: str = 'generado') -> list[int]:
    """Guarda las propuestas de una generación y borra las anteriores del mes.

    Las propuestas viejas del mismo mes se van: si se quedaran, la pantalla
    mostraría una mezcla de dos generaciones y nadie sabría cuáles se pueden
    comparar entre sí. La que estuviera marcada como oficial **sí** se conserva,
    porque es la que la oficina ya tiene en la mano.
    """
    creados = []
    with transaccion() as conexion:
        conexion.execute(
            'DELETE FROM horarios WHERE anio=? AND mes=? AND oficial=0 AND publicado=0',
            (int(anio), int(mes)))
        for numero, resultado in enumerate(resultados, start=1):
            cursor = conexion.execute(
                'INSERT INTO horarios(anio, mes, datos_json, valido, errores_json, '
                'grupo_id, alternativa, fuente) VALUES(?,?,?,?,?,?,?,?)',
                (int(anio), int(mes),
                 json.dumps(resultado, ensure_ascii=False, default=str),
                 1 if resultado.get('valido') else 0,
                 json.dumps(resultado.get('errores') or [], ensure_ascii=False, default=str),
                 grupo_id, numero, fuente))
            creados.append(int(cursor.lastrowid))
    return creados


def propuestas(anio: int, mes: int) -> list[dict]:
    with abierta() as conexion:
        filas = conexion.execute(
            'SELECT * FROM horarios WHERE anio=? AND mes=? ORDER BY oficial DESC, alternativa',
            (int(anio), int(mes))).fetchall()
    return [_como_dict(f) for f in filas]


def obtener(horario_id: int) -> Optional[dict]:
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM horarios WHERE id=?', (int(horario_id),)).fetchone()
    return _como_dict(fila) if fila else None


def oficial(anio: int, mes: int) -> Optional[dict]:
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM horarios WHERE anio=? AND mes=? AND oficial=1 LIMIT 1',
            (int(anio), int(mes))).fetchone()
    return _como_dict(fila) if fila else None


def marcar_oficial(horario_id: int) -> dict:
    """Deja esa propuesta como la oficial del mes y desmarca a sus hermanas."""
    with transaccion() as conexion:
        fila = conexion.execute(
            'SELECT anio, mes FROM horarios WHERE id=?', (int(horario_id),)).fetchone()
        if fila is None:
            raise ValueError('Esa propuesta ya no existe.')
        conexion.execute(
            'UPDATE horarios SET oficial=0 WHERE anio=? AND mes=?',
            (int(fila['anio']), int(fila['mes'])))
        conexion.execute('UPDATE horarios SET oficial=1 WHERE id=?', (int(horario_id),))
    resultado = obtener(horario_id)
    assert resultado is not None
    return resultado


def quitar_oficial(anio: int, mes: int) -> None:
    """Deja el mes sin oficial, para poder elegir otra propuesta de cero.

    Se puede deshacer a propósito: marcar como oficial por error era, en la
    versión anterior, un camino sin vuelta que obligaba a reiniciar el mes.
    """
    with transaccion() as conexion:
        conexion.execute(
            'UPDATE horarios SET oficial=0, publicado=0, publicado_en=NULL '
            'WHERE anio=? AND mes=?', (int(anio), int(mes)))


def publicar(anio: int, mes: int) -> dict:
    elegido = oficial(anio, mes)
    if elegido is None:
        raise ValueError(
            'Antes de publicar hay que marcar una de las propuestas como oficial.')
    with transaccion() as conexion:
        conexion.execute(
            "UPDATE horarios SET publicado=1, publicado_en=datetime('now') WHERE id=?",
            (elegido['id'],))
    return obtener(elegido['id'])


def meses_con_horario() -> list[tuple[int, int]]:
    with abierta() as conexion:
        filas = conexion.execute(
            'SELECT DISTINCT anio, mes FROM horarios ORDER BY anio, mes').fetchall()
    return [(int(f['anio']), int(f['mes'])) for f in filas]


def borrar_desde(anio: int, mes: int) -> int:
    """Borra los horarios de ese mes en adelante. Devuelve cuántos."""
    with transaccion() as conexion:
        cursor = conexion.execute(
            'DELETE FROM horarios WHERE anio>? OR (anio=? AND mes>=?)',
            (int(anio), int(anio), int(mes)))
        return int(cursor.rowcount or 0)
