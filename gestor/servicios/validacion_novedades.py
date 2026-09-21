"""Validación e invalidación de novedades, reutilizable sin HTTP."""
from __future__ import annotations

from typing import Optional

from gestor.datos import novedades, personal
from gestor.dominio import calendario
from gestor.servicios import cierres, periodos


def _ficha(empleado_id: int) -> dict:
    ficha = personal.obtener(empleado_id)
    if ficha is None:
        raise ValueError('Esa persona ya no está en la plantilla.')
    return ficha


def _nombre(empleado_id: int) -> str:
    return _ficha(empleado_id)['nombre']


def _buscar_solicitud(solicitud_id: int) -> dict:
    solicitud = next((s for s in novedades.listar_solicitudes()
                      if s['id'] == solicitud_id), None)
    if solicitud is None:
        raise ValueError('Esa solicitud ya no existe.')
    return solicitud


def _buscar_asignacion(asignacion_id: int) -> dict:
    asignacion = next((a for a in novedades.listar_asignaciones()
                       if a['id'] == asignacion_id), None)
    if asignacion is None:
        raise ValueError('Esa asignación ya no existe.')
    return asignacion


def _avisar_de_la_solicitud(solicitud: dict, motivo: str) -> str:
    """Marca los meses que esa novedad deja viejos, y devuelve el aviso.

    Una novedad sin fecha de fin —«los martes libra, hasta nuevo aviso»— no
    afecta a un rango de fechas sino a todo lo que venga después, así que se
    marca desde su inicio en adelante.
    """
    area = solicitud.get('area') or _ficha(solicitud['empleado_id'])['area']
    if solicitud.get('sin_fecha_fin'):
        return periodos.avisar_desde(solicitud['fecha_inicio'], motivo, area,
                                     origen='solicitudes')
    return periodos.avisar([solicitud['fecha_inicio'], solicitud.get('fecha_fin')],
                           motivo, area, origen='solicitudes')


def _avisar_de_la_asignacion(asignacion: dict, area: str, motivo: str) -> str:
    """Una asignación recurrente sin final toca todos los meses generados."""
    if asignacion.get('recurrente_indefinido'):
        return periodos.avisar_desde(
            asignacion.get('vigente_desde') or str(calendario.PRIMER_DIA), motivo,
            area, origen='asignaciones')
    return periodos.avisar(asignacion.get('fechas') or [], motivo, area,
                           origen='asignaciones')


def _conflictos(solicitud: dict, excluir: Optional[int] = None) -> list[dict]:
    """Con qué choca esa novedad, mire quien la mire.

    Está separado de la ruta a propósito. La comprobación vivía dentro de
    `prevalidar`, que recibe el identificador de algo **ya guardado**, así que
    los dos caminos por los que una novedad nace o se vuelve aprobada sin pasar
    por «aprobar» se la saltaban enteros: marcar la casilla «ya aprobada» al
    crearla, y corregir las fechas de una que ya lo estaba. Por ahí entraban
    exactamente los choques que el control existe para impedir.
    """
    nombre = solicitud.get('empleado_nombre') or _nombre(solicitud['empleado_id'])
    inicio = solicitud['fecha_inicio']
    fin = solicitud.get('fecha_fin') or inicio
    conflictos = [{
        'codigo': 'NOVEDAD_SOLAPADA',
        'fecha': c['fecha_del_choque'],
        'empleado_id': solicitud['empleado_id'],
        'mensaje': (f'{nombre} ya tiene aprobado {c["tipo"]} el '
                    f'{c["fecha_del_choque"]}. Cancela una de las dos antes de '
                    'aprobar esta.'),
    } for c in novedades.solapadas(
        solicitud['empleado_id'], inicio, fin, excluir=excluir,
        patron=solicitud)]

    # El descanso semanal es uno, así que moverlo dos veces en la misma semana
    # son dos órdenes contrarias. No se solapan por fecha —el 14 y el 15 son
    # días distintos— así que la comprobación de arriba no las ve nunca.
    if solicitud['tipo'] == 'descanso':
        for otra in novedades.descansos_movidos_de_la_semana(
                solicitud['empleado_id'], inicio, fin, excluir=excluir):
            conflictos.append({
                'codigo': 'DOS_DESCANSOS_LA_MISMA_SEMANA',
                'fecha': otra['fecha_inicio'],
                'empleado_id': solicitud['empleado_id'],
                'mensaje': (
                    f'{nombre} ya tiene aprobado mover su '
                    f'descanso al {otra["fecha_inicio"]}, que cae en la misma '
                    'semana. El descanso semanal es uno solo: cancela esa '
                    'primera solicitud si ahora prefiere este otro día.'),
            })
    return conflictos


def _exigir_que_no_choque(solicitud: dict, excluir: Optional[int] = None) -> None:
    """Se niega a dejar aprobada una novedad que contradice a otra.

    Aprobar dos cosas distintas para el mismo día no es algo que la aplicación
    pueda resolver sola: el motor acaba obedeciendo a una y el horario
    contradice a la otra, que sigue aprobada en su pantalla.
    """
    choques = _conflictos(solicitud, excluir=excluir)
    if choques:
        raise ValueError(choques[0]['mensaje'])


