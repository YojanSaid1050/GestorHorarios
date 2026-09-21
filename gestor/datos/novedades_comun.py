"""Novedades comun: responsabilidad separada de gestor/datos/novedades.py."""
from __future__ import annotations

from datetime import date

from gestor.dominio import calendario

CAMPOS_SOLICITUD = (
    'empleado_id', 'tipo', 'fecha_inicio', 'fecha_fin', 'sin_fecha_fin',
    'modo_periodo', 'dia_semana_recurrente', 'modo_cobertura',
    'reemplazo_empleado_id', 'intercambio_empleado_id', 'turno_solicitado',
    'dia_descanso_solicitado', 'estado', 'observacion',
    'hora_inicio', 'hora_fin',
)

CAMPOS_ASIGNACION = (
    'empleado_id', 'tipo', 'fechas_json', 'recurrente_indefinido',
    'dias_semana_json', 'horario_administrativo', 'turno_excepcion',
    'libera_cobertura', 'reemplazo_empleado_id', 'descripcion',
    'vigente_desde', 'estado', 'grupo_id', 'grupo_alcance', 'grupo_area',
    'grupo_etiqueta',
)


def _hoy() -> str:
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
