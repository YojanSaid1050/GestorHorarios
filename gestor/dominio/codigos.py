# -*- coding: utf-8 -*-
"""Los códigos que puede llevar una casilla del horario, y qué significan.

Un único sitio donde está escrito qué es cada código. En la versión anterior
esta información estaba repartida: el motor sabía que ADM-AC no cubre turno, la
auditoría independiente creía que sí, y el Excel tenía su propia lista. Cuando
tres sitios contestan a la misma pregunta, tarde o temprano uno contesta
distinto y nadie se entera hasta que un área se queda un día sin nadie.

Aquí cada código declara tres cosas, y todo lo demás se deduce de ellas:

* **¿la persona trabaja ese día?** — decide si necesita descanso semanal, si le
  cuenta la racha de días seguidos y si suma horas.
* **¿cubre un turno operativo, y cuál?** — decide si sirve para el mínimo del
  área. Es la pregunta que se contestaba mal.
* **¿es una ausencia aprobada?** — vacaciones, incapacidad, permiso: la persona
  no está, pero eso no es un descanso que haya que compensar.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Codigo:
    clave: str
    nombre: str
    trabaja: bool
    ausencia: bool = False
    # Qué franja cubre. `None` = no cubre ninguna. `'AM'`/`'PM'` = esa. La
    # cadena `'propia'` significa «la franja que esa persona tenía ese día»,
    # que es el caso de la jornada administrativa general.
    cubre: str | None = None
    descripcion: str = ''


CODIGOS: dict[str, Codigo] = {c.clave: c for c in (
    Codigo('AM', 'Mañana', trabaja=True, cubre='AM',
           descripcion='Turno operativo de la mañana.'),
    Codigo('PM', 'Tarde', trabaja=True, cubre='PM',
           descripcion='Turno operativo de la tarde.'),
    Codigo('D', 'Descanso', trabaja=False,
           descripcion='Día libre. Es el que la aplicación reparte.'),
    Codigo('ADM-GS', 'Administrativo general', trabaja=True, cubre='propia',
           descripcion=(
               'Jornada administrativa. La persona sigue cubriendo la franja que '
               'le tocaba ese día: cambia lo que hace, no el hueco que deja en el '
               'cuadro. Si además hay que liberar esa cobertura, se dice en '
               'Asignaciones y otra persona la garantiza.')),
    Codigo('ADM-AC', 'Administrativo de Atención al Ciudadano', trabaja=True, cubre=None,
           descripcion=(
               'Horario administrativo propio y permanente de Atención al '
               'Ciudadano, con su propia franja. NO releva a nadie en un turno '
               'operativo: un día en el que solo queda esta persona es un día sin '
               'cobertura, aunque ella esté trabajando.')),
    Codigo('CAP', 'Capacitación', trabaja=True, cubre='propia',
           descripcion='Formación dentro de la jornada; sigue contando como presencia.'),
    Codigo('VAC', 'Vacaciones', trabaja=False, ausencia=True,
           descripcion='Ausencia aprobada.'),
    Codigo('INC', 'Incapacidad', trabaja=False, ausencia=True,
           descripcion='Ausencia aprobada.'),
    Codigo('PER', 'Permiso', trabaja=False, ausencia=True,
           descripcion='Ausencia aprobada.'),
    Codigo('NV', 'No vigente', trabaja=False, ausencia=True,
           descripcion=(
               'La persona todavía no había entrado o ya se había retirado. No es '
               'una ausencia suya: es que ese día no formaba parte de la plantilla, '
               'y por eso no cuenta para ningún reparto ni para ningún mínimo.')),
)}

TODOS = tuple(CODIGOS)
OPERATIVOS = ('AM', 'PM')
DESCANSO = 'D'
FUERA = 'NV'

TRABAJADOS = frozenset(c.clave for c in CODIGOS.values() if c.trabaja)
AUSENCIAS = frozenset(c.clave for c in CODIGOS.values() if c.ausencia)
#: Códigos que sirven para el mínimo de un área. Ojo: no es lo mismo que
#: TRABAJADOS. ADM-AC está en TRABAJADOS y no está aquí, y esa diferencia es
#: justo la que se perdía cuando cada módulo mantenía su propia lista.
CUBREN = frozenset(c.clave for c in CODIGOS.values() if c.cubre is not None)

ADMINISTRATIVOS_POR_AREA = {
    'gestion_social': 'ADM-GS',
    'comunicaciones': 'ADM-GS',
    'atencion_ciudadano': 'ADM-AC',
}


def existe(clave: str) -> bool:
    return clave in CODIGOS


def trabaja(clave: str) -> bool:
    """¿La persona está trabajando ese día?"""
    c = CODIGOS.get(clave)
    return bool(c and c.trabaja)


def franja_que_cubre(clave: str, franja_propia: str | None = None) -> str | None:
    """Qué turno operativo cubre esta casilla, si es que cubre alguno.

    `franja_propia` es el turno que esa persona tenía ese día antes de que le
    pusieran la jornada administrativa. Solo se usa para los códigos que cubren
    «la propia»; para el resto sobra.
    """
    c = CODIGOS.get(clave)
    if c is None or c.cubre is None:
        return None
    if c.cubre == 'propia':
        return franja_propia if franja_propia in OPERATIVOS else None
    return c.cubre


def describir(clave: str) -> str:
    c = CODIGOS.get(clave)
    return c.descripcion if c else ''


# ---------------------------------------------------------------------------
# Nombres que usa el motor
# ---------------------------------------------------------------------------
# El motor viene de la versión anterior, donde estas listas vivían en su propio
# archivo. Se conservan los nombres para no reescribir siete mil líneas por un
# cambio de vocabulario, pero **se derivan de las declaraciones de arriba** en
# vez de escribirse otra vez. Ese es todo el arreglo: antes eran cinco listas a
# mano en cinco archivos, y una se quedó sin `CAP`; justo el núcleo normativo,
# que es la última red. Una capacitación en medio de una racha la partía a sus
# ojos, y veintiuna jornadas seguidas pasaban el tope de catorce.
NO_TRABAJADOS = frozenset(c.clave for c in CODIGOS.values()
                          if not c.trabaja and c.clave != FUERA)
FUERA_DE_VIGENCIA = FUERA
ADMINISTRATIVOS = frozenset(ADMINISTRATIVOS_POR_AREA.values())
