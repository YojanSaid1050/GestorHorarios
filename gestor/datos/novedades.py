# -*- coding: utf-8 -*-
"""Las dos formas que tiene la operación de apartarse del horario normal.

Se guardan aparte porque son cosas distintas, aunque en pantalla se parezcan:

* una **solicitud** la pide una persona y alguien la aprueba o la rechaza —unas
  vacaciones, una incapacidad, un cambio de turno un día concreto—;
* una **asignación** la decide la coordinación y no se aprueba: se pone —un
  descanso extra, una jornada administrativa, una actividad—.

Las dos se buscan **por período completo** y no por mes natural. Es el mismo
detalle de siempre y ya costó caro: al aprobar unas vacaciones del 1 de octubre
solo se avisaba a octubre, y septiembre —cuyo período llega hasta el domingo 4—
se quedaba dando por bueno un horario que ya no coincidía con lo aprobado.
"""
from __future__ import annotations

import json
from typing import Optional

from gestor.datos.base import abierta, transaccion
from gestor.dominio import calendario

CAMPOS_SOLICITUD = (
    'empleado_id', 'tipo', 'fecha_inicio', 'fecha_fin', 'sin_fecha_fin',
    'modo_periodo', 'dia_semana_recurrente', 'modo_cobertura',
    'reemplazo_empleado_id', 'intercambio_empleado_id', 'turno_solicitado',
    'dia_descanso_solicitado', 'estado', 'observacion',
)

CAMPOS_ASIGNACION = (
    'empleado_id', 'tipo', 'fechas_json', 'recurrente_indefinido',
    'dias_semana_json', 'horario_administrativo', 'turno_excepcion',
    'libera_cobertura', 'reemplazo_empleado_id', 'descripcion',
    'vigente_desde', 'estado', 'grupo_id', 'grupo_alcance', 'grupo_area',
    'grupo_etiqueta',
)


def _hoy() -> str:
    from datetime import date
    return date.today().isoformat()


def _estado_efectivo_solicitud(item: dict) -> str:
    """Lo que hay que enseñar, que no siempre es lo que dice la columna.

    Una solicitud aprobada cuyas fechas ya pasaron no está «aprobada»: está
    cumplida. Y una pendiente cuyo plazo pasó no se puede aprobar ya. Sin esta
    distinción la lista se llenaba de vacaciones de agosto pidiendo aprobación.
    """
    estado = str(item.get('estado') or 'pendiente')
    if item.get('sin_fecha_fin') or str(item.get('fecha_fin') or '') >= _hoy():
        return estado
    if estado == 'aprobada':
        return 'finalizada'
    if estado == 'pendiente':
        return 'vencida'
    return estado


def _estado_efectivo_asignacion(item: dict) -> str:
    estado = str(item.get('estado') or 'activo')
    if estado != 'activo' or item.get('recurrente_indefinido'):
        return estado
    fechas = [str(f) for f in (item.get('fechas') or [])]
    if fechas and max(fechas) < _hoy():
        return 'finalizado'
    return estado


def _rango(mes: int, anio: int) -> tuple[str, str]:
    inicio, fin = calendario.rango(int(mes), int(anio))
    return inicio.isoformat(), fin.isoformat()


# ------------------------------------------------------------- solicitudes

def _comprobar_el_orden_de_las_fechas(inicio, fin) -> None:
    """Una novedad no puede terminar antes de empezar.

    No se comprobaba en ninguna parte, y el resultado era **silencio**: la
    solicitud se guardaba, se dejaba aprobar y al generar el mes no producía ni
    un solo día, porque el rango estaba vacío. Nadie veía un error; se veían
    unas vacaciones aprobadas que no salían en el horario, que es peor que un
    fallo, porque parece un fallo del reparto.

    Invertir las dos fechas es además el error más fácil de cometer: se elige
    primero el final por costumbre, y el calendario acepta las dos sin quejarse.
    """
    if not inicio or not fin or str(fin) >= str(inicio):
        return
    raise ValueError(
        f'La novedad terminaría el {fin}, antes de empezar el {inicio}. '
        'Revisa las dos fechas: la de fin no puede ser anterior a la de inicio.')


