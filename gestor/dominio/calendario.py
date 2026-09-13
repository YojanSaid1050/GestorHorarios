# -*- coding: utf-8 -*-
"""El calendario de la operación: semanas completas, no meses naturales.

Esta es la idea de la que cuelga casi todo lo demás, y la que más cuesta ver
desde fuera: **un mes no se programa del día 1 al 30**. Se programa por semanas
enteras, de lunes a domingo. Octubre de 2026 va del lunes 28 de septiembre al
domingo 1 de noviembre.

Se hace así porque el descanso semanal tiene que caer dentro de una semana de
verdad. Programando por mes natural, la última semana quedaba partida en tres o
cuatro días sueltos y había que meter un descanso ahí dentro aunque no tocara,
o dejar a alguien nueve días seguidos a caballo entre dos meses sin que ninguno
de los dos lo viera.

La consecuencia que hay que tener siempre presente: **los períodos se solapan**.
El 1 de octubre de 2026 pertenece a la vez al período de septiembre —que llega
hasta el domingo 4— y al de octubre. Preguntarle a una fecha por su mes natural
es un atajo que ya ha costado caro: al aprobar unas vacaciones del 1 de octubre
solo se avisaba a octubre, y septiembre se quedaba dando por bueno un horario
que ya no coincidía con lo aprobado. Para eso está `periodos_de_la_fecha`.
"""
from __future__ import annotations

import calendar as _calendario_py
from datetime import date, timedelta

from gestor.dominio import festivos as festivos_mod

NOMBRES_DIAS = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')
NOMBRES_MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
                 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')

#: Día en que arranca la operación. Nada anterior se programa ni se muestra.
PRIMER_DIA = date(2026, 8, 1)

#: Los meses que **no se generan**: llegan transcritos del Excel que la oficina
#: ya trabajó. No se pueden reiniciar, no se pueden volver a armar y no se les
#: puede aconsejar que se rehagan. Están aquí, en un solo sitio, porque tres
#: piezas distintas necesitan saberlo —el reinicio, la revisión de publicación y
#: el aviso de meses desactualizados— y tres copias de un mismo hecho es
#: exactamente como se descolgó la versión anterior.
MESES_BASE = ((2026, 8), (2026, 9))


def es_mes_base(mes: int, anio: int) -> bool:
    return (int(anio), int(mes)) in MESES_BASE


def lunes_de(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def domingo_de(fecha: date) -> date:
    return fecha + timedelta(days=6 - fecha.weekday())


def nombre_del_periodo(mes: int, anio: int) -> str:
    return f'{NOMBRES_MESES[int(mes) - 1]} de {int(anio)}'


def rango(mes: int, anio: int) -> tuple[date, date]:
    """Primer y último día del período de programación de un mes.

    El primer mes de operación es la excepción: agosto de 2026 es la base
    histórica, se corresponde con el horario real ya publicado y abarca
    exactamente sus días naturales. El mes siguiente hereda de él el lunes con
    el que arranca.
    """
    primero = date(anio, mes, 1)
    ultimo = date(anio, mes, _calendario_py.monthrange(anio, mes)[1])
    if (anio, mes) == (PRIMER_DIA.year, PRIMER_DIA.month):
        return primero, ultimo
    return max(lunes_de(primero), PRIMER_DIA), domingo_de(ultimo)


def periodos_de_la_fecha(fecha: date) -> list[tuple[int, int]]:
    """Qué meses tienen ese día dentro de su programación. Pueden ser dos."""
    encontrados = []
    for salto in (-1, 0, 1):
        mes, anio = fecha.month + salto, fecha.year
        if mes < 1:
            anio, mes = anio - 1, 12
        elif mes > 12:
            anio, mes = anio + 1, 1
        inicio, fin = rango(mes, anio)
        if inicio <= fecha <= fin:
            encontrados.append((anio, mes))
    return encontrados


def es_ultimo_viernes(fecha: date) -> bool:
    """¿Es el último viernes de **su propio** mes?

    Ese día las áreas hacen jornada administrativa completa. Se decide sobre el
    mes al que pertenece el día, no sobre el mes que se está programando: en la
    primera y la última semana del período conviven días de dos meses.
    """
    if fecha.weekday() != 4:
        return False
    return (fecha + timedelta(days=7)).month != fecha.month


def semanas(mes: int, anio: int) -> list[tuple[date, date]]:
    """Las semanas completas del período, de lunes a domingo."""
    inicio, fin = rango(mes, anio)
    salida = []
    lunes = lunes_de(inicio)
    while lunes <= fin:
        salida.append((max(lunes, inicio), min(domingo_de(lunes), fin)))
        lunes += timedelta(days=7)
    return salida


def _dia(fecha: date, mapa_festivos: dict, mes: int, anio: int) -> dict:
    propio = fecha.month == mes and fecha.year == anio
    if propio:
        pertenece = 'propio'
    elif (fecha.year, fecha.month) < (anio, mes):
        pertenece = 'anterior'
    else:
        pertenece = 'siguiente'
    return {
        'fecha': fecha.isoformat(),
        'dia': fecha.day,
        'mes': fecha.month,
        'anio': fecha.year,
        'dia_semana_numero': fecha.weekday(),
        'dia_semana': NOMBRES_DIAS[fecha.weekday()],
        'lunes_semana': lunes_de(fecha).isoformat(),
        'es_sabado': fecha.weekday() == 5,
        'es_domingo': fecha.weekday() == 6,
        'es_ultimo_viernes_administrativo': es_ultimo_viernes(fecha),
        'es_festivo': fecha in mapa_festivos,
        'nombre_festivo': mapa_festivos.get(fecha),
        'mes_propio': propio,
        'pertenece': pertenece,
    }


def dias_del_periodo(mes: int, anio: int, ajustes_festivos=None) -> list[dict]:
    """Todos los días del período, con lo que hay que saber de cada uno."""
    inicio, fin = rango(mes, anio)
    mapa = festivos_mod.con_ajustes(inicio.year, ajustes_festivos)
    if fin.year != inicio.year:
        mapa.update(festivos_mod.con_ajustes(fin.year, ajustes_festivos))
    salida, fecha = [], inicio
    while fecha <= fin:
        salida.append(_dia(fecha, mapa, mes, anio))
        fecha += timedelta(days=1)
    return salida


def dias_del_mes(mes: int, anio: int, ajustes_festivos=None) -> list[dict]:
    """Solo los días naturales del mes. Para las vistas de calendario."""
    mapa = festivos_mod.con_ajustes(anio, ajustes_festivos)
    total = _calendario_py.monthrange(anio, mes)[1]
    return [_dia(date(anio, mes, n), mapa, mes, anio) for n in range(1, total + 1)]
