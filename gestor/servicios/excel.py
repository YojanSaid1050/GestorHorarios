"""Interfaz compatible; la implementación se organiza por responsabilidades.

Ver docs/ARQUITECTURA.md.
"""
from gestor.servicios import reglas_operacion as _reglas_operacion
from gestor.servicios.exportacion_excel.consulta import (
    _hojas_de_apoyo as _hojas_de_apoyo,
)
from gestor.servicios.exportacion_excel.estilos import AREA as AREA
from gestor.servicios.exportacion_excel.estilos import CODIGOS_NO_LABORADOS as CODIGOS_NO_LABORADOS
from gestor.servicios.exportacion_excel.estilos import CODIGOS_TRABAJO as CODIGOS_TRABAJO
from gestor.servicios.exportacion_excel.estilos import DIAS as DIAS
from gestor.servicios.exportacion_excel.estilos import EMPIEZA_UNA_FORMULA as EMPIEZA_UNA_FORMULA
from gestor.servicios.exportacion_excel.estilos import FRANJAS as FRANJAS
from gestor.servicios.exportacion_excel.estilos import HOJA_MES as HOJA_MES
from gestor.servicios.exportacion_excel.estilos import HOJA_SEMANAS as HOJA_SEMANAS
from gestor.servicios.exportacion_excel.estilos import LIBROS as LIBROS
from gestor.servicios.exportacion_excel.estilos import MARCA_AGUA as MARCA_AGUA
from gestor.servicios.exportacion_excel.estilos import MESES as MESES
from gestor.servicios.exportacion_excel.estilos import MESES_CORTOS as MESES_CORTOS
from gestor.servicios.exportacion_excel.estilos import (
    _agrupar_semanas as _agrupar_semanas,
)
from gestor.servicios.exportacion_excel.estilos import (
    _borde as _borde,
)
from gestor.servicios.exportacion_excel.estilos import (
    _cell as _cell,
)
from gestor.servicios.exportacion_excel.estilos import (
    _contar as _contar,
)
from gestor.servicios.exportacion_excel.estilos import (
    _dow as _dow,
)
from gestor.servicios.exportacion_excel.estilos import (
    _fecha_corta as _fecha_corta,
)
from gestor.servicios.exportacion_excel.estilos import (
    _formula_horas as _formula_horas,
)
from gestor.servicios.exportacion_excel.estilos import (
    _header as _header,
)
from gestor.servicios.exportacion_excel.estilos import (
    _rangos as _rangos,
)
from gestor.servicios.exportacion_excel.estilos import (
    _solo_texto as _solo_texto,
)
from gestor.servicios.exportacion_excel.horario import (
    _colorear_por_valor as _colorear_por_valor,
)
from gestor.servicios.exportacion_excel.horario import (
    _hoja_horario as _hoja_horario,
)
from gestor.servicios.exportacion_excel.libro import (
    _libro_pedido as _libro_pedido,
)
from gestor.servicios.exportacion_excel.libro import (
    crear_excel as crear_excel,
)

MAX_DIAS_POR_DEFECTO = _reglas_operacion.POR_DEFECTO