def crear_solicitud(datos: dict) -> int:
    valores = {c: datos.get(c) for c in CAMPOS_SOLICITUD}
    valores['estado'] = valores.get('estado') or 'pendiente'
    valores['observacion'] = valores.get('observacion') or ''
    valores['modo_periodo'] = valores.get('modo_periodo') or 'rango'
    valores['modo_cobertura'] = valores.get('modo_cobertura') or 'sin_cubrir'
    valores['sin_fecha_fin'] = 1 if valores.get('sin_fecha_fin') else 0
    valores['fecha_fin'] = valores.get('fecha_fin') or valores.get('fecha_inicio')
    _comprobar_el_orden_de_las_fechas(valores.get('fecha_inicio'), valores['fecha_fin'])
    columnas = ', '.join(valores)
    marcas = ', '.join('?' for _ in valores)
    with transaccion() as conexion:
        cursor = conexion.execute(
            f'INSERT INTO solicitudes({columnas}) VALUES({marcas})',
            tuple(valores.values()))
        return int(cursor.lastrowid)


def resolver_solicitud(solicitud_id: int, estado: str) -> None:
    if estado not in ('aprobada', 'rechazada', 'pendiente'):
        raise ValueError('Una solicitud solo puede quedar aprobada, rechazada o pendiente.')
    with transaccion() as conexion:
        conexion.execute(
            "UPDATE solicitudes SET estado=?, resuelto_en=datetime('now') WHERE id=?",
            (estado, int(solicitud_id)))


def borrar_solicitud(solicitud_id: int) -> None:
    with transaccion() as conexion:
        conexion.execute('DELETE FROM solicitudes WHERE id=?', (int(solicitud_id),))


def actualizar_solicitud(solicitud_id: int, datos: dict) -> None:
    """Corrige una solicitud ya escrita, sin cambiar su estado.

    Editar no reabre la decisión: si estaba aprobada, sigue aprobada con las
    fechas corregidas. Ponerla en pendiente al editar obligaría a aprobarla otra
    vez por cambiar una letra de la observación.
    """
    valores = {c: datos.get(c) for c in CAMPOS_SOLICITUD if c in datos and c != 'estado'}
    if not valores:
        return
    if 'sin_fecha_fin' in valores:
        valores['sin_fecha_fin'] = 1 if valores['sin_fecha_fin'] else 0
    if 'fecha_fin' in valores:
        valores['fecha_fin'] = valores['fecha_fin'] or valores.get(
            'fecha_inicio') or datos.get('fecha_inicio')
    _comprobar_el_orden_de_las_fechas(
        valores.get('fecha_inicio') or datos.get('fecha_inicio'),
        valores.get('fecha_fin'))
    asignaciones = ', '.join(f'{c}=?' for c in valores)
    with transaccion() as conexion:
        cursor = conexion.execute(
            f'UPDATE solicitudes SET {asignaciones} WHERE id=?',
            (*valores.values(), int(solicitud_id)))
        if not cursor.rowcount:
            raise ValueError('Esa solicitud ya no existe.')


def solicitudes_cumplidas() -> list[int]:
    """Las aprobadas cuyas fechas ya pasaron. Ni canceladas ni vencidas.

    El botón que las borra es una limpieza voluntaria del histórico cumplido.
    Llevarse también las rechazadas o las canceladas borraría justo lo que
    alguien puede querer consultar: por qué aquello no se hizo.
    """
    with abierta() as conexion:
        filas = conexion.execute(
            "SELECT id FROM solicitudes WHERE estado='aprobada' AND sin_fecha_fin=0 "
            'AND fecha_fin<?', (_hoy(),)).fetchall()
    return [int(f['id']) for f in filas]


