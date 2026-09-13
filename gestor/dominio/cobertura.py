# -*- coding: utf-8 -*-
"""Quién cubre qué, y cuánta gente hace falta. Un solo sitio.

Esta es la pieza que más veces ha fallado, y siempre por el mismo motivo: había
dos implementaciones. Una vivía en `coverage_rules` y la usaba la planificación
para decidir a quién poner en cada turno; la otra vivía en `motor/comun` y la
usaban la reparación y la validación para juzgar el resultado. Cada regla nueva
había que cablearla en las dos, y cada vez que se olvidó una, la aplicación
generó horarios que su propia validación daba por buenos.

Pasó tres veces seguidas y las tres se vieron en la oficina, no en las pruebas:

* la exención de festivos de Atención al Ciudadano quedó escrita en una sola de
  las dos, así que el motor la aplicaba y la validación no la veía;
* los días de cobertura por persona —quién puede cubrir martes y sábados y
  quién no— se cablearon en el conteo del área y se olvidaron en el conteo por
  turno, que era justo el caso para el que se habían inventado;
* la jornada administrativa de Atención al Ciudadano contaba como cobertura en
  la auditoría y no en el motor.

Aquí hay **una** respuesta a cada pregunta, y todo lo demás la consulta:

* ¿qué franja cubre esta casilla?          → `franja_cubierta`
* ¿cuánta gente hay cubriendo?             → `conteo`
* ¿cuánta gente exige el área?             → `ReglaCobertura` + `exigido`
* ¿este día cumple?                        → `incumplimientos`
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from gestor.dominio import codigos

AREAS = ('gestion_social', 'atencion_ciudadano', 'comunicaciones')
NOMBRES_AREA = {
    'gestion_social': 'Gestión Social',
    'atencion_ciudadano': 'Atención al Ciudadano',
    'comunicaciones': 'Comunicaciones',
}


# ---------------------------------------------------------------- la regla

@dataclass(frozen=True)
class ReglaCobertura:
    """Cuánta gente pide un área, desde una fecha en adelante.

    Hay dos naturalezas distintas y conviene no confundirlas, porque se tratan
    de forma distinta en todo el motor:

    * el **suelo** (`am_minimo`, `pm_minimo`, `minimo_area`) es una obligación
      operativa: un turno sin nadie es un turno sin nadie, y no se salta jamás;
    * el **techo** y el **reparto habitual** (`am_maximo`, `am_objetivo`…) son
      política de distribución: una asignación decidida a mano está por encima.

    `minimo_area` es «al menos tanta gente trabajando, en la franja que sea».
    Se usa donde el área no cubre dos franjas completas y lo que importa es que
    quede alguien, no dónde.
    """

    area: str
    vigente_desde: str
    am_minimo: int = 0
    pm_minimo: int = 0
    minimo_area: int = 0
    am_objetivo: Optional[int] = None
    pm_objetivo: Optional[int] = None
    am_maximo: Optional[int] = None
    pm_maximo: Optional[int] = None
    nota: str = ''
    editable: bool = True

    def como_dict(self) -> dict:
        return {
            'area': self.area, 'vigente_desde': self.vigente_desde,
            'am_minimo': self.am_minimo, 'pm_minimo': self.pm_minimo,
            'minimo_area': self.minimo_area,
            'am_objetivo': self.am_objetivo, 'pm_objetivo': self.pm_objetivo,
            'am_maximo': self.am_maximo, 'pm_maximo': self.pm_maximo,
            'nota': self.nota, 'editable': self.editable,
        }


# ------------------------------------------------- qué cubre una casilla

def dias_que_cubre(persona: dict) -> Optional[frozenset[int]]:
    """Los días de la semana en los que esta persona cuenta para el mínimo.

    `None` —lo normal— significa todos. Una lista significa solo esos, con el
    lunes en 0. La lista vacía significa ninguno: alguien que trabaja pero al
    que no se le puede encomendar la cobertura del área.

    Se guarda en positivo y no como excepciones. Escrito al revés («estos días
    NO cubre») había que acordarse de invertirlo en cada sitio que lo mirase, y
    el sitio que se olvidó de invertirlo fue el conteo por turno.
    """
    dias = persona.get('cobertura_dias')
    if dias is None:
        # La base lo guarda como texto; si viene así, se lee igual. Aceptar las
        # dos formas evita que el motor y la persistencia tengan que ponerse de
        # acuerdo en cuál usar, que es de donde salían las discrepancias.
        crudo = persona.get('cobertura_dias_json')
        if crudo in (None, ''):
            return None
        dias = desde_texto(crudo)
        if dias is None:
            return None
    return frozenset(int(d) for d in dias)


def cubre_ese_dia(persona: dict, casilla: dict) -> bool:
    dias = dias_que_cubre(persona)
    if dias is None:
        return True
    numero = casilla.get('dia_semana_numero')
    return numero is not None and int(numero) in dias


def franja_cubierta(persona: dict, casilla: dict) -> Optional[str]:
    """Qué turno operativo cubre esta casilla: 'AM', 'PM' o ninguno.

    Junta las tres cosas que deciden la respuesta, que antes se miraban por
    separado en sitios distintos:

    1. el código (ver `dominio.codigos`): ADM-AC no cubre nada, ADM-GS conserva
       la franja que la persona tenía;
    2. la decisión explícita de liberar la cobertura, tomada en «Asignaciones y
       ajustes» y guardada en `cobertura_operativa`;
    3. los días de cobertura de esa persona.
    """
    if not cubre_ese_dia(persona, casilla):
        return None

    turno = str(casilla.get('turno') or '')
    codigo = codigos.CODIGOS.get(turno)
    if codigo is None or codigo.cubre is None:
        return None
    if codigo.cubre in codigos.OPERATIVOS:
        return codigo.cubre

    # Códigos que conservan «la franja propia». La decisión explícita manda
    # sobre el turno que la persona traía.
    decidida = casilla.get('cobertura_operativa')
    if decidida in codigos.OPERATIVOS:
        return str(decidida)
    for campo in ('turno_operativo_origen', 'turno_original', 'turno_base'):
        candidato = casilla.get(campo)
        if candidato in codigos.OPERATIVOS:
            return str(candidato)
    # Sin franja propia no hay hueco que conservar: es el administrativo
    # permanente, que hace su jornada y no releva a nadie.
    return None


def esta_vigente(casilla: dict) -> bool:
    """¿Esa persona formaba parte de la plantilla ese día?

    Quien todavía no había entrado o ya se había retirado no cuenta para nada:
    ni suma al mínimo ni se le reprocha no descansar.
    """
    if casilla.get('vigente') is False:
        return False
    return str(casilla.get('turno') or '') != codigos.FUERA


# ------------------------------------------------------------- el conteo

@dataclass(frozen=True)
class Conteo:
    am: int = 0
    pm: int = 0
    #: Personas cubriendo alguna franja. No es `am + pm`: es la cuenta de
    #: personas, y sirve para el mínimo del área.
    cubriendo: int = 0
    #: Personas del área vigentes ese día, cubran o no.
    vigentes: int = 0
    #: De esas, las que podrían tomar un turno operativo: se excluye a quien
    #: tiene jornada administrativa permanente, porque su horario es otro y no
    #: releva a nadie. Es el tope de lo que se le puede exigir al área.
    operativos: int = 0
    #: Ese día toda el área hace jornada administrativa; nadie está en AM ni en
    #: PM y es correcto.
    viernes_administrativo: bool = False


def _casilla(persona: dict, fecha: str) -> Optional[dict]:
    for d in persona.get('dias', ()):
        if d.get('fecha') == fecha:
            return d
    return None


def conteo(horario: Sequence[dict], area: str, fecha: str,
           excluir: Optional[int] = None) -> Conteo:
    """Cuánta gente del área cubre cada franja ese día."""
    am = pm = cubriendo = vigentes = operativos = 0
    administrativo = False
    for persona in horario:
        if persona.get('area') != area:
            continue
        if excluir is not None and int(persona.get('empleado_id') or 0) == int(excluir):
            continue
        casilla = _casilla(persona, fecha)
        if casilla is None or not esta_vigente(casilla):
            continue
        vigentes += 1
        if persona.get('tipo_turno') != 'administrativo':
            operativos += 1
        # La marca del calendario dice que ese viernes **toca** jornada
        # administrativa. Que la haya de verdad es otra cosa, y es lo que
        # importa aquí: la exención existe porque ese día el área entera está en
        # ADM y nadie en AM ni en PM, a propósito. Si nadie está en ADM, la
        # premisa es falsa y el día se mide como cualquier otro.
        #
        # Sin esta segunda condición, Navidad y Viernes Santo —que caen en el
        # último viernes de su mes— quedaban exentos de comprobar cobertura
        # aunque se programan como festivos y todo el mundo trabaja en AM o PM.
        # Un área podía quedarse sin nadie esos días y no salía en ninguna
        # pantalla: el mismo silencio que dejó el viernes 2 de octubre.
        if (casilla.get('es_ultimo_viernes_administrativo')
                and str(casilla.get('turno') or '') in codigos.ADMINISTRATIVOS):
            administrativo = True
        franja = franja_cubierta(persona, casilla)
        if franja == 'AM':
            am += 1
            cubriendo += 1
        elif franja == 'PM':
            pm += 1
            cubriendo += 1
    return Conteo(am=am, pm=pm, cubriendo=cubriendo, vigentes=vigentes,
                  operativos=operativos, viernes_administrativo=administrativo)


def exigido(pedido: int, vigentes: int) -> int:
    """Lo que de verdad se le puede exigir al área ese día.

    Un mínimo nunca puede reclamar a toda el área a la vez: alguien tiene que
    poder descansar. Si el área tiene tres personas y el mínimo pide tres, se
    exigen dos. Sin esta válvula, un área pequeña con una baja hace imposible
    cualquier horario y la aplicación se queda sin poder generar el mes.
    """
    if pedido <= 0 or vigentes <= 0:
        return 0
    return max(0, min(int(pedido), vigentes - 1))


# ------------------------------------------------------- juzgar un día

@dataclass(frozen=True)
class Incumplimiento:
    norma: str
    area: str
    fecha: str
    mensaje: str
    #: Cierto cuando el día viene de un mes ya publicado y no se puede tocar
    #: desde aquí. Se informa igual —callarlo fue el error de la versión
    #: anterior— pero no se le reprocha al mes que se está creando.
    heredado: bool = False


def _es_heredado(horario: Sequence[dict], area: str, fecha: str) -> bool:
    casillas = [c for p in horario if p.get('area') == area
                for c in (_casilla(p, fecha),) if c]
    if not casillas:
        return False
    return all(str(c.get('origen') or '').startswith('base_') or c.get('bloqueado')
               for c in casillas)


def incumplimientos(horario: Sequence[dict], area: str, fecha: str,
                    regla: ReglaCobertura) -> list[Incumplimiento]:
    """Qué le falta a ese día en esa área. Lista vacía = cumple."""
    cuenta = conteo(horario, area, fecha)
    if cuenta.vigentes == 0:
        return []
    # El último viernes administrativo el área entera hace jornada ADM: ese día
    # nadie está en AM ni en PM y es a propósito.
    if cuenta.viernes_administrativo:
        return []

    heredado = _es_heredado(horario, area, fecha)
    nombre = NOMBRES_AREA.get(area, area)
    fallos: list[Incumplimiento] = []

    def anotar(norma: str, mensaje: str) -> None:
        fallos.append(Incumplimiento(norma, area, fecha, mensaje, heredado))

    pide_am = exigido(regla.am_minimo, cuenta.operativos)
    if pide_am and cuenta.am < pide_am:
        anotar('cobertura AM',
               f'{nombre} el {fecha}: {cuenta.am} persona(s) en la mañana y hacen falta {pide_am}.')

    pide_pm = exigido(regla.pm_minimo, cuenta.operativos)
    if pide_pm and cuenta.pm < pide_pm:
        anotar('cobertura PM',
               f'{nombre} el {fecha}: {cuenta.pm} persona(s) en la tarde y hacen falta {pide_pm}.')

    pide_area = exigido(regla.minimo_area, cuenta.operativos)
    if pide_area and cuenta.cubriendo < pide_area:
        anotar('cobertura del área',
               f'{nombre} el {fecha}: {cuenta.cubriendo} persona(s) cubriendo turno y '
               f'hacen falta {pide_area}, en la franja que sea.')

    if regla.am_maximo is not None and cuenta.am > int(regla.am_maximo):
        anotar('techo de la mañana',
               f'{nombre} el {fecha}: {cuenta.am} personas en la mañana y caben {regla.am_maximo}.')
    if regla.pm_maximo is not None and cuenta.pm > int(regla.pm_maximo):
        anotar('techo de la tarde',
               f'{nombre} el {fecha}: {cuenta.pm} personas en la tarde y caben {regla.pm_maximo}.')

    return fallos


def revisar(horario: Sequence[dict], fechas: Iterable[str],
            reglas: dict[str, ReglaCobertura]) -> list[Incumplimiento]:
    """Todos los incumplimientos de cobertura de un horario."""
    salida: list[Incumplimiento] = []
    for area in AREAS:
        regla = reglas.get(area)
        if regla is None:
            continue
        for fecha in fechas:
            salida.extend(incumplimientos(horario, area, fecha, regla))
    return salida


# ------------------------------------------- ¿puedo mover a esta persona?

def cabe_el_cambio(horario: Sequence[dict], persona: dict, casilla: dict,
                   turno_nuevo: str, regla: ReglaCobertura,
                   respetar_techo: bool = True) -> bool:
    """¿El área conserva su cobertura si esa persona pasa a ese turno?

    `respetar_techo` distingue las dos naturalezas de la regla. El suelo no se
    salta nunca. El techo sí lo salta una decisión tomada a mano: el usuario ya
    dijo que ese día quiere a esa persona en ese turno.
    """
    area = persona.get('area')
    fecha = casilla['fecha']
    antes = franja_cubierta(persona, casilla)
    despues = franja_cubierta(persona, {**casilla, 'turno': turno_nuevo})

    cuenta = conteo(horario, area, fecha)
    nuevos = {'AM': cuenta.am, 'PM': cuenta.pm}
    cubriendo = cuenta.cubriendo
    if antes in nuevos:
        nuevos[antes] -= 1
        cubriendo -= 1
    if despues in nuevos:
        nuevos[despues] += 1
        cubriendo += 1

    if nuevos['AM'] < exigido(regla.am_minimo, cuenta.operativos):
        return False
    if nuevos['PM'] < exigido(regla.pm_minimo, cuenta.operativos):
        return False
    if cubriendo < exigido(regla.minimo_area, cuenta.operativos):
        return False
    if respetar_techo and despues in nuevos:
        techo = regla.am_maximo if despues == 'AM' else regla.pm_maximo
        if techo is not None and nuevos[despues] > int(techo):
            return False
    return True


# ---------------------------------------------------------------------------
# Los días de cobertura, en texto y en lista
# ---------------------------------------------------------------------------
# Antes esto era un archivo aparte (`cobertura_personal`) y ahí estaba el
# problema: quien preguntaba «¿esta persona cubre hoy?» tenía que acordarse de
# consultarlo, y el conteo por turno se olvidó. Ahora vive junto a la única
# función que contesta esa pregunta, `franja_cubierta`, que ya lo tiene en
# cuenta sin que nadie tenga que acordarse.

def desde_texto(valor: Optional[str]) -> Optional[list[int]]:
    """Lee los días guardados. Cadena vacía = todos los días, que es lo normal.

    Se distingue «todos» (`None`) de «ninguno» (`[]`) a propósito: son dos cosas
    distintas y confundirlas dejaba a alguien contando siempre o nunca.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if texto == '':
        return None
    if texto in {'[]', 'ninguno'}:
        return []
    numeros = []
    for trozo in texto.replace(';', ',').split(','):
        trozo = trozo.strip()
        if not trozo:
            continue
        try:
            numero = int(trozo)
        except ValueError:
            continue
        if 0 <= numero <= 6:
            numeros.append(numero)
    return normalizar(numeros)


