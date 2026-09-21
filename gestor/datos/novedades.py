"""Interfaz compatible; la implementación se organiza por responsabilidades.

Ver docs/ARQUITECTURA.md.
"""
from gestor.datos.asignaciones import (
    _toca_el_periodo as _toca_el_periodo,
)
from gestor.datos.asignaciones import (
    _valores_de_asignacion as _valores_de_asignacion,
)
from gestor.datos.asignaciones import (
    actualizar_asignacion as actualizar_asignacion,
)
from gestor.datos.asignaciones import (
    asignaciones_cumplidas as asignaciones_cumplidas,
)
from gestor.datos.asignaciones import (
    asignaciones_para_el_motor as asignaciones_para_el_motor,
)
from gestor.datos.asignaciones import (
    borrar_asignacion as borrar_asignacion,
)
from gestor.datos.asignaciones import (
    borrar_grupo as borrar_grupo,
)
from gestor.datos.asignaciones import (
    cancelar_asignacion as cancelar_asignacion,
)
from gestor.datos.asignaciones import (
    cancelar_grupo as cancelar_grupo,
)
from gestor.datos.asignaciones import (
    crear_asignacion as crear_asignacion,
)
from gestor.datos.asignaciones import (
    crear_asignaciones as crear_asignaciones,
)
from gestor.datos.asignaciones import (
    listar_asignaciones as listar_asignaciones,
)
from gestor.datos.novedades_comun import CAMPOS_ASIGNACION as CAMPOS_ASIGNACION
from gestor.datos.novedades_comun import CAMPOS_SOLICITUD as CAMPOS_SOLICITUD
from gestor.datos.novedades_comun import (
    _estado_efectivo_asignacion as _estado_efectivo_asignacion,
)
from gestor.datos.novedades_comun import (
    _estado_efectivo_solicitud as _estado_efectivo_solicitud,
)
from gestor.datos.novedades_comun import (
    _hoy as _hoy,
)
from gestor.datos.novedades_comun import (
    _rango as _rango,
)
from gestor.datos.solicitudes import (
    _comprobar_el_orden_de_las_fechas as _comprobar_el_orden_de_las_fechas,
)
from gestor.datos.solicitudes import (
    actualizar_solicitud as actualizar_solicitud,
)
from gestor.datos.solicitudes import (
    borrar_solicitud as borrar_solicitud,
)
from gestor.datos.solicitudes import (
    crear_solicitud as crear_solicitud,
)
from gestor.datos.solicitudes import (
    descansos_movidos_de_la_semana as descansos_movidos_de_la_semana,
)
from gestor.datos.solicitudes import (
    listar_solicitudes as listar_solicitudes,
)
from gestor.datos.solicitudes import (
    ocurrencias as ocurrencias,
)
from gestor.datos.solicitudes import (
    resolver_solicitud as resolver_solicitud,
)
from gestor.datos.solicitudes import (
    solapadas as solapadas,
)
from gestor.datos.solicitudes import (
    solicitudes_cumplidas as solicitudes_cumplidas,
)
from gestor.datos.solicitudes import (
    solicitudes_para_el_motor as solicitudes_para_el_motor,
)
