# -*- coding: utf-8 -*-
"""Qué meses han quedado desactualizados, y por qué.

Un mes generado es una foto de cómo estaban las cosas en el momento de armarlo.
Si después se aprueba una novedad, se retira a alguien o se cambia una regla,
ese horario deja de corresponderse con la realidad **y sigue igual de guardado**:
la aplicación no lo reescribe sola.

Y no lo hace a propósito. Regenerar por su cuenta un mes que la oficina ya
imprimió y repartió sería el peor comportamiento posible: la gente tendría un
papel en la pared distinto de lo que dice la pantalla, sin haber hecho nada.

Lo que sí se hace es dejar constancia, con el motivo escrito, para que la
pantalla pueda decir «octubre y noviembre se armaron antes de esto; conviene
volver a generarlos» y que sea una persona quien decida cuándo.

Se marca el **período** y también **el área**: una novedad de Comunicaciones no
obliga a recalcular Gestión Social, y poder recalcular solo el área afectada es
lo que evita que un cambio pequeño mueva el horario de todo el mundo.

Solo se marcan meses **que ya se generaron alguna vez**. Avisar de que noviembre
quedó desactualizado cuando noviembre todavía no existe es ruido: no hay ninguna
foto que se haya quedado vieja, y el aviso solo enseña a no leer los avisos.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Iterable, Optional

from gestor.datos.base import abierta, transaccion
from gestor.dominio import calendario
from gestor.dominio.cobertura import AREAS
from gestor.registro import obtener


def _fecha(texto) -> Optional[date]:
    try:
        return date.fromisoformat(str(texto)[:10])
    except (TypeError, ValueError):
        return None


def _generados(conexion) -> set[tuple[int, int]]:
    """Los meses que se pueden volver a armar, y que ya se armaron alguna vez.

    Los meses base quedan fuera aunque tengan horario guardado. Llegan
    transcritos del Excel que la oficina ya trabajó, la aplicación se niega a
    reiniciarlos y no hay forma de generarlos: decir «conviene volver a generar
    agosto» sería un consejo que no se puede seguir, y un aviso que no se puede
    atender enseña a no leer los avisos.
    """
    return {(int(f['anio']), int(f['mes'])) for f in conexion.execute(
        'SELECT DISTINCT anio, mes FROM horarios')
        if not calendario.es_mes_base(int(f['mes']), int(f['anio']))}


def _periodos_de(fechas: Iterable[str]) -> set[tuple[int, int]]:
    """A qué meses afecta un conjunto de fechas. Pueden ser dos por fecha."""
    afectados: set[tuple[int, int]] = set()
    for texto in fechas:
        cuando = _fecha(texto)
        if cuando is not None:
            afectados.update(calendario.periodos_de_la_fecha(cuando))
    return afectados


def _marcar(afectados: set[tuple[int, int]], motivo: str,
            area: Optional[str], origen: str = 'cambios') -> list[str]:
    if not afectados:
        return []
    if area is not None and area not in AREAS:
        # Mejor un mensaje que diga qué área se esperaba que un error de la base
        # hablando de una restricción CHECK.
        raise ValueError(
            f'«{area}» no es un área. Tiene que ser una de: {", ".join(AREAS)}.')
    with transaccion() as conexion:
        marcables = sorted(afectados & _generados(conexion))
        for anio, mes in marcables:
            _apuntar(conexion, 'periodos', (anio, mes), motivo, origen)
            if area:
                _apuntar(conexion, 'periodos_area', (anio, mes, area), motivo, origen)
    return [calendario.nombre_del_periodo(mes, anio) for anio, mes in marcables]


def marcar(fechas: Iterable[str], motivo: str, area: Optional[str] = None,
           origen: str = 'cambios') -> list[str]:
    """Deja marcados los meses generados que tocan esas fechas, con el motivo.

    Devuelve los meses marcados, en castellano, para poder decirlo en el mismo
    mensaje que confirma la acción: «aprobada; conviene volver a generar
    octubre de 2026».
    """
    return _marcar(_periodos_de(fechas), motivo, area, origen)


def marcar_desde(desde: str, motivo: str, area: Optional[str] = None,
                 origen: str = 'cambios') -> list[str]:
    """Para los cambios que no terminan: una regla nueva, un retiro, un fijo.

    Cambiar el mínimo de cobertura desde el 1 de noviembre no afecta a una lista
    de fechas: afecta a noviembre y a todo lo que venga después. Se marcan todos
    los meses generados cuyo período no haya terminado antes de esa fecha.
    """
    inicio = _fecha(desde)
    if inicio is None:
        return []
    with abierta() as conexion:
        candidatos = _generados(conexion)
    return _marcar({(anio, mes) for anio, mes in candidatos
                    if calendario.rango(mes, anio)[1] >= inicio}, motivo, area, origen)


def _apuntar(conexion, tabla: str, clave: tuple, motivo: str,
             origen: str = 'cambios') -> None:
    columnas = 'anio, mes' + (', area' if tabla == 'periodos_area' else '')
    marcas = ', '.join('?' for _ in clave)
    donde = 'anio=? AND mes=?' + (' AND area=?' if tabla == 'periodos_area' else '')

    fila = conexion.execute(
        f'SELECT razones_json FROM {tabla} WHERE {donde}', clave).fetchone()
    razones = _razones(fila['razones_json'] if fila else None)
    if motivo not in [r['mensaje'] for r in razones]:
        # Se acumulan sin repetir: si se aprueban tres vacaciones seguidas, el
        # aviso dice «hay novedades nuevas» una vez, no tres.
        razones.append({'mensaje': motivo, 'origen': origen})
    conexion.execute(
        f'INSERT INTO {tabla}({columnas}, sucio, razones_json) VALUES({marcas}, 1, ?) '
        f'ON CONFLICT({columnas}) DO UPDATE SET sucio=1, razones_json=excluded.razones_json, '
        "actualizado_en=datetime('now')",
        (*clave, json.dumps(razones, ensure_ascii=False)))


def _razones(crudo) -> list[dict]:
    """Los motivos guardados, siempre como fichas con mensaje y origen.

    Se leen así porque la pantalla no dice lo mismo según de dónde venga el
    cambio: «hay novedades por aplicar» y «este mes depende de otro que cambió»
    son dos avisos distintos y con dos acciones distintas. Se admite el formato
    antiguo —una lista de textos sueltos— para no perder lo ya escrito.
    """
    try:
        crudas = json.loads(crudo or '[]')
    except (TypeError, ValueError):
        return []
    return [r if isinstance(r, dict) else {'mensaje': str(r), 'origen': 'cambios'}
            for r in crudas]


def limpiar(mes: int, anio: int, area: Optional[str] = None) -> None:
    """Se llama al generar: ese mes vuelve a estar al día.

    Con área, se limpia solo esa: el período sigue marcado mientras quede
    cualquier otra área pendiente, porque el mes no está al día hasta que lo
    están todas.
    """
    with transaccion() as conexion:
        if area:
            conexion.execute(
                'DELETE FROM periodos_area WHERE anio=? AND mes=? AND area=?',
                (int(anio), int(mes), area))
            queda = conexion.execute(
                'SELECT 1 FROM periodos_area WHERE anio=? AND mes=? AND sucio=1 LIMIT 1',
                (int(anio), int(mes))).fetchone()
            if queda:
                return
        conexion.execute('DELETE FROM periodos_area WHERE anio=? AND mes=?',
                         (int(anio), int(mes)))
        conexion.execute('DELETE FROM periodos WHERE anio=? AND mes=?',
                         (int(anio), int(mes)))


def estado(mes: int, anio: int) -> dict:
    """Si ese mes está al día, y si no, por qué no."""
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT sucio, razones_json FROM periodos WHERE anio=? AND mes=?',
            (int(anio), int(mes))).fetchone()
        por_area = conexion.execute(
            'SELECT area, razones_json FROM periodos_area '
            'WHERE anio=? AND mes=? AND sucio=1', (int(anio), int(mes))).fetchall()
    return {
        'desactualizado': bool(fila and fila['sucio']),
        'razones': _razones(fila['razones_json'] if fila else None),
        'areas': {str(f['area']): _razones(f['razones_json']) for f in por_area},
    }


def desactualizados() -> list[dict]:
    """Todos los meses que han quedado atrás, para avisar de una vez."""
    with abierta() as conexion:
        filas = conexion.execute(
            'SELECT anio, mes, razones_json FROM periodos WHERE sucio=1 '
            'ORDER BY anio, mes').fetchall()
    return [{
        'anio': int(f['anio']), 'mes': int(f['mes']),
        'nombre': calendario.nombre_del_periodo(int(f['mes']), int(f['anio'])),
        'razones': _razones(f['razones_json']),
    } for f in filas]


def frase(meses: list[str]) -> str:
    """El aviso, ya redactado, para pegarlo detrás de «hecho».

    Vive aquí y no en cada ruta porque si no, cada pantalla acabaría diciéndolo
    con palabras distintas y la mitad no lo diría.
    """
    if not meses:
        return ''
    lista = meses[0] if len(meses) == 1 else ', '.join(meses[:-1]) + ' y ' + meses[-1]
    return (f' Conviene volver a generar {lista}: se armó antes de este cambio.'
            if len(meses) == 1 else
            f' Conviene volver a generar {lista}: se armaron antes de este cambio.')


def avisar(fechas: Iterable[str], motivo: str, area: Optional[str] = None,
           origen: str = 'cambios') -> str:
    """Marcar y devolver ya la frase. Es lo que llaman las rutas."""
    try:
        return frase(marcar(fechas, motivo, area, origen))
    except Exception:                                              # noqa: BLE001
        # Marcar es un aviso, no la acción. Si falla, la aprobación que acaba de
        # hacerse sigue siendo válida: se registra el fallo y se calla el aviso,
        # nunca al revés.
        obtener().exception('no se pudo marcar el período como desactualizado')
        return ''


def avisar_desde(desde: str, motivo: str, area: Optional[str] = None,
                 origen: str = 'cambios') -> str:
    try:
        return frase(marcar_desde(desde, motivo, area, origen))
    except Exception:                                              # noqa: BLE001
        obtener().exception('no se pudo marcar el período como desactualizado')
        return ''
