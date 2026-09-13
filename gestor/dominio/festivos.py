# -*- coding: utf-8 -*-
"""Los festivos de Colombia, calculados. Sin base de datos delante.

En la versión anterior este cálculo abría la base para leer los cambios de
fecha hechos a mano, y con eso el dominio pasaba a depender de la persistencia:
no se podía probar un año de festivos sin montar una base, y cualquier error de
SQLite se tragaba con un `except Exception` que devolvía el calendario sin
ajustes, en silencio.

Aquí el cálculo es una función pura. Los ajustes que haya hecho la oficina se
pasan como argumento, y quien los lee de la base es la capa de datos. Eso hace
que este archivo se pueda probar entero con dos líneas y que un fallo al leer
los ajustes se note en vez de disimularse.
"""
from __future__ import annotations

from datetime import date, timedelta

ANIO_MINIMO = 1900
ANIO_MAXIMO = 2200


def validar_anio(anio) -> int:
    """Un año imposible se explica, no revienta con un error técnico."""
    try:
        valor = int(anio)
    except (TypeError, ValueError):
        raise ValueError('El año debe ser un número, por ejemplo 2026.') from None
    if not ANIO_MINIMO <= valor <= ANIO_MAXIMO:
        raise ValueError(
            f'El año debe estar entre {ANIO_MINIMO} y {ANIO_MAXIMO}. '
            f'El indicado fue {valor}.')
    return valor


def domingo_de_pascua(anio: int) -> date:
    """Algoritmo de Gauss/Meeus. Del que cuelgan seis festivos del año."""
    a = anio % 19
    b, c = anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    ele = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ele) // 451
    mes = (h + ele - 7 * m + 114) // 31
    dia = ((h + ele - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def trasladar_al_lunes(fecha: date) -> date:
    """La ley Emiliani: varios festivos se corren al lunes siguiente."""
    return fecha + timedelta(days=(7 - fecha.weekday()) % 7)


def del_anio(anio: int) -> dict[date, str]:
    """El calendario oficial colombiano de ese año, sin ajustes de la oficina."""
    anio = validar_anio(anio)
    pascua = domingo_de_pascua(anio)
    fijos = {
        date(anio, 1, 1): 'Año Nuevo',
        date(anio, 5, 1): 'Día del Trabajo',
        date(anio, 7, 20): 'Independencia de Colombia',
        date(anio, 8, 7): 'Batalla de Boyacá',
        date(anio, 12, 8): 'Inmaculada Concepción',
        date(anio, 12, 25): 'Navidad',
        pascua - timedelta(days=3): 'Jueves Santo',
        pascua - timedelta(days=2): 'Viernes Santo',
    }
    movibles = (
        (date(anio, 1, 6), 'Día de los Reyes Magos'),
        (date(anio, 3, 19), 'Día de San José'),
        (date(anio, 6, 29), 'San Pedro y San Pablo'),
        (date(anio, 8, 15), 'Asunción de la Virgen'),
        (date(anio, 10, 12), 'Día de la Raza'),
        (date(anio, 11, 1), 'Todos los Santos'),
        (date(anio, 11, 11), 'Independencia de Cartagena'),
        (pascua + timedelta(days=39), 'Ascensión del Señor'),
        (pascua + timedelta(days=60), 'Corpus Christi'),
        (pascua + timedelta(days=68), 'Sagrado Corazón de Jesús'),
    )
    for fecha, nombre in movibles:
        fijos[trasladar_al_lunes(fecha)] = nombre
    return dict(sorted(fijos.items()))


def con_ajustes(anio: int, ajustes: list[dict] | None = None) -> dict[date, str]:
    """El calendario efectivo: el oficial más los cambios de fecha de la oficina.

    Cada ajuste es ``{'fecha_original', 'fecha_nueva', 'nombre'}``. Los pasa
    quien los tenga guardados; aquí no se va a buscarlos.
    """
    calendario = del_anio(anio)
    for ajuste in (ajustes or ()):
        original = date.fromisoformat(str(ajuste['fecha_original']))
        nueva = date.fromisoformat(str(ajuste['fecha_nueva']))
        nombre = ajuste.get('nombre') or calendario.get(original) or 'Festivo ajustado'
        calendario.pop(original, None)
        calendario[nueva] = nombre
    return dict(sorted(calendario.items()))
