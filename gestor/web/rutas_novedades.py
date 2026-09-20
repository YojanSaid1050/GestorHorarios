# -*- coding: utf-8 -*-
"""Solicitudes y asignaciones desde la pantalla.

La comprobación que da sentido a estas rutas es la de **novedades que se pisan**:
aprobar dos cosas distintas para el mismo día de la misma persona es una
contradicción que la aplicación no puede resolver sola. Se detecta antes de
aprobar y se explica, en vez de aplicar la última que llegó y dejar al usuario
preguntándose por qué el horario no dice lo que él aprobó.

Hay tres formas de quitar una novedad y no son la misma:

* **rechazar** — «no te lo concedo». Nunca llegó a existir.
* **cancelar** — se concedió y luego no hizo falta. Existió y se lee en el
  historial.
* **eliminar** — se escribió por error. Desaparece del todo.

Mezclarlas fue un error real: cancelar borraba, y entonces el historial no podía
explicar por qué aquel día alguien había librado.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from gestor.datos import novedades, personal
from gestor.dominio import calendario
from gestor.servicios import cierres, exclusion, historial, periodos

router = APIRouter(prefix='/api', tags=['novedades'])


class SolicitudNueva(BaseModel):
    empleado_id: int
    tipo: str
    fecha_inicio: str
    fecha_fin: Optional[str] = None
    sin_fecha_fin: bool = False
    modo_periodo: str = 'rango'
    dia_semana_recurrente: Optional[int] = None
    modo_cobertura: str = 'sin_cubrir'
    reemplazo_empleado_id: Optional[int] = None
    intercambio_empleado_id: Optional[int] = None
    turno_solicitado: Optional[str] = None
    dia_descanso_solicitado: Optional[int] = None
    #: Las horas de una capacitación. La pantalla las manda desde siempre; sin
    #: declararlas aquí, Pydantic las tiraba sin decir nada.
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    observacion: str = ''
    #: La casilla «Aprobada por el jefe» del formulario.
    #:
    #: Hay que declararla o Pydantic la tira sin decir nada, que es lo que
    #: pasaba: se marcaba la casilla, salía el aviso verde de guardado, y la
    #: solicitud aparecía en la tabla como **pendiente**. Había que aprobarla
    #: otra vez a mano, y quien no se fijaba se quedaba con una novedad sin
    #: aprobar que el horario no tenía en cuenta.
    aprobada: bool = False


class AsignacionNueva(BaseModel):
    empleado_id: int
    tipo: str
    fechas: list[str] = []
    recurrente_indefinido: bool = False
    dias_semana: list[int] = []
    horario_administrativo: Optional[str] = None
    turno_excepcion: Optional[str] = None
    cubrir_pm: bool = False
    reemplazo_empleado_id: Optional[int] = None
    descripcion: str = ''
    vigente_desde: Optional[str] = None
    estado: str = 'activo'


class AsignacionMasiva(BaseModel):
    empleado_ids: list[int]
    requerimiento: AsignacionNueva
    alcance: str = 'todos'
    area: Optional[str] = None
    aplicar_solo_compatibles: bool = False
    permitir_conflictos_grupo: bool = False


AREAS_BONITAS = {'gestion_social': 'Gestión Social',
                 'atencion_ciudadano': 'Atención al Ciudadano',
                 'comunicaciones': 'Comunicaciones'}


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


# ------------------------------------------------------------- solicitudes

@router.get('/solicitudes')
def listar_solicitudes(mes: Optional[int] = None, anio: Optional[int] = None):
    """Devuelve una lista, no un objeto: es lo que la pantalla pinta directamente."""
    return novedades.listar_solicitudes(mes, anio)


@router.delete('/solicitudes/finalizadas')
def borrar_finalizadas():
    """Limpieza voluntaria: solo lo aprobado que ya se cumplió.

    Va antes que `/solicitudes/{id}` a propósito. Declarada después, FastAPI
    leería «finalizadas» como un identificador y esta ruta no se alcanzaría
    nunca.
    """
    ids = novedades.solicitudes_cumplidas()
    for identificador in ids:
        novedades.borrar_solicitud(identificador)
    historial.anotar('limpiar_solicitudes', 'solicitud', {'eliminadas': len(ids)})
    return {'ok': True, 'eliminadas': len(ids),
            'mensaje': f'Se eliminaron {len(ids)} solicitud(es) ya cumplida(s).'}


@router.post('/solicitudes')
def crear_solicitud(solicitud: SolicitudNueva):
    datos = solicitud.model_dump()
    nombre = _nombre(datos['empleado_id'])
    ya_aprobada = bool(datos.pop('aprobada', False))
    datos['estado'] = 'aprobada' if ya_aprobada else 'pendiente'
    with exclusion.decidiendo():
        if ya_aprobada:
            # Nace aprobada: manda sobre el horario desde este momento, igual
            # que si alguien le hubiera dado a «aprobar». Se comprueba antes de
            # escribir, y las dos cosas juntas: entre mirar y escribir cabía
            # otra petición haciendo exactamente lo mismo.
            _exigir_que_no_choque({**datos, 'empleado_nombre': nombre})
        identificador = novedades.crear_solicitud(datos)
    historial.anotar('crear_solicitud', 'solicitud',
                     {'id': identificador, 'nombre': nombre, 'tipo': datos['tipo'],
                      'estado': datos['estado']})
    if not ya_aprobada:
        return {'ok': True, 'id': identificador,
                'mensaje': f'Solicitud de {nombre} registrada, pendiente de aprobar.'}
    # Una novedad que nace aprobada cambia el horario igual que una que se
    # aprueba después, así que el período queda marcado igual.
    aviso = _avisar_de_la_solicitud(
        {**datos, 'id': identificador}, 'se registró una novedad ya aprobada')
    return {'ok': True, 'id': identificador,
            'mensaje': f'Solicitud de {nombre} registrada y aprobada.' + aviso}


@router.put('/solicitudes/{solicitud_id}')
def editar_solicitud(solicitud_id: int, solicitud: SolicitudNueva):
    antes = _buscar_solicitud(solicitud_id)
    nuevos = solicitud.model_dump()
    with exclusion.decidiendo():
        if antes['estado'] == 'aprobada':
            # Corregir las fechas o la persona de algo aprobado es aprobarlo
            # otra vez, en otro sitio. `actualizar_solicitud` no toca la
            # columna `estado`, así que una aprobada se movía encima de otra
            # aprobada sin que nadie volviera a mirar.
            _exigir_que_no_choque({**antes, **nuevos}, excluir=solicitud_id)
        novedades.actualizar_solicitud(solicitud_id, nuevos)
    historial.anotar('editar_solicitud', 'solicitud', {'id': solicitud_id})
    aviso = ''
    if antes['estado'] == 'aprobada':
        # Cambiar las fechas de algo aprobado mueve el horario dos veces: donde
        # estaba y donde pasa a estar.
        aviso = _avisar_de_la_solicitud(antes, 'se corrigió una novedad aprobada')
        aviso += _avisar_de_la_solicitud(
            {**antes, **nuevos}, 'se corrigió una novedad aprobada')
    return {'ok': True, 'mensaje': 'Solicitud corregida.' + aviso}


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


@router.get('/solicitudes/{solicitud_id}/prevalidar')
def prevalidar(solicitud_id: int):
    """¿Chocaría con algo ya aprobado? Se pregunta antes de aprobar."""
    conflictos = _conflictos(_buscar_solicitud(solicitud_id), excluir=solicitud_id)
    return {'ok': True, 'compatible': not conflictos, 'conflictos': conflictos,
            'avisos': [c['mensaje'] for c in conflictos]}


@router.patch('/solicitudes/{solicitud_id}/aprobar')
def aprobar(solicitud_id: int):
    with exclusion.decidiendo():
        solicitud = _buscar_solicitud(solicitud_id)
        _exigir_que_no_choque(solicitud, excluir=solicitud_id)
        novedades.resolver_solicitud(solicitud_id, 'aprobada')
    historial.anotar('aprobar_solicitud', 'solicitud', {'id': solicitud_id})
    aviso = _avisar_de_la_solicitud(solicitud, 'se aprobó una novedad')
    return {'ok': True, 'mensaje': (
        'Aprobada. Vuelve a generar el mes para que aparezca en el horario.' + aviso)}


@router.patch('/solicitudes/{solicitud_id}/rechazar')
def rechazar(solicitud_id: int):
    """Rechazar algo que ya estaba aprobado también desactualiza el mes.

    Es el caso que se olvida: quitar una novedad cambia el horario tanto como
    ponerla, y sin este aviso el mes seguía enseñando unas vacaciones anuladas.
    """
    solicitud = _buscar_solicitud(solicitud_id)
    novedades.resolver_solicitud(solicitud_id, 'rechazada')
    historial.anotar('rechazar_solicitud', 'solicitud', {'id': solicitud_id})
    aviso = (_avisar_de_la_solicitud(solicitud, 'se anuló una novedad aprobada')
             if solicitud['estado'] == 'aprobada' else '')
    return {'ok': True, 'mensaje': (
        'Solicitud rechazada. Se conserva en el historial.' + aviso)}


@router.patch('/solicitudes/{solicitud_id}/cancelar')
def cancelar_solicitud(solicitud_id: int):
    """Cancelar no borra: la novedad existió y el historial tiene que decirlo."""
    solicitud = _buscar_solicitud(solicitud_id)
    novedades.resolver_solicitud(solicitud_id, 'cancelada')
    historial.anotar('cancelar_solicitud', 'solicitud', {'id': solicitud_id})
    aviso = (_avisar_de_la_solicitud(solicitud, 'se anuló una novedad aprobada')
             if solicitud['estado'] == 'aprobada' else '')
    return {'ok': True, 'mensaje': (
        'Solicitud cancelada. Se conserva en el historial.' + aviso)}


@router.patch('/solicitudes/{solicitud_id}/pendiente')
def volver_a_pendiente(solicitud_id: int):
    solicitud = _buscar_solicitud(solicitud_id)
    novedades.resolver_solicitud(solicitud_id, 'pendiente')
    historial.anotar('solicitud_pendiente', 'solicitud', {'id': solicitud_id})
    aviso = (_avisar_de_la_solicitud(solicitud, 'se retiró la aprobación de una novedad')
             if solicitud['estado'] == 'aprobada' else '')
    return {'ok': True, 'mensaje': 'Solicitud devuelta a pendiente.' + aviso}


@router.delete('/solicitudes/{solicitud_id}')
def borrar_solicitud(solicitud_id: int):
    """Borrado de verdad: para lo que se escribió por error.

    A diferencia de cancelar, esto no deja rastro. Por eso el aviso de que hay
    que regenerar se da igual: el horario ya guardado sigue contando con ella.
    """
    solicitud = _buscar_solicitud(solicitud_id)
    novedades.borrar_solicitud(solicitud_id)
    historial.anotar('borrar_solicitud', 'solicitud', {'id': solicitud_id})
    aviso = (_avisar_de_la_solicitud(solicitud, 'se eliminó una novedad aprobada')
             if solicitud['estado'] == 'aprobada' else '')
    return {'ok': True, 'requiere_recalculo': bool(aviso),
            'mensaje': 'Solicitud eliminada definitivamente.' + aviso}


# ------------------------------------------------------------ asignaciones

@router.get('/requerimientos')
def listar_asignaciones(mes: Optional[int] = None, anio: Optional[int] = None):
    return novedades.listar_asignaciones(mes, anio)


@router.delete('/requerimientos/finalizados')
def borrar_asignaciones_cumplidas():
    ids = novedades.asignaciones_cumplidas()
    for identificador in ids:
        novedades.borrar_asignacion(identificador)
    historial.anotar('limpiar_asignaciones', 'asignacion', {'eliminadas': len(ids)})
    return {'ok': True, 'eliminadas': len(ids),
            'mensaje': f'Se eliminaron {len(ids)} asignación(es) ya cumplida(s).'}


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


@router.post('/requerimientos/prevalidar')
def prevalidar_asignacion(asignacion: AsignacionNueva):
    datos = asignacion.model_dump()
    conflictos = _conflictos_de_asignacion(datos)
    return {'ok': True, 'tiene_conflictos': bool(conflictos), 'conflictos': conflictos,
            'compatible': not conflictos, 'avisos': [c['mensaje'] for c in conflictos],
            'fechas_libres': [f for f in (datos.get('fechas') or [])
                              if f not in {c['fecha'] for c in conflictos}]}


@router.post('/requerimientos/masivo/prevalidar')
def prevalidar_masivo(peticion: AsignacionMasiva):
    resultados = []
    for empleado_id in peticion.empleado_ids:
        datos = {**peticion.requerimiento.model_dump(), 'empleado_id': int(empleado_id)}
        revision = prevalidar_asignacion(AsignacionNueva(**datos))
        resultados.append({
            'empleado_id': int(empleado_id),
            'empleado_nombre': _nombre(int(empleado_id)),
            'compatible': revision['compatible'],
            'conflictos': revision['conflictos'],
        })
    return {'ok': True, 'resultados': resultados,
            'compatibles': sum(1 for r in resultados if r['compatible']),
            'conflictos_grupo': []}


@router.post('/requerimientos')
def crear_asignacion(asignacion: AsignacionNueva):
    datos = asignacion.model_dump()
    if not datos['fechas'] and not datos['recurrente_indefinido']:
        raise ValueError('Elige al menos una fecha, o marca que se repite cada semana.')
    ficha = _ficha(datos['empleado_id'])
    # Lo que la vista previa marca en rojo no se puede guardar pulsando el botón
    # de al lado. Guardar no llamaba a la comprobación, así que la vista previa
    # era un consejo y no un control.
    with exclusion.decidiendo():
        choques = _conflictos_de_asignacion(datos)
        if choques:
            raise ValueError(choques[0]['mensaje'])
        identificador = novedades.crear_asignacion(datos)
    historial.anotar('crear_asignacion', 'asignacion',
                     {'id': identificador, 'nombre': ficha['nombre'], 'tipo': datos['tipo']})
    aviso = _avisar_de_la_asignacion(datos, ficha['area'], 'se añadió una asignación')
    return {'ok': True, 'id': identificador, 'mensaje': 'Asignación guardada.' + aviso}


@router.post('/requerimientos/masivo')
def crear_asignacion_masiva(peticion: AsignacionMasiva):
    """La misma asignación a varias personas, con un identificador de grupo.

    El grupo se guarda en cada fila y no en una tabla aparte: así una persona se
    puede sacar del grupo sin desmontarlo, y el grupo entero se cancela de una
    vez buscando por ese identificador.
    """
    if not peticion.empleado_ids:
        raise ValueError('No hay nadie a quien asignar esto.')
    grupo = f'G{uuid.uuid4().hex[:10].upper()}'
    etiqueta = (f'Área {AREAS_BONITAS.get(str(peticion.area), peticion.area)}'
                if peticion.alcance == 'area' else 'Todo el personal')

    # Primero se mira a todo el mundo y solo después se escribe, todo de una
    # vez. Antes se guardaba persona a persona dentro del bucle, cada una con su
    # transacción, y la comprobación de que esa persona existe estaba **dentro**:
    # si la cuarta ya no estaba en la plantilla, las tres primeras se quedaban
    # guardadas y la respuesta era un error. Quien lo leía no tenía forma de
    # saber que tres personas sí la tenían puesta, ni cuáles.
    por_guardar, omitidos, areas = [], [], set()
    for empleado_id in peticion.empleado_ids:
        datos = {**peticion.requerimiento.model_dump(), 'empleado_id': int(empleado_id),
                 'grupo_id': grupo, 'grupo_alcance': peticion.alcance,
                 'grupo_area': peticion.area if peticion.alcance == 'area' else None,
                 'grupo_etiqueta': etiqueta}
        if peticion.aplicar_solo_compatibles:
            revision = prevalidar_asignacion(AsignacionNueva(**{
                **peticion.requerimiento.model_dump(), 'empleado_id': int(empleado_id)}))
            if not revision['compatible']:
                omitidos.append({'empleado_id': int(empleado_id),
                                 'nombre': _nombre(int(empleado_id)),
                                 'motivo': revision['conflictos'][0]['mensaje']})
                continue
        ficha = _ficha(int(empleado_id))
        areas.add(ficha['area'])
        por_guardar.append(datos)

    creadas = novedades.crear_asignaciones(por_guardar)
    if not creadas:
        raise ValueError(
            'No se pudo guardar para nadie: todas las personas del grupo tienen ya '
            'otra novedad en esas fechas.')

    historial.anotar('crear_asignacion_masiva', 'asignacion',
                     {'grupo_id': grupo, 'creadas': len(creadas),
                      'omitidos': len(omitidos), 'etiqueta': etiqueta})
    aviso = ''.join(_avisar_de_la_asignacion(peticion.requerimiento.model_dump(), area,
                                             'se añadió una asignación masiva')
                    for area in sorted(areas))
    resumen = f'Asignación guardada para {len(creadas)} persona(s).'
    if omitidos:
        resumen += (f' Se omitieron {len(omitidos)}: '
                    + ', '.join(o['nombre'] for o in omitidos) + '.')
    return {'ok': True, 'grupo_id': grupo, 'creadas': creadas, 'omitidos': omitidos,
            'conflictos_grupo_aceptados': [], 'mensaje': resumen + aviso}


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


@router.patch('/requerimientos/grupo/{grupo_id}/cancelar')
def cancelar_grupo(grupo_id: str):
    afectadas = [a for a in novedades.listar_asignaciones() if a.get('grupo_id') == grupo_id]
    if not afectadas:
        raise ValueError('Ese grupo ya no existe.')
    cuantas = novedades.cancelar_grupo(grupo_id)
    historial.anotar('cancelar_grupo_asignacion', 'asignacion',
                     {'grupo_id': grupo_id, 'canceladas': cuantas})
    aviso = _avisar_del_grupo(afectadas, 'se canceló una asignación masiva')
    return {'ok': True, 'canceladas': cuantas, 'mensaje': (
        f'Se canceló la asignación de {cuantas} persona(s). Queda en el historial.' + aviso)}


@router.delete('/requerimientos/grupo/{grupo_id}')
def borrar_grupo(grupo_id: str):
    afectadas = [a for a in novedades.listar_asignaciones() if a.get('grupo_id') == grupo_id]
    if not afectadas:
        raise ValueError('Ese grupo ya no existe.')
    aviso = _avisar_del_grupo(afectadas, 'se eliminó una asignación masiva')
    cuantas = novedades.borrar_grupo(grupo_id)
    historial.anotar('borrar_grupo_asignacion', 'asignacion',
                     {'grupo_id': grupo_id, 'eliminadas': cuantas})
    return {'ok': True, 'eliminadas': cuantas, 'mensaje': (
        f'Se eliminaron las {cuantas} asignación(es) del grupo.' + aviso)}


@router.put('/requerimientos/{asignacion_id}')
def editar_asignacion(asignacion_id: int, asignacion: AsignacionNueva):
    antes = _buscar_asignacion(asignacion_id)
    datos = asignacion.model_dump()
    novedades.actualizar_asignacion(asignacion_id, datos)
    historial.anotar('editar_asignacion', 'asignacion', {'id': asignacion_id})
    area = antes['area']
    aviso = (_avisar_de_la_asignacion(antes, area, 'se corrigió una asignación')
             + _avisar_de_la_asignacion(datos, area, 'se corrigió una asignación'))
    return {'ok': True, 'mensaje': 'Asignación corregida.' + aviso}


@router.patch('/requerimientos/{asignacion_id}/cancelar')
def cancelar_asignacion(asignacion_id: int):
    asignacion = _buscar_asignacion(asignacion_id)
    novedades.cancelar_asignacion(asignacion_id)
    historial.anotar('cancelar_asignacion', 'asignacion', {'id': asignacion_id})
    aviso = _avisar_de_la_asignacion(asignacion, asignacion['area'],
                                     'se canceló una asignación')
    return {'ok': True, 'mensaje': (
        'Asignación cancelada. Se conserva en el historial.' + aviso)}


@router.delete('/requerimientos/{asignacion_id}')
def borrar_asignacion(asignacion_id: int):
    asignacion = _buscar_asignacion(asignacion_id)
    novedades.borrar_asignacion(asignacion_id)
    historial.anotar('borrar_asignacion', 'asignacion', {'id': asignacion_id})
    aviso = _avisar_de_la_asignacion(asignacion, asignacion['area'],
                                     'se eliminó una asignación')
    return {'ok': True, 'mensaje': 'Asignación eliminada definitivamente.' + aviso}