def a_texto(dias: Optional[Iterable[int]]) -> str:
    if dias is None:
        return ''
    lista = normalizar(dias)
    return ','.join(str(d) for d in lista) if lista else '[]'


def normalizar(dias: Iterable[int]) -> list[int]:
    """Ordenados y sin repetir, para que dos listas iguales se guarden igual."""
    return sorted({int(d) for d in dias if 0 <= int(d) <= 6})


def cubre(dias: Optional[Iterable[int]], dia_semana: Optional[int]) -> bool:
    if dias is None:
        return True
    if dia_semana is None:
        return False
    return int(dia_semana) in {int(d) for d in dias}


def cubre_empleado(empleado: dict, dia_semana: Optional[int]) -> bool:
    """¿Esta persona cuenta para el mínimo de su área ese día de la semana?"""
    return cubre(dias_que_cubre(empleado), dia_semana)


def describir(dias: Optional[Iterable[int]]) -> str:
    """En castellano, para la pantalla."""
    from gestor.dominio.calendario import NOMBRES_DIAS
    if dias is None:
        return 'todos los días'
    lista = normalizar(dias)
    if not lista:
        return 'ningún día'
    nombres = [NOMBRES_DIAS[d] for d in lista]
    if len(nombres) == 1:
        return nombres[0]
    return ', '.join(nombres[:-1]) + ' y ' + nombres[-1]