def _fechas_que_ocupa(datos: dict) -> list[str]:
    """Los días que esa asignación va a ocupar de verdad.

    Con fechas sueltas son esas. Si se repite cada semana, son los días que
    caen dentro de los meses que ya tienen horario: mirar solo la lista de
    fechas dejaba a las recurrentes sin un solo conflicto posible —no tienen
    fechas— y por ahí entraban enteras sin que nadie las comparara con nada.
    """
    sueltas = [str(f)[:10] for f in (datos.get('fechas') or [])]
    if not (datos.get('recurrente_indefinido') and datos.get('dias_semana')):
        return sueltas
    from datetime import timedelta

    from gestor.datos import horarios as datos_horarios
    dias = {int(d) for d in datos['dias_semana']}
    desde = str(datos.get('vigente_desde') or '')[:10]
    salida = set(sueltas)
    for anio, mes in datos_horarios.meses_con_horario():
        inicio, fin = calendario.rango(int(mes), int(anio))
        fecha = inicio
        while fecha <= fin:
            if fecha.weekday() in dias and fecha.isoformat() >= (desde or fecha.isoformat()):
                salida.add(fecha.isoformat())
            fecha += timedelta(days=1)
    return sorted(salida)


def _conflictos_de_asignacion(datos: dict) -> list[dict]:
    """Con qué choca esa asignación, mirando las cuatro cosas que la pisan.

    La vista previa comparaba **solo** contra novedades aprobadas, y solo en
    las fechas escritas a mano. No veía otra asignación de la misma persona el
    mismo día, ni las semanas cerradas, ni nada de lo que produce una
    recurrencia. Y, lo que era peor, guardar no la llamaba: lo que la pantalla
    acababa de marcar en rojo se guardaba igual pulsando el botón de al lado.
    """
    empleado_id = int(datos['empleado_id'])
    fechas = _fechas_que_ocupa(datos)
    conflictos = []

    for fecha in fechas:
        choques = novedades.solapadas(empleado_id, fecha, fecha)
        if choques:
            conflictos.append({
                'codigo': 'NOVEDAD_SOLAPADA', 'fecha': fecha,
                'empleado_id': empleado_id,
                'mensaje': (f'El {fecha} esa persona ya tiene aprobada otra novedad '
                            f'({choques[0]["tipo"]}).')})

    # Otra asignación de la misma persona el mismo día. Dos instrucciones para
    # el mismo turno son una y su contraria, y el motor acaba obedeciendo a la
    # que se aplique después.
    propias = {}
    for otra in novedades.listar_asignaciones():
        if (int(otra['empleado_id']) != empleado_id
                or str(otra.get('estado') or 'activo') != 'activo'
                or int(otra['id']) == int(datos.get('id') or 0)):
            continue
        for fecha in _fechas_que_ocupa(otra):
            propias.setdefault(fecha, otra)
    for fecha in fechas:
        otra = propias.get(fecha)
        if otra is not None:
            conflictos.append({
                'codigo': 'ASIGNACION_SOLAPADA', 'fecha': fecha,
                'empleado_id': empleado_id,
                'mensaje': (f'El {fecha} esa persona ya tiene otra asignación '
                            f'({otra["tipo"]}). Quita una de las dos.')})

    # Y las semanas cerradas, que es lo que significa cerrarlas.
    from datetime import date as _date
    for fecha in fechas:
        # Los periodos se solapan, así que una fecha puede pertenecer a dos: se
        # miran los dos, porque cerrarla en cualquiera de ellos la cierra.
        for anio, mes in calendario.periodos_de_la_fecha(_date.fromisoformat(fecha)):
            if fecha in cierres.fechas_cerradas(anio, mes):
                conflictos.append({
                    'codigo': 'SEMANA_CERRADA', 'fecha': fecha,
                    'empleado_id': empleado_id,
                    'mensaje': (f'El {fecha} está en una semana cerrada. Ábrela '
                                'primero si de verdad hay que tocarla.')})
                break
    return conflictos


def _avisar_del_grupo(afectadas: list[dict], motivo: str) -> str:
    """Marca **todas** las áreas del grupo, no solo la de la primera fila.

    Estaba escrito `afectadas[:1]`: se cancelaba el grupo entero —las tres
    áreas— y solo se marcaba como desactualizada la del primero de la lista.
    Las demás se quedaban con un horario que ya no se corresponde con lo que
    hay aprobado y sin nada que lo dijera. Las filas de un grupo comparten
    fechas, así que basta con una por área.
    """
    primeras: dict[str, dict] = {}
    for fila in afectadas:
        primeras.setdefault(str(fila.get('area') or ''), fila)
    return ''.join(_avisar_de_la_asignacion(fila, area, motivo)
                   for area, fila in sorted(primeras.items()) if area)