def listar_solicitudes(mes: Optional[int] = None, anio: Optional[int] = None,
                       solo_aprobadas: bool = False) -> list[dict]:
    condiciones, argumentos = [], []
    if mes and anio:
        inicio, fin = _rango(mes, anio)
        condiciones.append(
            '((fecha_inicio<=? AND fecha_fin>=?) OR (sin_fecha_fin=1 AND fecha_inicio<=?))')
        argumentos += [fin, inicio, fin]
    if solo_aprobadas:
        condiciones.append("estado='aprobada'")
    donde = ('WHERE ' + ' AND '.join(condiciones)) if condiciones else ''
    with abierta() as conexion:
        filas = conexion.execute(
            'SELECT s.*, e.nombre AS nombre, e.nombre AS empleado_nombre, '
            'e.area AS area, r.nombre AS reemplazo_nombre, '
            'i.nombre AS intercambio_nombre '
            'FROM solicitudes s '
            'JOIN empleados e ON e.id = s.empleado_id '
            'LEFT JOIN empleados r ON r.id = s.reemplazo_empleado_id '
            f'LEFT JOIN empleados i ON i.id = s.intercambio_empleado_id {donde} '
            'ORDER BY s.fecha_inicio, s.id', argumentos).fetchall()
    salida = []
    for fila in filas:
        item = dict(fila)
        item['sin_fecha_fin'] = bool(item.get('sin_fecha_fin'))
        # El motor pregunta por `aprobada`, que es como se llamaba la columna
        # antes de que el estado tuviera tres valores. Se traduce aquí, en el
        # único sitio que lee la tabla, y no en el motor: así el día que el
        # estado gane un valor más, solo hay que tocar esta línea.
        item['aprobada'] = item.get('estado') == 'aprobada'
        item['estado_efectivo'] = _estado_efectivo_solicitud(item)
        # Una novedad semanal sin final llega hasta donde llegue el período que
        # se está mirando: sin esto, «los martes libra» solo valía la semana en
        # que se pidió.
        if mes and anio and item['sin_fecha_fin'] and item['modo_periodo'] == 'semanal':
            inicio, fin = _rango(mes, anio)
            item['fecha_inicio'] = max(inicio, str(item.get('fecha_inicio') or inicio))
            item['fecha_fin'] = fin
        salida.append(item)
    return salida


def solicitudes_para_el_motor(mes: int, anio: int) -> list[dict]:
    """Solo las aprobadas: lo pendiente todavía no es una decisión."""
    return listar_solicitudes(mes, anio, solo_aprobadas=True)


def solapadas(empleado_id: int, desde: str, hasta: str,
              excluir: Optional[int] = None) -> list[dict]:
    """Novedades ya aprobadas de esa persona que pisan esas fechas.

    Aprobar dos cosas distintas para el mismo día es una contradicción que la
    aplicación no puede resolver sola: se detecta antes de aprobar y se explica.
    """
    argumentos = [int(empleado_id), hasta, desde]
    extra = ''
    if excluir is not None:
        extra = ' AND id<>?'
        argumentos.append(int(excluir))
    with abierta() as conexion:
        filas = conexion.execute(
            "SELECT * FROM solicitudes WHERE empleado_id=? AND estado='aprobada' "
            f'AND fecha_inicio<=? AND fecha_fin>=?{extra}', argumentos).fetchall()
    return [dict(f) for f in filas]


# ------------------------------------------------------------ asignaciones

def crear_asignacion(datos: dict) -> int:
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
    columnas = ', '.join(valores)
    marcas = ', '.join('?' for _ in valores)
    with transaccion() as conexion:
        cursor = conexion.execute(
            f'INSERT INTO asignaciones({columnas}) VALUES({marcas})',
            tuple(valores.values()))
        return int(cursor.lastrowid)


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
        # Una asignación recurrente sin final toca todos los períodos: «los
        # miércoles hace jornada administrativa», hasta que se quite.
        return True
    return any(inicio <= str(f) <= fin for f in asignacion['fechas'])


def asignaciones_para_el_motor(mes: int, anio: int) -> list[dict]:
    """Las asignaciones del período, en la forma que el motor entiende.

    Una asignación recurrente se despliega aquí en los días concretos del
    período: el motor trabaja con fechas, no con «todos los miércoles».
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
            fecha = inicio
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
        })
    return salida
