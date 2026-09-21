"""Interfaz compatible; la implementación se organiza por responsabilidades.

Ver docs/ARQUITECTURA.md.
"""
from gestor.motor.reparaciones.base import PUENTE_ADM_FATIGA as PUENTE_ADM_FATIGA
from gestor.motor.reparaciones.base import (
    _admite_descanso as _admite_descanso,
)
from gestor.motor.reparaciones.base import (
    _cobertura_area_completa as _cobertura_area_completa,
)
from gestor.motor.reparaciones.base import (
    _contar_violaciones_max_dias as _contar_violaciones_max_dias,
)
from gestor.motor.reparaciones.base import (
    _firma_estado_turnos as _firma_estado_turnos,
)
from gestor.motor.reparaciones.base import (
    _habilitar_descanso_max6_con_reajuste as _habilitar_descanso_max6_con_reajuste,
)
from gestor.motor.reparaciones.base import (
    _orden_dias_estable as _orden_dias_estable,
)
from gestor.motor.reparaciones.base import (
    _restaurar_descanso_automatico_de_semana as _restaurar_descanso_automatico_de_semana,
)
from gestor.motor.reparaciones.base import (
    _restore_base_work as _restore_base_work,
)
from gestor.motor.reparaciones.base import (
    _restore_estado_horario as _restore_estado_horario,
)
from gestor.motor.reparaciones.base import (
    _snapshot_estado_horario as _snapshot_estado_horario,
)
from gestor.motor.reparaciones.cobertura import (
    _asegurar_cobertura_minima as _asegurar_cobertura_minima,
)
from gestor.motor.reparaciones.cobertura import (
    reparar_cobertura_adm_gs as reparar_cobertura_adm_gs,
)
from gestor.motor.reparaciones.cobertura import (
    reparar_cobertura_minima as reparar_cobertura_minima,
)
from gestor.motor.reparaciones.domingos import (
    reparar_balance_domingos_post_reglas as reparar_balance_domingos_post_reglas,
)
from gestor.motor.reparaciones.fatiga import (
    _adelantar_turno_tras_descanso as _adelantar_turno_tras_descanso,
)
from gestor.motor.reparaciones.fatiga import (
    limpiar_puentes_fatiga_obsoletos as limpiar_puentes_fatiga_obsoletos,
)
from gestor.motor.reparaciones.fatiga import (
    reparar_fatiga_laboral as reparar_fatiga_laboral,
)
from gestor.motor.reparaciones.rachas import (
    _intentar_reparacion_max6_area_conjunta as _intentar_reparacion_max6_area_conjunta,
)
from gestor.motor.reparaciones.rachas import (
    _intentar_reparacion_max6_coordinada as _intentar_reparacion_max6_coordinada,
)
from gestor.motor.reparaciones.rachas import (
    reparar_max_dias_consecutivos as reparar_max_dias_consecutivos,
)
from gestor.motor.reparaciones.rotacion import (
    reparar_cambio_semanal as reparar_cambio_semanal,
)
from gestor.motor.reparaciones.rotacion import (
    reparar_habitualidad as reparar_habitualidad,
)
