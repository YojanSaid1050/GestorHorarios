# -*- coding: utf-8 -*-
"""Los cambios que una persona decide a mano sobre un horario ya armado.

Un cambio manual **sobrevive a la siguiente generación**. Esa es toda la razón
de que se guarde en la base en vez de vivir dentro del horario: si al volver a
generar el mes desapareciera, el trabajo de revisar celda por celda se perdería
cada vez y nadie volvería a usar el editor.

Cuando el cambio se salta una regla, se guarda **qué regla se saltó y por qué**.
Sin eso, tres meses después nadie puede responder por qué ese domingo hay dos
personas del mismo turno; con eso, la respuesta está escrita al lado.

Se buscan **por período completo**, no por mes natural. Un cambio sobre el 1 de
octubre pertenece a la última semana de septiembre y también a octubre: guardado
bajo «octubre» desaparecía en cuanto se volvía a generar septiembre. Es el mismo
fallo que ya costó caro en solicitudes y asignaciones.
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from gestor.datos.base import abierta, transaccion
from gestor.dominio import calendario


def _fila(fila) -> dict:
    datos = dict(fila)
    datos['forzado'] = bool(datos.get('forzado'))
    datos['activo'] = bool(datos.get('activo', 1))
    datos['reglas'] = json.loads(datos.pop('reglas_json', None) or '[]')
    return datos


def listar(mes: Optional[int] = None, anio: Optional[int] = None,
           incluir_retirados: bool = False) -> list[dict]:
    condiciones = [] if incluir_retirados else ['a.activo=1']
    argumentos: list = []
    if mes and anio:
        inicio, fin = calendario.rango(int(mes), int(anio))
        condiciones.append('a.fecha BETWEEN ? AND ?')
        argumentos += [inicio.isoformat(), fin.isoformat()]
    donde = ('WHERE ' + ' AND '.join(condiciones)) if condiciones else ''
    with abierta() as conexion:
        filas = conexion.execute(
            f'SELECT a.*, e.nombre AS empleado_nombre, e.area AS area '
            f'FROM ajustes_manuales a JOIN empleados e ON e.id=a.empleado_id {donde} '
            'ORDER BY a.fecha, e.nombre', argumentos).fetchall()
    return [_fila(f) for f in filas]


def para_el_motor(mes: int, anio: int) -> list[dict]:
    """Los cambios vigentes del período, en la forma que el motor entiende."""
    return [{
        'empleado_id': int(a['empleado_id']),
        'fecha': str(a['fecha']),
        'turno': str(a['turno']),
        'forzar_total': bool(a['forzado']),
        'justificacion': str(a.get('justificacion') or ''),
        'reglas': list(a.get('reglas') or []),
        'origen_persistente': True,
        'ajuste_id': int(a['id']),
    } for a in listar(mes, anio)]


def guardar(empleado_id: int, fecha: str, turno: str, *, forzado: bool = False,
            justificacion: str = '', reglas: Iterable[str] = ()) -> int:
    """Deja escrito el cambio, y con él qué reglas se saltó y por qué.

    Guardar un cambio forzado sin justificación no se admite: la justificación
    **es** el cambio. Un turno raro sin explicación al lado es exactamente lo
    que nadie puede auditar después.
    """
    forzado = bool(forzado)
    justificacion = str(justificacion or '').strip()
    if forzado and len(justificacion) < 5:
        raise ValueError(
            'Un cambio que se salta una regla necesita un motivo escrito. '
            'Sin él, dentro de tres meses nadie podrá explicar por qué está ahí.')
    with transaccion() as conexion:
        cursor = conexion.execute(
            'INSERT INTO ajustes_manuales(empleado_id, fecha, turno, forzado, '
            'justificacion, reglas_json, activo) VALUES(?,?,?,?,?,?,1) '
            'ON CONFLICT(empleado_id, fecha) DO UPDATE SET '
            'turno=excluded.turno, forzado=excluded.forzado, '
            'justificacion=excluded.justificacion, reglas_json=excluded.reglas_json, '
            'activo=1',
            (int(empleado_id), str(fecha)[:10], str(turno), 1 if forzado else 0,
             justificacion, json.dumps(sorted(set(reglas)), ensure_ascii=False)))
        return int(cursor.lastrowid or 0)


def retirar(empleado_id: int, fecha: str) -> bool:
    """Devuelve ese día a automático. No borra: deja de aplicarse.

    Conservarlo desactivado permite responder «aquí hubo un cambio manual y se
    retiró el día tal», que es una pregunta que se hace de verdad.
    """
    with transaccion() as conexion:
        cursor = conexion.execute(
            'UPDATE ajustes_manuales SET activo=0 WHERE empleado_id=? AND fecha=? '
            'AND activo=1', (int(empleado_id), str(fecha)[:10]))
        return bool(cursor.rowcount)


def borrar_desde(fecha: str) -> int:
    with transaccion() as conexion:
        cursor = conexion.execute('DELETE FROM ajustes_manuales WHERE fecha>?',
                                  (str(fecha)[:10],))
        return int(cursor.rowcount or 0)
