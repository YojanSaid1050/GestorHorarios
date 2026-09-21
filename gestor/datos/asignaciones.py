"""Asignaciones: responsabilidad separada de gestor/datos/novedades.py."""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from gestor.datos.base import abierta, transaccion
from gestor.datos.novedades_comun import (
    CAMPOS_ASIGNACION,
    _estado_efectivo_asignacion,
    _rango,
)
from gestor.dominio import calendario


def _valores_de_asignacion(datos: dict) -> dict:
    valores = {c: datos.get(c) for c in CAMPOS_ASIGNACION}
    valores['fechas_json'] = json.dumps(
        [str(f) for f in (datos.get('fechas') or [])], ensure_ascii=False)
    valores['dias_semana_json'] = json.dumps(
        [int(d) for d in (datos.get('dias_semana') or [])], ensure_ascii=False)
    valores['recurrente_indefinido'] = 1 if datos.get('recurrente_indefinido') else 0
    valores['libera_cobertura'] = 1 if (
        datos.get('libera_cobertura') or datos.get('cubrir_pm')) else 0
    valores['descripcion'] = valores.get('descripcion') or ''
    valores['estado'] = valores.get('estado') or 'activo'
    fechas = [str(f) for f in (datos.get('fechas') or [])]
    valores['vigente_desde'] = (
        valores.get('vigente_desde') or (sorted(fechas)[0] if fechas else None))
    return valores

def crear_asignacion(datos: dict) -> int:
    return crear_asignaciones([datos])[0]

def crear_asignaciones(muchas: list[dict]) -> list[int]:
    """Varias asignaciones, o ninguna.

    La versión masiva guardaba persona a persona, cada una con su transacción.
    Si la cuarta fallaba —bastaba con que alguien hubiera dejado la plantilla—
    las tres primeras ya estaban confirmadas y el mensaje era un error: quien lo
    leía no tenía forma de saber que tres personas sí tenían la asignación
    puesta, ni cuáles.

    Aquí van todas dentro de la misma transacción: o están todas o no está
    ninguna, que es lo que significa «asignar a este grupo».
    """
    filas = [_valores_de_asignacion(d) for d in muchas]
    if not filas:
        return []
    creados = []
    with transaccion() as conexion:
        for valores in filas:
            columnas = ', '.join(valores)
            marcas = ', '.join('?' for _ in valores)
            cursor = conexion.execute(
                f'INSERT INTO asignaciones({columnas}) VALUES({marcas})',
                tuple(valores.values()))
            creados.append(int(cursor.lastrowid))
    return creados

def borrar_asignacion(asignacion_id: int) -> None:
    with transaccion() as conexion:
        conexion.execute('DELETE FROM asignaciones WHERE id=?', (int(asignacion_id),))

def actualizar_asignacion(asignacion_id: int, datos: dict) -> None:
    valores = {c: datos.get(c) for c in CAMPOS_ASIGNACION
               if c in datos and c not in ('grupo_id', 'grupo_alcance',
                                           'grupo_area', 'grupo_etiqueta')}
    if 'fechas' in datos:
        valores['fechas_json'] = json.dumps(
            [str(f) for f in (datos.get('fechas') or [])], ensure_ascii=False)
    if 'dias_semana' in datos:
        valores['dias_semana_json'] = json.dumps(
            [int(d) for d in (datos.get('dias_semana') or [])], ensure_ascii=False)
    if 'recurrente_indefinido' in datos:
        valores['recurrente_indefinido'] = 1 if datos['recurrente_indefinido'] else 0
    if 'libera_cobertura' in datos or 'cubrir_pm' in datos:
        valores['libera_cobertura'] = 1 if (
            datos.get('libera_cobertura') or datos.get('cubrir_pm')) else 0
    if not valores:
        return
    asignaciones = ', '.join(f'{c}=?' for c in valores)
    with transaccion() as conexion:
        cursor = conexion.execute(
            f'UPDATE asignaciones SET {asignaciones} WHERE id=?',
            (*valores.values(), int(asignacion_id)))
        if not cursor.rowcount:
            raise ValueError('Esa asignación ya no existe.')

def cancelar_asignacion(asignacion_id: int) -> None:
    with transaccion() as conexion:
        cursor = conexion.execute(
            "UPDATE asignaciones SET estado='cancelado' WHERE id=?",
            (int(asignacion_id),))
        if not cursor.rowcount:
            raise ValueError('Esa asignación ya no existe.')

def cancelar_grupo(grupo_id: str) -> int:
    with transaccion() as conexion:
        cursor = conexion.execute(
            "UPDATE asignaciones SET estado='cancelado' WHERE grupo_id=?", (str(grupo_id),))
        return int(cursor.rowcount or 0)

def borrar_grupo(grupo_id: str) -> int:
    with transaccion() as conexion:
        cursor = conexion.execute('DELETE FROM asignaciones WHERE grupo_id=?',
                                  (str(grupo_id),))
        return int(cursor.rowcount or 0)

def asignaciones_cumplidas() -> list[int]:
    """Las que ya se hicieron: activas, con fechas, y todas ellas pasadas."""
    cumplidas = []
    for asignacion in listar_asignaciones():
        if asignacion.get('estado_efectivo') == 'finalizado':
            cumplidas.append(int(asignacion['id']))
    return cumplidas

