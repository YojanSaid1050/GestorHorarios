"""Presupuesto cooperativo para las búsquedas del generador de horarios.

Las reparaciones automáticas (máximo 7 días, fatiga, balance dominical y el
solver coordinado por área) exploran combinaciones que crecen de forma
multiplicativa. Cuando un conflicto no tiene solución —por ejemplo, una
asignación directa que encadena una racha con un mes oficial congelado— esas
exploraciones podían consumir minutos por cada candidato y dejar la aplicación
colgada durante toda la generación.

Este módulo define un presupuesto por generación con dos límites:

* tiempo de pared, para que la interfaz siempre reciba respuesta;
* número de nodos explorados, para que el resultado sea reproducible aunque la
  máquina sea más lenta o más rápida.

El presupuesto es cooperativo: cada bucle costoso pregunta ``queda()`` antes de
seguir. Al agotarse, la reparación abandona la rama y el horario conserva el
conflicto, que la validación final reporta con un mensaje comprensible. Nunca se
inventa una solución ni se oculta el problema.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Optional


def _entero_env(nombre: str, defecto: int) -> int:
    try:
        valor = int(os.environ.get(nombre, '') or defecto)
    except (TypeError, ValueError):
        return defecto
    return valor if valor > 0 else defecto


def _flotante_env(nombre: str, defecto: float) -> float:
    try:
        valor = float(os.environ.get(nombre, '') or defecto)
    except (TypeError, ValueError):
        return defecto
    return valor if valor > 0 else defecto


# El límite que decide de verdad es el de nodos: es idéntico en cualquier
# máquina, así que la misma entrada produce siempre el mismo horario y el mismo
# hash. El límite de tiempo es solo una red de seguridad para equipos muy
# lentos; en condiciones normales nunca llega a activarse.
NODOS_POR_CANDIDATO = _entero_env('GESTOR_HORARIOS_NODOS_CANDIDATO', 20_000)
SEGUNDOS_POR_CANDIDATO = _flotante_env('GESTOR_HORARIOS_SEGUNDOS_CANDIDATO', 40.0)

# Exploración completa de un área (Top 5 + diversificación). También se corta
# por nodos para que el resultado sea reproducible.
NODOS_POR_AREA = _entero_env('GESTOR_HORARIOS_NODOS_AREA', 150_000)
NODOS_POR_AREA_CON_TOP5 = _entero_env('GESTOR_HORARIOS_NODOS_AREA_TOP5', 60_000)
SEGUNDOS_POR_AREA = _flotante_env('GESTOR_HORARIOS_SEGUNDOS_AREA', 240.0)
SEGUNDOS_POR_AREA_CON_TOP5 = _flotante_env('GESTOR_HORARIOS_SEGUNDOS_AREA_TOP5', 180.0)

# Tope duro de combinaciones evaluadas dentro de un único ``product`` de
# reparación. Evita que una sola rama consuma el presupuesto entero.
MAX_COMBINACIONES_REPARACION = _entero_env('GESTOR_HORARIOS_MAX_COMBINACIONES', 600)
MAX_COMBINACIONES_SOLVER_AREA = _entero_env('GESTOR_HORARIOS_MAX_COMBINACIONES_AREA', 4_000)


class PresupuestoBusqueda:
    """Contador de tiempo y nodos para una búsqueda acotada."""

    __slots__ = ('segundos', 'max_nodos', '_inicio', 'nodos', '_motivo')

    def __init__(self, segundos: float, max_nodos: int) -> None:
        self.segundos = float(segundos)
        self.max_nodos = int(max_nodos)
        self._inicio = time.perf_counter()
        self.nodos = 0
        self._motivo: Optional[str] = None

    # -- consulta -----------------------------------------------------
    @property
    def agotado(self) -> bool:
        return self._motivo is not None

    @property
    def motivo(self) -> Optional[str]:
        return self._motivo

    @property
    def transcurrido(self) -> float:
        return time.perf_counter() - self._inicio

    def queda(self, coste: int = 1) -> bool:
        """Consume ``coste`` nodos y dice si la búsqueda puede continuar."""
        if self._motivo is not None:
            return False
        self.nodos += int(coste)
        if self.nodos > self.max_nodos:
            self._motivo = 'nodos'
            return False
        # ``perf_counter`` es barato, pero no hace falta consultarlo en cada
        # nodo: basta con revisarlo cada 256 para acotar el tiempo real.
        if self.nodos % 256 == 0 and self.transcurrido > self.segundos:
            self._motivo = 'tiempo'
            return False
        return True

    def detener(self, motivo: str = 'externo') -> None:
        if self._motivo is None:
            self._motivo = motivo

    def resumen(self) -> dict:
        return {
            'nodos': self.nodos,
            'segundos': round(self.transcurrido, 3),
            'agotado': self.agotado,
            'motivo': self._motivo,
        }


_local = threading.local()


def presupuesto_actual() -> Optional[PresupuestoBusqueda]:
    return getattr(_local, 'presupuesto', None)


def queda_presupuesto(coste: int = 1) -> bool:
    """True si no hay presupuesto activo o si todavía queda margen."""
    actual = presupuesto_actual()
    if actual is None:
        return True
    return actual.queda(coste)


def presupuesto_agotado() -> bool:
    actual = presupuesto_actual()
    return bool(actual and actual.agotado)


@contextmanager
def presupuesto_busqueda(
    segundos: Optional[float] = None,
    nodos: Optional[int] = None,
    reutilizar: bool = True,
):
    """Activa un presupuesto para el bloque.

    Con ``reutilizar=True`` (por defecto) un presupuesto exterior ya activo se
    conserva: así la exploración completa de un área impone su propio techo y
    las llamadas internas no lo reinician.
    """
    actual = presupuesto_actual()
    if actual is not None and reutilizar:
        yield actual
        return
    nuevo = PresupuestoBusqueda(
        SEGUNDOS_POR_CANDIDATO if segundos is None else segundos,
        NODOS_POR_CANDIDATO if nodos is None else nodos,
    )
    anterior = actual
    _local.presupuesto = nuevo
    try:
        yield nuevo
    finally:
        _local.presupuesto = anterior


def limitar(iterable, maximo: int, coste: int = 1):
    """Recorre ``iterable`` respetando el presupuesto y un tope local.

    El tope local solo corta esta rama; no agota el presupuesto general, para
    que las siguientes reparaciones conserven su margen.
    """
    contador = 0
    for elemento in iterable:
        if contador >= maximo or not queda_presupuesto(coste):
            return
        contador += 1
        yield elemento
