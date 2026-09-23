# -*- coding: utf-8 -*-
"""Las reglas que no se negocian.

Casi todo en esta aplicación es configurable: el reparto por área, el máximo de
jornadas seguidas, los festivos, quién descansa qué día. Eso está bien, porque
la oficina cambia y la aplicación tiene que poder cambiar con ella.

Pero hay un puñado de cosas que no deberían depender de que alguien las
configure bien. Vienen de la ley o de la naturaleza del trabajo, y si alguna vez
se rompen no es una preferencia mal puesta: es un horario que no se puede
publicar. Esas están aquí.

**No tienen pantalla, ni ajuste, ni forma de desactivarlas desde la aplicación.**
No aparecen en Configuración ni en ningún menú. Para cambiar una hay que editar
este archivo y volver a compilar el programa, que es exactamente la barrera que
se quiere: obliga a que sea una decisión pensada y no un clic.

Se comprueban siempre, al final de generar cualquier mes, y lo que encuentran
son errores —no advertencias—, así que un mes que las incumple no se puede
marcar como oficial.

Si añades una regla aquí, escribe también de dónde sale. Dentro de un año nadie
se acordará, y una regla sin motivo escrito acaba borrándose por parecer
arbitraria.

## Lo que se probó a meter aquí y no encajaba

«Ningún área se queda sin nadie un día laborable» parecía candidata, y no lo es:
cuántas personas cubre cada área y cuál es su mínimo obligatorio se configura a
propósito, con fecha de vigencia, porque cambia con la oficina. Un área de una
sola persona que pide el día libre se queda vacía, y eso es una decisión que
alguien puede tomar. Ponerla aquí convertía en «no publicable» algo que las
reglas de cobertura ya vigilan y que además admite excepciones legítimas.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

# Códigos con los que el horario dice que alguien trabajó ese día.
#
# Se leen del vocabulario del motor y no se vuelven a escribir aquí. Estuvieron
# escritos a mano y se quedaron sin `CAP`, que es un día de capacitación y sí es
# jornada trabajada. El efecto era grave y silencioso: una capacitación aprobada
# en medio de una racha la partía a ojos de este archivo, así que veintiuna
# jornadas seguidas con una capacitación por el medio no incumplían el tope de
# catorce, y la aplicación daba ese mes por publicable. Justo aquí, que es la
# última red y la única que no se puede desactivar desde ninguna pantalla.
from gestor.dominio.codigos import FUERA_DE_VIGENCIA, TRABAJADOS

TRABAJO = TRABAJADOS
# Fuera de vigencia: la persona ni siquiera pertenecía a la plantilla ese día.
FUERA = FUERA_DE_VIGENCIA


@dataclass(frozen=True)
class Regla:
    """Una regla del núcleo, con su motivo escrito al lado."""

    clave: str
    titulo: str
    fundamento: str


# --------------------------------------------------------------------------
# Las reglas
# --------------------------------------------------------------------------

DESCANSO_SEMANAL = Regla(
    clave='descanso_semanal',
    titulo='Toda persona descansa al menos un día por semana',
    fundamento=(
        'Código Sustantivo del Trabajo, artículo 172: descanso dominical o '
        'compensatorio remunerado. Una semana entera sin ningún día no laborado '
        'no es una preferencia de la oficina, es una jornada que no se puede '
        'pagar como está.'
    ),
)

TOPE_ABSOLUTO_JORNADAS = Regla(
    clave='tope_absoluto_jornadas',
    titulo='Nadie encadena más de catorce jornadas seguidas',
    fundamento=(
        'El máximo de jornadas seguidas es configurable —de fábrica son diez— y '
        'puede subirse desde Configuración para que el reparto de domingos tenga '
        'margen. Pero catorce días seguidos son dos semanas sin descansar, y eso '
        'ya no es un ajuste de reparto: es que alguien se quedó sin su descanso '
        'semanal dos veces seguidas. Este tope no se puede subir desde ninguna '
        'pantalla.'
    ),
)

UN_TURNO_POR_DIA = Regla(
    clave='un_turno_por_dia',
    titulo='Cada persona tiene exactamente un turno cada día',
    fundamento=(
        'No es una regla laboral sino de coherencia: una casilla vacía o dos '
        'turnos el mismo día significan que el horario está mal armado. Se '
        'comprueba aquí porque un horario así no se puede publicar aunque todo '
        'lo demás cuadre.'
    ),
)

SIN_DOBLE_JORNADA = Regla(
    clave='sin_doble_jornada',
    titulo='Nadie hace mañana y tarde el mismo día',
    fundamento=(
        'La jornada operativa es de una franja. Cubrir las dos el mismo día son '
        'catorce horas seguidas, que excede la jornada máxima legal diaria y '
        'además deja a la persona sin el descanso entre jornadas.'
    ),
)

REGLAS = (
    UN_TURNO_POR_DIA,
    SIN_DOBLE_JORNADA,
    DESCANSO_SEMANAL,
    TOPE_ABSOLUTO_JORNADAS,
)

# El tope absoluto. No se lee de la configuración a propósito.
MAXIMO_ABSOLUTO_JORNADAS = 14


# --------------------------------------------------------------------------
# La comprobación
# --------------------------------------------------------------------------

def _dias_vigentes(fila: dict) -> list[dict]:
    return [d for d in fila.get('dias', [])
            if d.get('vigente', True) and d.get('turno') != FUERA]


def _un_turno_por_dia(horario: list[dict]) -> list[str]:
    fallos = []
    for fila in horario:
        vistas = set()
        for d in fila.get('dias', []):
            fecha = d.get('fecha')
            if fecha in vistas:
                fallos.append(f"{fila['nombre']}: el {fecha} aparece dos veces en su fila.")
            vistas.add(fecha)
            if d.get('vigente', True) and not str(d.get('turno') or '').strip():
                fallos.append(f"{fila['nombre']}: el {fecha} se quedó sin turno.")
    return fallos


def _sin_doble_jornada(horario: list[dict]) -> list[str]:
    # Con la forma actual del horario —un turno por casilla— esto no puede
    # ocurrir, y aun así se comprueba: es barato, y el día que la estructura
    # cambie será esta comprobación la que avise antes de que salga publicado.
    fallos = []
    for fila in horario:
        for d in _dias_vigentes(fila):
            turno = str(d.get('turno') or '')
            if '+' in turno or '/' in turno:
                fallos.append(
                    f"{fila['nombre']} {d['fecha']}: figura con dos jornadas el mismo día ({turno}).")
    return fallos


def _descanso_semanal(horario: list[dict]) -> list[str]:
    fallos = []
    for fila in horario:
        por_semana: dict[str, list[dict]] = defaultdict(list)
        for d in _dias_vigentes(fila):
            por_semana[str(d.get('lunes_semana') or '')].append(d)
        semanas = sorted(por_semana)
        for lunes, dias in sorted(por_semana.items()):
            # Solo se juzgan las semanas completas dentro del período: una semana
            # de la que solo asoman dos días no dice nada sobre el descanso.
            if len(dias) < 7:
                continue
            # La primera semana del período se comparte con el mes anterior: su
            # lunes suele caer en el mes de al lado. Si el descanso de esa
            # persona se dio en un día que este mes no ve, denunciarlo aquí sería
            # acusar de algo que sí ocurrió, solo que en el horario de al lado.
            # Se comprobó con septiembre de 2026: su primera semana empieza el 31
            # de agosto, que pertenece a agosto.
            if semanas and lunes == semanas[0]:
                continue
            # Lo mismo con lo que llega heredado y ya publicado: eso lo juzgó su
            # propio mes cuando se publicó.
            if any(str(d.get('origen') or '').startswith('base_') for d in dias):
                continue
            if all(d['turno'] in TRABAJO for d in dias):
                fallos.append(
                    f"{fila['nombre']}: la semana del {lunes} no tiene ni un día de descanso.")
    return fallos


def _tope_absoluto(horario: list[dict]) -> list[str]:
    fallos = []
    for fila in horario:
        racha, desde, peor, peor_desde = 0, None, 0, None
        for d in sorted(_dias_vigentes(fila), key=lambda x: x['fecha']):
            if d['turno'] in TRABAJO:
                racha += 1
                if racha == 1:
                    desde = d['fecha']
                # El tope limita decisiones nuevas, no reescribe las bases
                # manuales. Los días históricos sí cuentan si la racha continúa.
                if racha > peor and not str(d.get('origen') or '').startswith('base_'):
                    peor, peor_desde = racha, desde
            else:
                racha = 0
        if peor > MAXIMO_ABSOLUTO_JORNADAS:
            fallos.append(
                f"{fila['nombre']}: encadena {peor} jornadas seguidas desde el {peor_desde}; "
                f'el tope que no se puede levantar es {MAXIMO_ABSOLUTO_JORNADAS}.')
    return fallos


COMPROBACIONES = {
    UN_TURNO_POR_DIA.clave: _un_turno_por_dia,
    SIN_DOBLE_JORNADA.clave: _sin_doble_jornada,
    DESCANSO_SEMANAL.clave: _descanso_semanal,
    TOPE_ABSOLUTO_JORNADAS.clave: _tope_absoluto,
}


def revisar(horario: list[dict]) -> list[str]:
    """Pasa el horario por las reglas del núcleo y devuelve lo que incumple.

    Vacío quiere decir que el mes respeta lo innegociable. Cada mensaje empieza
    por el título de la regla, para que quien lo lea sepa que no está ante una
    preferencia mal configurada sino ante algo que no se puede publicar.
    """
    problemas: list[str] = []
    for regla in REGLAS:
        for fallo in COMPROBACIONES[regla.clave](horario or []):
            problemas.append(f'{regla.titulo}. {fallo}')
    return problemas


def catalogo() -> list[dict]:
    """Las reglas del núcleo con su fundamento, para la auditoría y la documentación.

    No es para una pantalla de configuración: no hay nada que configurar. Es para
    poder responder «¿por qué el programa no me deja publicar esto?» sin tener
    que abrir el código.
    """
    return [{'clave': r.clave, 'titulo': r.titulo, 'fundamento': r.fundamento,
             'configurable': False}
            for r in REGLAS]
