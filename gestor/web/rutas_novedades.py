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
from gestor.servicios import historial, periodos

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
    novedades.actualizar_solicitud(solicitud_id, solicitud.model_dump())
    historial.anotar('editar_solicitud', 'solicitud', {'id': solicitud_id})
    aviso = ''
    if antes['estado'] == 'aprobada':
        # Cambiar las fechas de algo aprobado mueve el horario dos veces: donde
        # estaba y donde pasa a estar.
        aviso = _avisar_de_la_solicitud(antes, 'se corrigió una novedad aprobada')
        aviso += _avisar_de_la_solicitud(
            {**antes, **solicitud.model_dump()}, 'se corrigió una novedad aprobada')
    return {'ok': True, 'mensaje': 'Solicitud corregida.' + aviso}


@router.get('/solicitudes/{solicitud_id}/prevalidar')
def prevalidar(solicitud_id: int):
    """¿Chocaría con algo ya aprobado? Se pregunta antes de aprobar."""
    solicitud = _buscar_solicitud(solicitud_id)
    choques = novedades.solapadas(
        solicitud['empleado_id'], solicitud['fecha_inicio'], solicitud['fecha_fin'],
        excluir=solicitud_id)
    conflictos = [{
        'codigo': 'NOVEDAD_SOLAPADA',
        'fecha': c['fecha_inicio'],
        'empleado_id': solicitud['empleado_id'],
        'mensaje': (f'{solicitud["empleado_nombre"]} ya tiene aprobado {c["tipo"]} '
                    f'del {c["fecha_inicio"]} al {c["fecha_fin"]}. Cancela una de las '
                    'dos antes de aprobar esta.'),
    } for c in choques]
    return {'ok': True, 'compatible': not conflictos, 'conflictos': conflictos,
            'avisos': [c['mensaje'] for c in conflictos]}


@router.patch('/solicitudes/{solicitud_id}/aprobar')
def aprobar(solicitud_id: int):
    previo = prevalidar(solicitud_id)
    if not previo['compatible']:
        raise ValueError(previo['avisos'][0])
    solicitud = _buscar_solicitud(solicitud_id)
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


@router.post('/requerimientos/prevalidar')
def prevalidar_asignacion(asignacion: AsignacionNueva):
    datos = asignacion.model_dump()
    conflictos = []
    for fecha in datos.get('fechas') or []:
        choques = novedades.solapadas(datos['empleado_id'], fecha, fecha)
        if choques:
            conflictos.append({
                'codigo': 'NOVEDAD_SOLAPADA', 'fecha': fecha,
                'empleado_id': datos['empleado_id'],
                'mensaje': (f'El {fecha} esa persona ya tiene aprobada otra novedad '
                            f'({choques[0]["tipo"]}).')})
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

    creadas, omitidos, areas = [], [], set()
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
        creadas.append(novedades.crear_asignacion(datos))

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


@router.patch('/requerimientos/grupo/{grupo_id}/cancelar')
def cancelar_grupo(grupo_id: str):
    afectadas = [a for a in novedades.listar_asignaciones() if a.get('grupo_id') == grupo_id]
    if not afectadas:
        raise ValueError('Ese grupo ya no existe.')
    cuantas = novedades.cancelar_grupo(grupo_id)
    historial.anotar('cancelar_grupo_asignacion', 'asignacion',
                     {'grupo_id': grupo_id, 'canceladas': cuantas})
    aviso = ''.join(_avisar_de_la_asignacion(a, a['area'], 'se canceló una asignación masiva')
                    for a in afectadas[:1])
    return {'ok': True, 'canceladas': cuantas, 'mensaje': (
        f'Se canceló la asignación de {cuantas} persona(s). Queda en el historial.' + aviso)}


@router.delete('/requerimientos/grupo/{grupo_id}')
def borrar_grupo(grupo_id: str):
    afectadas = [a for a in novedades.listar_asignaciones() if a.get('grupo_id') == grupo_id]
    if not afectadas:
        raise ValueError('Ese grupo ya no existe.')
    aviso = ''.join(_avisar_de_la_asignacion(a, a['area'], 'se eliminó una asignación masiva')
                    for a in afectadas[:1])
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
