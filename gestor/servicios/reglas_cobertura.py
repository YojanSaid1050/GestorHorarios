# -*- coding: utf-8 -*-
"""Guardar y leer cuánta gente pide cada área, con fecha de vigencia.

Este archivo solo hace de puente: la **regla** vive en `dominio.cobertura` y
todas las cuentas se hacen allí. Aquí se guardan filas y se elige cuál está
vigente.

Esa separación es el arreglo. En la versión anterior este archivo tenía su
propia clase de regla, su propio conteo de personal y sus propios mínimos, y el
motor tenía otros: dos respuestas a la misma pregunta que había que mantener
sincronizadas a mano. Cuando se olvidaba una, la aplicación generaba horarios
que su propia validación daba por buenos.

La **vigencia** tampoco es un adorno: un cambio de política no puede alterar un
mes ya oficializado. Si en noviembre se decide que Comunicaciones pasa a 2 de
mañana, octubre sigue midiéndose con la regla con la que se hizo. Por eso cada
regla lleva la fecha desde la que manda, y se elige por fecha y no por «la
última que se guardó».
"""
from __future__ import annotations

import threading
from datetime import date
from typing import Optional

from gestor.datos.base import abierta, transaccion
from gestor.dominio.cobertura import AREAS, NOMBRES_AREA, ReglaCobertura
from gestor.registro import obtener

INICIO_OPERACION = '2026-08-01'

#: Las reglas tal como salen de fábrica. Están en una constante y no dentro de
#: la función que las siembra porque «restablecer de fábrica» necesita saber
#: cuántas tienen que quedar para comprobar que las repuso; dos listas separadas
#: se habrían descolgado la primera vez que se añadiera una.
DE_FABRICA: tuple[ReglaCobertura, ...] = (
    ReglaCobertura(
        area='gestion_social', vigente_desde=INICIO_OPERACION,
        am_minimo=1, pm_minimo=1, minimo_area=2,
        nota=('Gestión Social cubre las dos franjas: siempre tiene que haber al menos '
              '1 persona en la mañana y 1 en la tarde.'),
    ),
    ReglaCobertura(
        area='comunicaciones', vigente_desde=INICIO_OPERACION,
        minimo_area=1, am_maximo=2, pm_maximo=1,
        nota=('Comunicaciones necesita al menos 1 persona trabajando, en la franja que '
              'sea. Caben hasta 2 en la mañana y 1 en la tarde.'),
    ),
    ReglaCobertura(
        area='comunicaciones', vigente_desde='2026-08-31',
        minimo_area=1, am_objetivo=2, pm_objetivo=1, am_maximo=2, pm_maximo=1,
        nota=('Desde la semana del 31 de agosto de 2026, Comunicaciones trabaja 2 de '
              'mañana y 1 de tarde. El mínimo obligatorio sigue siendo 1 persona en el '
              'área: el reparto dice cómo se distribuye habitualmente, no obliga a '
              'cubrir un turno concreto.'),
    ),
    ReglaCobertura(
        area='atencion_ciudadano', vigente_desde=INICIO_OPERACION,
        minimo_area=1, am_maximo=3, pm_maximo=1,
        nota=('Atención al Ciudadano necesita al menos 1 persona trabajando, en la '
              'franja que sea: solo una persona rota entre los dos turnos. La jornada '
              'administrativa propia del área (ADM-AC) no cuenta como cobertura.'),
    ),
)

_candado = threading.Lock()
_cache: Optional[dict[str, list[ReglaCobertura]]] = None


def olvidar_lo_leido() -> None:
    """Vacía lo que se recuerda entre lecturas.

    Las reglas se leen una vez y se conservan mientras la aplicación está
    abierta. Al cambiarlas hay que llamar a esto, y las pruebas lo llaman entre
    unas y otras: sin ello, una prueba heredaba las reglas que dejó escritas la
    anterior.
    """
    global _cache
    with _candado:
        _cache = None


def _fila_a_regla(fila) -> ReglaCobertura:
    def entero(clave):
        valor = fila[clave]
        return None if valor is None else int(valor)

    return ReglaCobertura(
        area=str(fila['area']),
        vigente_desde=str(fila['vigente_desde']),
        am_minimo=int(fila['am_minimo'] or 0),
        pm_minimo=int(fila['pm_minimo'] or 0),
        minimo_area=int(fila['minimo_area'] or 0),
        am_objetivo=entero('am_objetivo'),
        pm_objetivo=entero('pm_objetivo'),
        am_maximo=entero('am_maximo'),
        pm_maximo=entero('pm_maximo'),
        nota=str(fila['nota'] or ''),
    )


