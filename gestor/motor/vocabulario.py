# -*- coding: utf-8 -*-
"""El vocabulario del dominio: los códigos de turno y los topes.

Aquí no se decide nada. Son los nombres con los que el resto del motor
habla de un día: qué cuenta como trabajado, qué como descanso, qué
significa estar fuera de vigencia.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

# Cómo se le cuenta a una persona un aviso de validación vive en su propio
# módulo: son ciento catorce líneas de texto que no dependen del horario.
# Los códigos viven en `backend/codigos_turno.py`, que no importa nada y del que
# leen todos. Estuvieron copiados en cinco archivos y uno se quedó sin `CAP`.
# El motor los conoce por sus nombres de siempre; el dominio los llama en
# castellano. La traducción se hace **aquí y solo aquí**: es lo que permitió
# mover los códigos a `dominio.codigos` sin tocar una línea del motor.
#
# `__all__` no es decoración: sin él, una limpieza automática de importaciones
# «sin usar» se llevó por delante estos nombres y el motor entero dejó de
# arrancar. Están usados —desde otros diez archivos—, solo que no en este.
from gestor.dominio.codigos import (  # noqa: F401  (se reexportan al motor)
    ADMINISTRATIVOS as FATIGUE_ADMIN_CODES,
)
from gestor.dominio.codigos import (
    FUERA_DE_VIGENCIA as OUT_OF_VIGENCY_CODE,
)
from gestor.dominio.codigos import (
    NO_TRABAJADOS as NONWORK_CODES,
)
from gestor.dominio.codigos import (
    TODOS as ALL_CODES,
)
from gestor.dominio.codigos import (
    TRABAJADOS as WORK_CODES,
)

__all__ = [
    'ALL_CODES',
    'DOMINGOS_MITAD_EXACTA',
    'FATIGUE_ADMIN_CODES',
    'MAX_DIAS_CONSECUTIVOS',
    'NONWORK_CODES',
    'OUT_OF_VIGENCY_CODE',
    'WORK_CODES',
    'MIN_COMM_PM',
    'MIN_GS_PER_SHIFT',
]

# Máximo de jornadas seguidas.
#
# Es una regla configurable desde la aplicación, con fecha de vigencia, igual
# que las de cobertura: `backend.operation_rules` guarda la política y este
# valor es solo el respaldo cuando todavía no hay ninguna configurada.
#
# El motor no lo lee directamente: usa `maximo_dias_consecutivos()`, que
# devuelve el tope activo para la generación en curso. Así un mes ya publicado
# conserva el tope con el que se hizo aunque después se cambie la política.
MAX_DIAS_CONSECUTIVOS = 10

_LIMITE_RACHA: ContextVar[Optional[int]] = ContextVar('limite_racha', default=None)

# Cuando ningún reparto posible cuadra los domingos de una persona, el mes no
# puede quedarse sin generar: se conserva la mejor propuesta, marcada como
# excepción, y la validación explica quién queda fuera y por qué.
_BALANCE_DOMINICAL_FLEXIBLE: ContextVar[bool] = ContextVar(
    'balance_dominical_flexible', default=False)

# Reparto de domingos.
# La regla de la operación es mitad y mitad: con 4 domingos, 2 trabajados y 2
# descansados; con 5, 2 trabajados y 3 descansados. Es decir, exactamente
# floor(n/2) domingos trabajados, sin margen.
# Poniendo esto en False vuelve el comportamiento antiguo, que admitía también
# ceil(n/2) cuando el número de domingos era impar.
DOMINGOS_MITAD_EXACTA = True

# Compatibilidad histórica: estos nombres eran la política escrita en el código.
# Desde R11 la cobertura se define por área y fecha en `reglas_cobertura`, y se
# consulta con `minimo_cobertura()`. Se conservan como valor de referencia para
# lecturas antiguas, no como regla vigente.
MIN_GS_PER_SHIFT = 1

MIN_COMM_PM = 1

_CACHE_SECUENCIA: dict[int, tuple] = {}

_CACHE_ORDEN_FIRMA: dict[int, tuple] = {}
