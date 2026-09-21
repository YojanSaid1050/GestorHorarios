"""Libro: responsabilidad separada de gestor/servicios/excel.py."""
from pathlib import Path

from openpyxl import Workbook

from gestor import rutas
from gestor.servicios.apariencia import obtener_colores_excel
from gestor.servicios.exportacion_excel.consulta import (
    _hojas_de_apoyo,
)
from gestor.servicios.exportacion_excel.estilos import (
    HOJA_MES,
    HOJA_SEMANAS,
    LIBROS,
)
from gestor.servicios.exportacion_excel.horario import (
    _hoja_horario,
)


def _libro_pedido(resultado: dict, modo: str | None) -> str:
    """Qué libro se está pidiendo, admitiendo también los nombres antiguos."""
    pedido = str(resultado.get('_export_libro') or modo or resultado.get('_export_version') or '')
    if pedido in LIBROS:
        return pedido
    if resultado.get('_export_week_start'):
        return 'semana'
    if pedido == 'solo_horario':
        return 'trabajo'
    return 'completo'

def crear_excel(resultado: dict, modo: str | None = None) -> Path:
    """Arma el libro pedido.

    Son tres, no cinco. El de trabajo lleva dos hojas: el horario por semanas
    completas —donde se hacen los cambios— y su espejo del mes, que las recibe.
    Los otros dos se reparten: una semana suelta y el libro completo con los
    comentarios y las hojas de consulta. En esos dos, las horas siguen siendo
    fórmula; el resto de controles no, porque no son para quien los lee.
    """
    if not resultado.get('horario'):
        raise ValueError('El horario está vacío.')

    colores = obtener_colores_excel()
    rutas.EXPORTACIONES.mkdir(parents=True, exist_ok=True)
    libro = _libro_pedido(resultado, modo)

    wb = Workbook()
    wb.remove(wb.active)

    dias = resultado['horario'][0]['dias']
    dias_del_mes = [d for d in dias if d.get('mes_propio', True)]

    if libro == 'trabajo':
        ctx = _hoja_horario(wb, HOJA_SEMANAS, resultado, dias, colores, {
            'con_comentarios': False, 'controles': True,
        })
        if dias_del_mes and len(dias_del_mes) != len(dias):
            _hoja_horario(wb, HOJA_MES, resultado, dias_del_mes, colores, {
                'con_comentarios': False, 'controles': True,
                'recorte': 'los días del mes',
                'enlace': HOJA_SEMANAS, 'enlace_cols': ctx['col_por_fecha'],
                'enlace_horas_periodo': ctx['col_horas_periodo'],
            })
        sufijo = LIBROS['trabajo']
    elif libro == 'semana':
        inicio = resultado.get('_export_week_start')
        ctx = _hoja_horario(wb, 'Horario de la semana', resultado, dias, colores, {
            'con_comentarios': False, 'controles': False, 'recorte': 'una semana',
        })
        sufijo = f"{LIBROS['semana']}_{inicio}" if inicio else LIBROS['semana']
    else:
        ctx = _hoja_horario(wb, 'Horario con comentarios', resultado, dias, colores, {
            'con_comentarios': True, 'controles': False,
        })
        _hojas_de_apoyo(wb, resultado, colores, ctx)
        sufijo = LIBROS['completo']

    ruta = rutas.EXPORTACIONES / f"Programacion_{resultado['anio']}_{resultado['mes']:02d}{sufijo}.xlsx"
    wb.save(ruta)
    return ruta
