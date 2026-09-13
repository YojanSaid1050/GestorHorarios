# -*- coding: utf-8 -*-
"""Dejar constancia de quién hizo qué.

Es lo único que permite reconstruir por qué un mes salió como salió. Cuando
alguien pregunta «¿por qué esta persona libró ese jueves?», la respuesta casi
siempre está aquí: una solicitud aprobada, una asignación, un cambio de turno
con fecha.

Anotar **nunca puede tumbar la operación**. Si el historial falla, lo que estaba
haciendo el usuario sigue adelante y el fallo va al registro: perder una línea
de historial es malo, perder el trabajo del usuario por no poder anotarla es
mucho peor.
"""
from __future__ import annotations

import contextvars
import json
from typing import Optional

from gestor.datos.base import transaccion
from gestor.registro import obtener

#: Quién está haciendo la operación en curso. Se pone al entrar por la web y se
#: lee al anotar, para no tener que arrastrar el nombre por quince funciones.
actor_actual: contextvars.ContextVar[str] = contextvars.ContextVar('actor', default='')


def anotar(accion: str, entidad: str, detalle: Optional[dict] = None,
           actor: Optional[str] = None) -> None:
    try:
        with transaccion() as conexion:
            conexion.execute(
                'INSERT INTO historial(accion, entidad, actor, detalle_json) VALUES(?,?,?,?)',
                (str(accion), str(entidad), str(actor or actor_actual.get() or ''),
                 json.dumps(detalle or {}, ensure_ascii=False, default=str)))
    except Exception:                                              # noqa: BLE001
        obtener().exception('no se pudo anotar en el historial: %s/%s', accion, entidad)


def listar(limite: int = 300) -> list[dict]:
    from gestor.datos.base import abierta
    with abierta() as conexion:
        filas = conexion.execute(
            'SELECT * FROM historial ORDER BY creado_en DESC, id DESC LIMIT ?',
            (int(limite),)).fetchall()
    salida = []
    for fila in filas:
        item = dict(fila)
        try:
            item['detalle'] = json.loads(item.pop('detalle_json') or '{}')
        except Exception:                                          # noqa: BLE001
            item['detalle'] = {}
        salida.append(item)
    return salida


def vaciar() -> int:
    with transaccion() as conexion:
        cursor = conexion.execute('DELETE FROM historial')
        return int(cursor.rowcount or 0)
