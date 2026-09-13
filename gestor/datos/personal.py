# -*- coding: utf-8 -*-
"""Leer y escribir el personal.

Una decisión que se ve aquí y explica media aplicación: **la configuración de
una persona tiene fecha de vigencia**. Cambiar hoy el turno de alguien no puede
reescribir los meses que ya se publicaron con la configuración anterior; lo que
hace es abrir un tramo nuevo desde el lunes que se indique. Por eso además de la
ficha actual hay un historial, y el motor pide siempre «cómo estaba esta persona
en tal fecha».

Sin eso, corregir el turno de una persona en noviembre cambiaba retroactivamente
agosto, septiembre y octubre, y la oficina veía cómo un horario ya repartido
dejaba de coincidir con el papel que tenía en la pared.
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from gestor.datos.base import abierta, transaccion
from gestor.dominio.cobertura import a_texto, desde_texto

#: El orden en que se muestran y se recorren. No es capricho: el motor reparte
#: en este orden y, sin un orden estable, dos generaciones del mismo mes con los
#: mismos datos podían salir distintas.
ORDEN = (
    "CASE area WHEN 'gestion_social' THEN 1 WHEN 'atencion_ciudadano' THEN 2 "
    "WHEN 'comunicaciones' THEN 3 ELSE 9 END, orden_rotacion, id"
)

CAMPOS = (
    'nombre', 'cargo', 'area', 'tipo_turno', 'turno_fijo', 'descanso_fijo',
    'pareja_id', 'inicio_rotacion', 'fecha_ancla_rotacion', 'orden_rotacion',
    'exento_especiales', 'es_nuevo', 'cobertura_dias_json', 'activo',
    'alta_desde', 'retirado_desde',
)


def _como_dict(conexion, fila) -> dict:
    persona = dict(fila)
    persona['activo'] = bool(persona.get('activo', 1))
    persona['exento_especiales'] = bool(persona.get('exento_especiales', 0))
    persona['es_nuevo'] = bool(persona.get('es_nuevo', 0))
    # Se guarda como texto y se devuelve como lista, o `None` para «todos los
    # días», que es como lo entiende el resto del programa.
    persona['cobertura_dias'] = desde_texto(persona.pop('cobertura_dias_json', None))
    pareja = None
    if persona.get('pareja_id'):
        encontrada = conexion.execute(
            'SELECT nombre FROM empleados WHERE id=?', (persona['pareja_id'],)).fetchone()
        pareja = encontrada['nombre'] if encontrada else None
    persona['nombre_pareja'] = pareja
    # Nombres con los que el motor pregunta por la vigencia. Se traducen aquí,
    # en el único sitio que lee la tabla, para que el motor no tenga que saber
    # cómo se llaman las columnas.
    persona['vigente_desde'] = persona.get('alta_desde') or '2026-08-01'
    persona['desactivado_en'] = persona.get('retirado_desde') or None
    return persona


def listar(incluir_retirados: bool = False) -> list[dict]:
    with abierta() as conexion:
        donde = '' if incluir_retirados else 'WHERE activo=1'
        filas = conexion.execute(
            f'SELECT * FROM empleados {donde} ORDER BY activo DESC, {ORDEN}').fetchall()
        return [_como_dict(conexion, f) for f in filas]


def obtener(empleado_id: int) -> Optional[dict]:
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM empleados WHERE id=?', (int(empleado_id),)).fetchone()
        return _como_dict(conexion, fila) if fila else None


def por_nombre(nombre: str) -> Optional[dict]:
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM empleados WHERE nombre=?', (nombre,)).fetchone()
        return _como_dict(conexion, fila) if fila else None


# ------------------------------------------------------------------ escribir

def _valores(datos: dict) -> dict:
    salida = {c: datos.get(c) for c in CAMPOS}
    if 'cobertura_dias' in datos:
        salida['cobertura_dias_json'] = a_texto(datos.get('cobertura_dias'))
    salida['cobertura_dias_json'] = salida.get('cobertura_dias_json') or ''
    salida['cargo'] = salida.get('cargo') or 'GUÍA SOCIAL'
    salida['orden_rotacion'] = int(salida.get('orden_rotacion') or 0)
    for bandera in ('exento_especiales', 'es_nuevo'):
        salida[bandera] = 1 if salida.get(bandera) else 0
    salida['activo'] = 0 if salida.get('activo') is False else 1
    salida['alta_desde'] = salida.get('alta_desde') or '2026-08-01'
    return salida


def crear(datos: dict) -> int:
    valores = _valores(datos)
    columnas = ', '.join(valores)
    marcas = ', '.join('?' for _ in valores)
    with transaccion() as conexion:
        cursor = conexion.execute(
            f'INSERT INTO empleados({columnas}) VALUES({marcas})', tuple(valores.values()))
        return int(cursor.lastrowid)


def actualizar(empleado_id: int, datos: dict, vigente_desde: Optional[str] = None) -> None:
    """Cambia la ficha. Con `vigente_desde`, abre un tramo nuevo desde esa fecha.

    Guardar el estado anterior **antes** de pisarlo es lo que permite que un mes
    ya publicado se siga leyendo con la configuración que tenía. Es barato y es
    la única forma de que corregir algo hoy no reescriba el pasado.
    """
    with transaccion() as conexion:
        anterior = conexion.execute(
            'SELECT * FROM empleados WHERE id=?', (int(empleado_id),)).fetchone()
        if anterior is None:
            raise ValueError('Esa persona ya no está en la plantilla.')
        if vigente_desde:
            foto = {c: anterior[c] for c in CAMPOS if c in anterior.keys()}
            conexion.execute(
                'INSERT INTO empleados_historial(empleado_id, vigente_desde, datos_json) '
                'VALUES(?,?,?)',
                (int(empleado_id), str(vigente_desde),
                 json.dumps(foto, ensure_ascii=False, default=str)))
        campos = {c: v for c, v in _valores({**dict(anterior), **datos}).items()}
        asignaciones = ', '.join(f'{c}=?' for c in campos)
        conexion.execute(f'UPDATE empleados SET {asignaciones} WHERE id=?',
                         (*campos.values(), int(empleado_id)))


def retirar(empleado_id: int, desde: str) -> None:
    """Marca la salida sin borrar nada.

    Borrar a alguien se llevaría por delante su rastro en meses ya publicados.
    Lo que se hace es dejar escrito desde cuándo ya no está: el motor lo verá
    fuera de vigencia a partir de esa fecha y seguirá viéndolo dentro antes.
    """
    with transaccion() as conexion:
        conexion.execute(
            'UPDATE empleados SET activo=0, retirado_desde=? WHERE id=?',
            (str(desde), int(empleado_id)))


def reactivar(empleado_id: int) -> None:
    with transaccion() as conexion:
        conexion.execute(
            'UPDATE empleados SET activo=1, retirado_desde=NULL WHERE id=?',
            (int(empleado_id),))


def emparejar(uno: int, otro: Optional[int]) -> None:
    """Une o separa una pareja de punto de contacto, siempre por los dos lados.

    Una pareja escrita en un solo sentido es una pareja que el motor ve desde
    una punta y no desde la otra: a una persona le evita coincidir con la otra y
    a la otra no. Aquí no se puede: la reciprocidad la impone esta función.
    """
    with transaccion() as conexion:
        conexion.execute('UPDATE empleados SET pareja_id=NULL WHERE pareja_id=?', (int(uno),))
        if otro is None:
            conexion.execute('UPDATE empleados SET pareja_id=NULL WHERE id=?', (int(uno),))
            return
        conexion.execute('UPDATE empleados SET pareja_id=NULL WHERE pareja_id=?', (int(otro),))
        conexion.execute('UPDATE empleados SET pareja_id=? WHERE id=?', (int(otro), int(uno)))
        conexion.execute('UPDATE empleados SET pareja_id=? WHERE id=?', (int(uno), int(otro)))


# ------------------------------------------------------------- el historial

def configuracion_en(empleado_id: int, fecha: str) -> Optional[dict]:
    """Cómo estaba configurada esa persona en esa fecha."""
    with abierta() as conexion:
        tramo = conexion.execute(
            'SELECT datos_json FROM empleados_historial '
            'WHERE empleado_id=? AND vigente_desde > ? '
            'ORDER BY vigente_desde, id LIMIT 1',
            (int(empleado_id), str(fecha))).fetchone()
        if tramo:
            return json.loads(tramo['datos_json'])
        fila = conexion.execute(
            'SELECT * FROM empleados WHERE id=?', (int(empleado_id),)).fetchone()
        return _como_dict(conexion, fila) if fila else None


def cambios_programados() -> list[dict]:
    with abierta() as conexion:
        nombres = {int(r['id']): r['nombre']
                   for r in conexion.execute('SELECT id, nombre FROM empleados')}
        filas = conexion.execute(
            'SELECT empleado_id, vigente_desde, datos_json FROM empleados_historial '
            'ORDER BY empleado_id, vigente_desde').fetchall()
    return [{
        'empleado_id': int(f['empleado_id']),
        'nombre': nombres.get(int(f['empleado_id']), '—'),
        'vigente_desde': str(f['vigente_desde']),
        'antes': json.loads(f['datos_json']),
    } for f in filas]


def guardar_muchos(personas: Iterable[dict]) -> int:
    """Alta en bloque. Para la siembra inicial."""
    creadas = 0
    for persona in personas:
        crear(persona)
        creadas += 1
    return creadas
