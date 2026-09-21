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

from gestor.datos import novedades
from gestor.servicios import exclusion, historial
from gestor.servicios.validacion_novedades import (
    _avisar_de_la_asignacion as _avisar_de_la_asignacion,
)
from gestor.servicios.validacion_novedades import (
    _avisar_de_la_solicitud as _avisar_de_la_solicitud,
)
from gestor.servicios.validacion_novedades import (
    _avisar_del_grupo as _avisar_del_grupo,
)
from gestor.servicios.validacion_novedades import (
    _buscar_asignacion as _buscar_asignacion,
)
from gestor.servicios.validacion_novedades import (
    _buscar_solicitud as _buscar_solicitud,
)
from gestor.servicios.validacion_novedades import (
    _conflictos as _conflictos,
)
from gestor.servicios.validacion_novedades import (
    _conflictos_de_asignacion as _conflictos_de_asignacion,
)
from gestor.servicios.validacion_novedades import (
    _exigir_que_no_choque as _exigir_que_no_choque,
)
from gestor.servicios.validacion_novedades import (
    _fechas_que_ocupa as _fechas_que_ocupa,
)
from gestor.servicios.validacion_novedades import (
    _ficha as _ficha,
)
from gestor.servicios.validacion_novedades import (
    _nombre as _nombre,
)
from gestor.web.modelos_novedades import (
    AsignacionMasiva as AsignacionMasiva,
)
from gestor.web.modelos_novedades import (
    AsignacionNueva as AsignacionNueva,
)
from gestor.web.modelos_novedades import (
    SolicitudNueva as SolicitudNueva,
)

router = APIRouter(prefix='/api', tags=['novedades'])








AREAS_BONITAS = {'gestion_social': 'Gestión Social',
                 'atencion_ciudadano': 'Atención al Ciudadano',
                 'comunicaciones': 'Comunicaciones'}














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