def _todas() -> dict[str, list[ReglaCobertura]]:
    global _cache
    with _candado:
        if _cache is not None:
            return _cache
    por_area: dict[str, list[ReglaCobertura]] = {a: [] for a in AREAS}
    try:
        with abierta() as conexion:
            filas = conexion.execute(
                'SELECT * FROM reglas_cobertura ORDER BY area, vigente_desde').fetchall()
        for fila in filas:
            por_area.setdefault(str(fila['area']), []).append(_fila_a_regla(fila))
    except Exception:                                              # noqa: BLE001
        # Si la base no se puede leer se trabaja con las de fábrica y **se deja
        # constancia**. La versión anterior se lo tragaba en silencio, y la
        # aplicación seguía con las reglas de fábrica sin que nadie lo supiera.
        obtener().exception('no se pudieron leer las reglas de cobertura; '
                            'se usan las de fábrica')
        for regla_fabrica in DE_FABRICA:
            por_area.setdefault(regla_fabrica.area, []).append(regla_fabrica)
    for area, lista in por_area.items():
        if not lista:
            lista.extend(r for r in DE_FABRICA if r.area == area)
    with _candado:
        _cache = por_area
    return por_area


def regla(area: str, fecha=None) -> ReglaCobertura:
    """La regla que manda en esa área en esa fecha.

    Sin fecha se toma la última, que es la política de hoy. Con fecha se toma la
    que estaba vigente entonces, y eso es lo que permite que un mes publicado
    siga midiéndose con las reglas con las que se hizo.
    """
    candidatas = _todas().get(area) or []
    if not candidatas:
        return ReglaCobertura(area=area, vigente_desde=INICIO_OPERACION)
    if fecha is None:
        return candidatas[-1]
    dia = fecha.isoformat() if isinstance(fecha, date) else str(fecha)
    vigentes = [r for r in candidatas if r.vigente_desde <= dia]
    return vigentes[-1] if vigentes else candidatas[0]


def reglas_de(area: str) -> list[ReglaCobertura]:
    return list(_todas().get(area) or ())


def todas_las_reglas() -> dict[str, list[dict]]:
    return {a: [r.como_dict() for r in reglas_de(a)] for a in AREAS}


def con_identificador(area: str) -> list[dict]:
    """Las reglas del área con el número con el que se pueden borrar.

    El identificador no vive en la regla —la regla es una decisión, no una fila—
    pero la pantalla necesita algo con lo que señalar cuál quitar. Se añade
    aquí, en el puente, y no dentro del dominio.
    """
    with abierta() as conexion:
        filas = conexion.execute(
            'SELECT * FROM reglas_cobertura WHERE area=? ORDER BY vigente_desde',
            (area,)).fetchall()
    salida = []
    for fila in filas:
        regla_leida = _fila_a_regla(fila)
        salida.append({**regla_leida.como_dict(), 'id': int(fila['id']),
                       'texto_minimo': _texto_minimo(regla_leida),
                       'texto_rangos': _texto_rangos(regla_leida)})
    return salida


def _texto_minimo(r: ReglaCobertura) -> str:
    partes = []
    if r.am_minimo:
        partes.append(f'{r.am_minimo} de mañana')
    if r.pm_minimo:
        partes.append(f'{r.pm_minimo} de tarde')
    if partes:
        return 'mínimo ' + ' y '.join(partes)
    if r.minimo_area:
        return (f'mínimo {r.minimo_area} persona'
                f'{"s" if r.minimo_area != 1 else ""} en el área')
    return 'sin mínimo obligatorio'


def _texto_rangos(r: ReglaCobertura) -> str:
    topes = []
    if r.am_maximo is not None:
        topes.append(f'hasta {r.am_maximo} de mañana')
    if r.pm_maximo is not None:
        topes.append(f'hasta {r.pm_maximo} de tarde')
    return ' y '.join(topes)


def borrar_por_id(regla_id: int) -> dict:
    """Quita la regla que la pantalla ha señalado. Nunca deja un área sin ninguna."""
    with abierta() as conexion:
        fila = conexion.execute('SELECT * FROM reglas_cobertura WHERE id=?',
                                (int(regla_id),)).fetchone()
    if fila is None:
        raise ValueError('Esa regla de cobertura ya no existe.')
    area, desde = str(fila['area']), str(fila['vigente_desde'])
    borrar(area, desde)
    return {'area': area, 'vigente_desde': desde}


def descripcion_minimos_regla(area: str, fecha=None) -> str:
    """La regla en una frase, para explicarla en pantalla y en los avisos."""
    actual = regla(area, fecha)
    nombre = NOMBRES_AREA.get(area, area)
    partes = []
    if actual.am_minimo:
        partes.append(f'{actual.am_minimo} en la mañana')
    if actual.pm_minimo:
        partes.append(f'{actual.pm_minimo} en la tarde')
    if partes:
        return f'En {nombre} tiene que haber al menos ' + ' y '.join(partes) + '.'
    if actual.minimo_area:
        return (f'En {nombre} tiene que haber al menos {actual.minimo_area} '
                'persona(s) trabajando, en la franja que sea.')
    return f'{nombre} no tiene un mínimo configurado.'


# --------------------------------------------------------------- escribir

