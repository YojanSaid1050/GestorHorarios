# -*- coding: utf-8 -*-
"""Lo que está cerrado, y lo mismo para todo el que pregunte.

Cerrar una semana significa una cosa: esos siete días son los que la oficina
tiene en la mano, y ningún camino del programa los cambia. Estaba escrito tres
veces —en la edición, en la publicación y en la pantalla de operación— y una de
las tres se había quedado atrás: la generación completa del mes no preguntaba
siquiera, así que volver a generar reescribía tranquilamente una semana cerrada.

Dos decisiones que conviene ver escritas:

* **Una semana se identifica por su lunes, no por el mes desde el que se mira.**
  Los periodos se solapan: la primera semana de octubre es también la última de
  septiembre. Cerrarla desde septiembre y preguntar desde octubre daba «no está
  cerrada», que es justo lo contrario de lo que había dicho quien la cerró.
* **Congelar es casilla a casilla, no día a día.** Al motor no se le dice «no
  toques estas fechas»; se le entrega cada celda con lo que ya tenía, marcada
  para preservar. Es la única forma de que la semana salga idéntica y no
  parecida.
"""
from __future__ import annotations

from datetime import date, timedelta

from gestor.datos.base import abierta
from gestor.dominio import calendario


def lunes_cerrados() -> set[str]:
    """Todos los lunes cerrados, vengan del mes que vengan."""
    with abierta() as conexion:
        return {str(fila['lunes'])[:10] for fila in conexion.execute(
            'SELECT DISTINCT lunes FROM semanas WHERE cerrada=1')}


def semanas_cerradas(anio: int, mes: int) -> set[str]:
    """Los lunes cerrados que caen dentro de este periodo.

    Se cruza con las semanas del periodo en lugar de filtrar por `mes` en la
    consulta: una semana compartida está cerrada para los dos meses que la
    comparten, porque es la misma semana.
    """
    del_periodo = {inicio.isoformat()
                   for inicio, _ in calendario.semanas(int(mes), int(anio))}
    return del_periodo & lunes_cerrados()


def fechas_de(lunes: str) -> set[str]:
    inicio = date.fromisoformat(str(lunes)[:10])
    return {(inicio + timedelta(days=i)).isoformat() for i in range(7)}


def fechas_cerradas(anio: int, mes: int) -> set[str]:
    """Los días concretos que no se pueden tocar en este periodo."""
    cerradas: set[str] = set()
    for lunes in semanas_cerradas(anio, mes):
        cerradas.update(fechas_de(lunes))
    return cerradas


def celda_congelada(empleado_id: int, dia: dict) -> dict:
    """Una casilla tal y como está, en el formato que entiende el motor."""
    return {
        'empleado_id': int(empleado_id),
        'fecha': str(dia.get('fecha')),
        'turno': dia.get('turno'),
        'preservar': True,
        'origen': dia.get('origen'),
        'observacion': dia.get('observacion', ''),
        'solicitud_id': dia.get('solicitud_id'),
        'requerimiento_id': dia.get('requerimiento_id'),
        'festivo_origen': dia.get('festivo_origen'),
        'capacitacion_horas': dia.get('capacitacion_horas') or 0.0,
        'cobertura_operativa': dia.get('cobertura_operativa'),
        'turno_operativo_origen': dia.get('turno_operativo_origen'),
    }


def congelar_lo_cerrado(mes: int, anio: int, base: dict | None = None) -> list[dict]:
    """Las celdas de las semanas cerradas, para que el motor las respete.

    Se leen del horario oficial, que es el que la oficina tiene: cerrar una
    semana sin horario oficial no congela nada, y no hay nada que congelar.
    """
    fechas = fechas_cerradas(anio, mes)
    if not fechas:
        return []
    if base is None:
        from gestor.datos import horarios
        base = horarios.oficial(int(anio), int(mes))
    if not base:
        return []
    return [celda_congelada(int(fila.get('empleado_id') or 0), dia)
            for fila in base.get('horario') or []
            for dia in fila.get('dias') or []
            if str(dia.get('fecha')) in fechas]
