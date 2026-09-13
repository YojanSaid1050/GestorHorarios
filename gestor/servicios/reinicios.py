# -*- coding: utf-8 -*-
"""Volver atrás: reiniciar un mes en adelante, o toda la aplicación.

El fallo que este archivo existe para no repetir: **reiniciar borraba los
horarios y nada más**. Sobrevivían los cambios manuales guardados —que se
vuelven a aplicar en cada generación—, las semanas cerradas y el estado del
período, así que al volver a generar salía el mismo mes. Desde fuera eso se lee
como que el botón no hace nada, y con razón.

Reiniciar de verdad significa borrar las cuatro cosas.
"""
from __future__ import annotations

from gestor.datos.base import transaccion
from gestor.dominio import calendario
from gestor.servicios.continuidad import periodo_anterior

#: Agosto y septiembre de 2026 son las programaciones base y no se reinician:
#: llegan transcritas del Excel real de la oficina. El primer mes que sí se
#: puede reiniciar es el siguiente al último de ellas.
PRIMER_MES_REINICIABLE = (calendario.MESES_BASE[-1][0],
                          calendario.MESES_BASE[-1][1] + 1)


def reiniciar_programacion(mes: int, anio: int) -> dict:
    """Borra los horarios de ese mes en adelante, y todo lo que los reconstruye."""
    if not 1 <= int(mes) <= 12:
        raise ValueError('El mes tiene que estar entre 1 y 12.')
    if (int(anio), int(mes)) < PRIMER_MES_REINICIABLE:
        raise ValueError(
            'Agosto y septiembre de 2026 son las programaciones base y no se reinician: '
            'llegan transcritas del horario real de la oficina. El reinicio tiene que '
            'empezar en octubre de 2026 o en un mes posterior.')

    # Los cambios manuales se guardan por fecha, y los períodos se solapan: el de
    # septiembre llega hasta el 4 de octubre. Cortar por el primer día del
    # período de octubre —el 28 de septiembre— se llevaría por delante ajustes
    # que pertenecen a septiembre, que aquí se conserva. El corte va justo
    # después de que termine el período anterior.
    mes_anterior, anio_anterior = periodo_anterior(mes, anio)
    corte = calendario.rango(mes_anterior, anio_anterior)[1].isoformat()

    with transaccion() as conexion:
        resumen = conexion.execute(
            'SELECT COUNT(*) AS total, '
            'COALESCE(SUM(CASE WHEN oficial=1 THEN 1 ELSE 0 END),0) AS oficiales, '
            "COUNT(DISTINCT printf('%04d-%02d',anio,mes)) AS periodos "
            'FROM horarios WHERE anio>? OR (anio=? AND mes>=?)',
            (int(anio), int(anio), int(mes))).fetchone()
        borrados = dict(resumen)

        conexion.execute('DELETE FROM horarios WHERE anio>? OR (anio=? AND mes>=?)',
                         (int(anio), int(anio), int(mes)))
        for tabla in ('semanas', 'periodos', 'periodos_area'):
            conexion.execute(f'DELETE FROM {tabla} WHERE anio>? OR (anio=? AND mes>=?)',
                             (int(anio), int(anio), int(mes)))
        ajustes = conexion.execute(
            'SELECT COUNT(*) AS n FROM ajustes_manuales WHERE fecha>?', (corte,)).fetchone()['n']
        conexion.execute('DELETE FROM ajustes_manuales WHERE fecha>?', (corte,))

    return {
        'ok': True,
        'desde': f'{int(anio):04d}-{int(mes):02d}',
        'registros_eliminados': int(borrados['total'] or 0),
        'oficiales_eliminados': int(borrados['oficiales'] or 0),
        'periodos_afectados': int(borrados['periodos'] or 0),
        'ajustes_manuales_eliminados': int(ajustes or 0),
        'mensaje': (
            f'Se reinició la programación desde {calendario.nombre_del_periodo(mes, anio)}. '
            'Se borraron también los cambios manuales guardados, las semanas cerradas y el '
            'estado de esos períodos, para que al generarlos otra vez salgan de cero. '
            'Se conservan agosto y septiembre de 2026, el personal, las novedades y la '
            'configuración.'),
    }
