"""Contratos de entrada de solicitudes y asignaciones."""
from typing import Optional

from pydantic import BaseModel


class SolicitudNueva(BaseModel):
    empleado_id: int
    tipo: str
    fecha_inicio: str
    fecha_fin: Optional[str] = None
    sin_fecha_fin: bool = False
    modo_periodo: str = 'rango'
    dia_semana_recurrente: Optional[int] = None
    modo_cobertura: str = 'sin_cubrir'
    reemplazo_empleado_id: Optional[int] = None
    intercambio_empleado_id: Optional[int] = None
    turno_solicitado: Optional[str] = None
    dia_descanso_solicitado: Optional[int] = None
    #: Las horas de una capacitación. La pantalla las manda desde siempre; sin
    #: declararlas aquí, Pydantic las tiraba sin decir nada.
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    observacion: str = ''
    #: La casilla «Aprobada por el jefe» del formulario.
    #:
    #: Hay que declararla o Pydantic la tira sin decir nada, que es lo que
    #: pasaba: se marcaba la casilla, salía el aviso verde de guardado, y la
    #: solicitud aparecía en la tabla como **pendiente**. Había que aprobarla
    #: otra vez a mano, y quien no se fijaba se quedaba con una novedad sin
    #: aprobar que el horario no tenía en cuenta.
    aprobada: bool = False


class AsignacionNueva(BaseModel):
    empleado_id: int
    tipo: str
    fechas: list[str] = []
    recurrente_indefinido: bool = False
    dias_semana: list[int] = []
    horario_administrativo: Optional[str] = None
    turno_excepcion: Optional[str] = None
    cubrir_pm: bool = False
    reemplazo_empleado_id: Optional[int] = None
    descripcion: str = ''
    vigente_desde: Optional[str] = None
    estado: str = 'activo'


class AsignacionMasiva(BaseModel):
    empleado_ids: list[int]
    requerimiento: AsignacionNueva
    alcance: str = 'todos'
    area: Optional[str] = None
    aplicar_solo_compatibles: bool = False
    permitir_conflictos_grupo: bool = False