def sembrar_de_fabrica(conexion) -> None:
    """Deja escritas las reglas iniciales. No pisa lo que el usuario cambió."""
    for r in DE_FABRICA:
        conexion.execute(
            '''INSERT OR IGNORE INTO reglas_cobertura
               (area, vigente_desde, am_minimo, pm_minimo, minimo_area,
                am_objetivo, pm_objetivo, am_maximo, pm_maximo, nota)
               VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (r.area, r.vigente_desde, r.am_minimo, r.pm_minimo, r.minimo_area,
             r.am_objetivo, r.pm_objetivo, r.am_maximo, r.pm_maximo, r.nota))
    olvidar_lo_leido()


def restablecer_de_fabrica() -> int:
    """Vuelve a dejar exactamente las reglas de fábrica, ni una más.

    Sembrar no basta: la siembra respeta lo que ya hay, que es lo correcto al
    arrancar y lo contrario de lo que significa «volver a cero». En la versión
    anterior el reinicio de fábrica solo sembraba, así que una regla editada
    sobrevivía, y con ella sobrevivió durante versiones la exención de festivos
    que dejaba un área sin cobertura.
    """
    with transaccion() as conexion:
        conexion.execute('DELETE FROM reglas_cobertura')
        for r in DE_FABRICA:
            conexion.execute(
                '''INSERT INTO reglas_cobertura
                   (area, vigente_desde, am_minimo, pm_minimo, minimo_area,
                    am_objetivo, pm_objetivo, am_maximo, pm_maximo, nota)
                   VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (r.area, r.vigente_desde, r.am_minimo, r.pm_minimo, r.minimo_area,
                 r.am_objetivo, r.pm_objetivo, r.am_maximo, r.pm_maximo, r.nota))
    olvidar_lo_leido()
    return len(DE_FABRICA)


def guardar(regla_nueva: ReglaCobertura) -> None:
    with transaccion() as conexion:
        conexion.execute(
            '''INSERT INTO reglas_cobertura
               (area, vigente_desde, am_minimo, pm_minimo, minimo_area,
                am_objetivo, pm_objetivo, am_maximo, pm_maximo, nota)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(area, vigente_desde) DO UPDATE SET
                 am_minimo=excluded.am_minimo, pm_minimo=excluded.pm_minimo,
                 minimo_area=excluded.minimo_area,
                 am_objetivo=excluded.am_objetivo, pm_objetivo=excluded.pm_objetivo,
                 am_maximo=excluded.am_maximo, pm_maximo=excluded.pm_maximo,
                 nota=excluded.nota''',
            (regla_nueva.area, regla_nueva.vigente_desde,
             regla_nueva.am_minimo, regla_nueva.pm_minimo, regla_nueva.minimo_area,
             regla_nueva.am_objetivo, regla_nueva.pm_objetivo,
             regla_nueva.am_maximo, regla_nueva.pm_maximo, regla_nueva.nota))
    olvidar_lo_leido()


def borrar(area: str, vigente_desde: str) -> bool:
    """Quita una regla. Nunca deja un área sin ninguna."""
    if len(reglas_de(area)) <= 1:
        raise ValueError(
            f'{NOMBRES_AREA.get(area, area)} se quedaría sin ninguna regla de '
            'cobertura. Cambia la que hay en vez de quitarla.')
    with transaccion() as conexion:
        cursor = conexion.execute(
            'DELETE FROM reglas_cobertura WHERE area=? AND vigente_desde=?',
            (area, vigente_desde))
        borradas = cursor.rowcount
    olvidar_lo_leido()
    return bool(borradas)


# ------------------------------------------ preguntas sueltas que hace el motor

def minimo(area: str, turno: str, fecha=None) -> int:
    """Personas obligatorias en ese turno, según la regla vigente."""
    actual = regla(area, fecha)
    return actual.am_minimo if turno == 'AM' else actual.pm_minimo


def minimo_area(area: str, fecha=None) -> int:
    """Personas obligatorias en el área, en la franja que sea."""
    return regla(area, fecha).minimo_area


def maximo(area: str, turno: str, fecha=None, disponibles: Optional[int] = None) -> Optional[int]:
    """Techo de personas en ese turno, o `None` si el área no tiene techo.

    `disponibles` es la gente que hay que repartir ese día, y con ese dato el
    techo cede lo justo: una política escrita para tres personas no puede dejar
    sin turno a las siete que hay hoy. El techo es política de reparto, no una
    obligación operativa; el suelo es lo que no se salta nunca.
    """
    actual = regla(area, fecha)
    tope = actual.am_maximo if turno == 'AM' else actual.pm_maximo
    if tope is None:
        return None
    suelo = actual.am_minimo if turno == 'AM' else actual.pm_minimo
    tope = max(int(tope), int(suelo))
    if disponibles is not None:
        contrario = actual.pm_maximo if turno == 'AM' else actual.am_maximo
        if contrario is not None:
            tope = max(tope, int(disponibles) - int(contrario))
    return tope


def rango(area: str, turno: str, fecha=None) -> tuple[int, Optional[int]]:
    """Suelo y techo de ese turno, en una sola respuesta."""
    return minimo(area, turno, fecha), maximo(area, turno, fecha)