def listar_asignaciones(mes: Optional[int] = None, anio: Optional[int] = None) -> list[dict]:
    with abierta() as conexion:
        filas = conexion.execute(
            'SELECT a.*, e.nombre AS nombre, e.nombre AS empleado_nombre, '
            'e.area AS area, r.nombre AS reemplazo_nombre FROM asignaciones a '
            'JOIN empleados e ON e.id = a.empleado_id '
            'LEFT JOIN empleados r ON r.id = a.reemplazo_empleado_id '
            'ORDER BY a.id').fetchall()

    salida = []
    for fila in filas:
        item = dict(fila)
        item['fechas'] = json.loads(item.pop('fechas_json') or '[]')
        item['dias_semana'] = json.loads(item.pop('dias_semana_json') or '[]')
        item['recurrente_indefinido'] = bool(item.get('recurrente_indefinido'))
        item['libera_cobertura'] = bool(item.get('libera_cobertura'))
        # La pantalla lo llama `cubrir_pm` desde siempre, y el motor también.
        # Se traduce aquí, en el único sitio que lee la tabla.
        item['cubrir_pm'] = item['libera_cobertura']
        item['estado_efectivo'] = _estado_efectivo_asignacion(item)
        if mes and anio and not _toca_el_periodo(item, mes, anio):
            continue
        salida.append(item)
    return salida

def _toca_el_periodo(asignacion: dict, mes: int, anio: int) -> bool:
    inicio, fin = _rango(mes, anio)
    if asignacion['recurrente_indefinido']:
        # Una asignación recurrente sin final toca todos los períodos **desde
        # que empieza**: «los miércoles hace jornada administrativa, a partir de
        # diciembre», hasta que se quite. Devolver siempre `True` la metía
        # también en octubre, que es meses antes de que nadie la hubiera
        # decidido.
        return fin >= str(asignacion.get('vigente_desde') or inicio)[:10]
    return any(inicio <= str(f) <= fin for f in asignacion['fechas'])

def asignaciones_para_el_motor(mes: int, anio: int) -> list[dict]:
    """Las asignaciones del período, en la forma que el motor entiende.

    Una asignación recurrente se despliega aquí en los días concretos del
    período: el motor trabaja con fechas, no con «todos los miércoles». Pero se
    le dice **además** que era recurrente, porque de eso dependen el orden en
    que se aplican y si un choque es un error o un aviso.
    """
    from datetime import timedelta

    inicio, fin = calendario.rango(int(mes), int(anio))
    salida = []
    for asignacion in listar_asignaciones(mes, anio):
        if str(asignacion.get('estado') or 'activo') != 'activo':
            # Una asignación cancelada sigue guardada para poder leerla en el
            # historial, pero no vuelve a aplicarse.
            continue
        fechas = [str(f) for f in asignacion['fechas']
                  if inicio.isoformat() <= str(f) <= fin.isoformat()]
        if asignacion['recurrente_indefinido'] and asignacion['dias_semana']:
            dias = {int(d) for d in asignacion['dias_semana']}
            # Desde cuándo se repite. Sin esto, una recurrente creada para
            # diciembre generaba ocurrencias en octubre: la repetición empezaba
            # el primer día del período que se estuviera armando, fuera cual
            # fuera, y el horario se movía meses antes de que nadie lo hubiera
            # decidido.
            desde = asignacion.get('vigente_desde')
            arranque = max(inicio, date.fromisoformat(str(desde)[:10])) if desde else inicio
            fecha = arranque
            while fecha <= fin:
                if fecha.weekday() in dias:
                    fechas.append(fecha.isoformat())
                fecha += timedelta(days=1)
        if not fechas:
            continue
        salida.append({
            'id': asignacion['id'],
            'empleado_id': asignacion['empleado_id'],
            'tipo': asignacion['tipo'],
            'fechas': sorted(set(fechas)),
            'horario_administrativo': asignacion.get('horario_administrativo'),
            'turno_excepcion': asignacion.get('turno_excepcion'),
            'cubrir_pm': asignacion.get('cubrir_pm'),
            'reemplazo_empleado_id': asignacion.get('reemplazo_empleado_id'),
            'descripcion': asignacion.get('descripcion') or '',
            # Que se repite sola, y qué días. El motor lo necesita y no se lo
            # daba nadie.
            #
            # `_es_habitual` decide tres cosas: en qué orden se aplican las
            # asignaciones —la habitualidad primero, la fecha concreta después,
            # porque una fecha es una instrucción para ese día y la habitualidad
            # es lo que se hace mientras nadie diga otra cosa—, si un choque es
            # un error o un aviso, y si el día queda marcado como
            # `origen_habitual` para que una novedad aprobada pueda reescribirlo.
            # Sin estos dos campos siempre era `False`: el orden dependía otra
            # vez de cuál se hubiera creado primero, y un choque contra un
            # «todos los lunes en PM» dejaba el mes entero sin poder generarse
            # en vez de resolverse con un aviso.
            'recurrente_indefinido': bool(asignacion.get('recurrente_indefinido')),
            'dias_semana': list(asignacion.get('dias_semana') or []),
            'vigente_desde': asignacion.get('vigente_desde'),
        })
    return salida
