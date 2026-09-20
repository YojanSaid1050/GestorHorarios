# -*- coding: utf-8 -*-
"""Armar el mes: reunir todo lo que hay que tener en cuenta y llamar al motor.

Aquí no se decide ningún turno. Lo que se hace es juntar en un sitio las seis
cosas que el motor necesita —el personal vigente, las novedades aprobadas, las
asignaciones, los cambios manuales guardados, la continuidad con el mes anterior
y las reglas de ese momento— y entregarle cada una.

Se generan **cinco propuestas** del mismo mes. No es un adorno: un horario
correcto no es único, y poder comparar cinco antes de elegir es lo que convierte
la aplicación en una herramienta y no en un oráculo. Cada propuesta se calcula
con una variante distinta del reparto y se descartan las repetidas: enseñar
cinco opciones que en realidad son la misma sería peor que enseñar una.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from gestor.datos import ajustes as datos_ajustes
from gestor.datos import horarios, novedades, personal
from gestor.dominio import calendario
from gestor.registro import obtener
from gestor.servicios import cierres, continuidad, periodos

#: Cuántas propuestas se ofrecen para comparar.
PROPUESTAS = 5
#: Cuántas variantes se prueban para conseguirlas. Se piden de más porque
#: algunas salen repetidas y se descartan.
VARIANTES = 12


class NoSePuedeGenerar(Exception):
    """Falta algo para poder armar el mes, y el mensaje dice qué."""


@dataclass
class Generacion:
    anio: int
    mes: int
    grupo_id: str
    propuestas: list[dict]

    def como_dict(self) -> dict:
        return {
            'anio': self.anio, 'mes': self.mes, 'grupo_id': self.grupo_id,
            'cantidad': len(self.propuestas),
            'propuestas': self.propuestas,
        }


def _firma(resultado: dict) -> tuple:
    """Dos propuestas con los mismos turnos son la misma propuesta."""
    return tuple(
        (fila['empleado_id'], tuple(d['turno'] for d in fila['dias']))
        for fila in resultado.get('horario', ())
    )


#: Novedades que, una vez aprobadas, mandan sobre el horario: el motor no las
#: decide, las refleja. Un cambio a mano no puede taparlas (ver
#: `motor.decisiones.NO_SE_PISAN_NI_FORZANDO`).
MANDAN_SOBRE_EL_HORARIO = ('vacaciones', 'incapacidad', 'permiso', 'capacitacion')


def _tapado_por_una_ausencia(ajuste: dict, solicitudes: list[dict]) -> bool:
    """¿Ese ajuste guardado cae sobre un día que ya tiene una novedad aprobada?

    Si cae, se descarta en silencio en vez de entregárselo al motor. El motor lo
    rechazaría —y hace bien—, pero ese rechazo es un error, y un error deja las
    cinco propuestas marcadas como inválidas: el mes entero quedaría en rojo por
    un ajuste de hace semanas al que la realidad pasó por encima, sin más salida
    que ir a buscarlo y borrarlo a mano.

    La novedad es posterior y es una decisión de alguien; el ajuste es una
    preferencia que ya no se puede cumplir.
    """
    empleado = int(ajuste.get('empleado_id') or 0)
    fecha = str(ajuste.get('fecha'))[:10]
    return any(
        int(s.get('empleado_id') or 0) == empleado
        and str(s.get('tipo') or '') in MANDAN_SOBRE_EL_HORARIO
        and str(s.get('fecha_inicio') or '')[:10] <= fecha
        <= str(s.get('fecha_fin') or s.get('fecha_inicio') or '')[:10]
        for s in solicitudes or ())


def generar(mes: int, anio: int, cuantas: int = PROPUESTAS) -> Generacion:
    """Calcula las propuestas del mes y las guarda."""
    from gestor.motor.orquestacion import generar_horario_completo

    if calendario.es_mes_base(int(mes), int(anio)):
        raise NoSePuedeGenerar(
            f'{calendario.nombre_del_periodo(int(mes), int(anio))} llega transcrito '
            'del Excel que la oficina ya trabajó: es de donde parte todo lo demás y '
            'no se vuelve a calcular. Si hay algo que corregir ahí, se corrige en la '
            'transcripción.')
    aviso = continuidad.falta_el_mes_anterior(mes, anio)
    if aviso:
        raise NoSePuedeGenerar(aviso)

    inicio, fin = calendario.rango(int(mes), int(anio))
    # La plantilla **de este periodo**, con sus cambios de turno dentro y no la
    # foto de cómo está hoy: programar que alguien rota desde noviembre no puede
    # hacerle rotar en octubre.
    empleados = personal.para_periodo(inicio.isoformat(), fin.isoformat())
    if not empleados:
        raise NoSePuedeGenerar(
            'No hay nadie en la plantilla, así que no hay horario que armar. '
            'Añade personal en la pantalla de Personal.')

    solicitudes = novedades.solicitudes_para_el_motor(mes, anio)
    asignaciones = novedades.asignaciones_para_el_motor(mes, anio)
    contexto = continuidad.todo(mes, anio)
    # La foto de los avisos que hay ahora: es lo que estas propuestas
    # incorporan, y lo único que se podrá dar por resuelto si se elige una.
    avisos = periodos.pendientes(int(mes), int(anio))

    # Lo que rehacer el mes **no** puede llevarse por delante.
    #
    # Las dos cosas estaban solo en la edición parcial, y volver a generar era
    # la puerta de atrás de las dos:
    #
    # * Los cambios a mano ya guardados. Se ponía un turno a mano, se guardaba,
    #   se volvía a generar el mes y volvía a estar como antes, sin decir nada.
    #   El ajuste seguía en la base —la pantalla lo enseñaba— y el horario no lo
    #   tenía: dos respuestas distintas a la misma pregunta.
    # * Las semanas cerradas. Cerrar una semana es decir «esta ya está y no se
    #   toca»; generar el mes entero ni siquiera preguntaba, así que la
    #   reescribía. Se congelan casilla a casilla desde el horario oficial, que
    #   es el que la oficina tiene en la mano.
    #
    # El orden importa: primero lo cerrado, y encima los ajustes. Un ajuste
    # dentro de una semana cerrada no se aplica, que es lo correcto —para eso
    # está cerrada—, y para eso lo cerrado tiene que ir delante.
    congelados = cierres.congelar_lo_cerrado(int(mes), int(anio))
    cerradas = cierres.fechas_cerradas(int(anio), int(mes))
    guardados = [a for a in datos_ajustes.para_el_motor(int(mes), int(anio))
                 if str(a.get('fecha'))[:10] not in cerradas
                 and not _tapado_por_una_ausencia(a, solicitudes)]
    manuales = congelados + guardados

    vistas: set[tuple] = set()
    propuestas: list[dict] = []
    #: Lo que reventó en cada variante, para poder distinguir «no cabe» de
    #: «el programa falló» cuando no queda ninguna propuesta.
    fallos: list[str] = []
    intentos = 0
    for variante in range(VARIANTES):
        if len(propuestas) >= cuantas:
            break
        intentos += 1
        try:
            resultado = generar_horario_completo(
                empleados, solicitudes, int(mes), int(anio),
                variante=variante, requerimientos=asignaciones,
                ajustes_manuales=manuales, **contexto)
        except Exception as fallo:                                 # noqa: BLE001
            # Que una variante falle no puede tumbar la generación entera: se
            # deja constancia y se sigue con la siguiente. Antes, un fallo en la
            # tercera variante dejaba al usuario sin ninguna propuesta y sin
            # saber por qué.
            obtener().exception('la variante %s de %s-%s no se pudo calcular',
                                variante, anio, mes)
            fallos.append(f'{type(fallo).__name__}: {fallo}')
            continue
        # Un horario sin una sola persona no es una propuesta.
        #
        # Cuando la configuración de la plantilla no cuadra —una pareja de PC
        # que apunta a alguien que ya no está, un rotativo sin lunes de
        # referencia— el motor contesta con `horario: []` y el motivo dentro.
        # Eso se guardaba como propuesta, las cinco iguales, y la pantalla
        # decía «Se armaron 5 propuestas, marca una como oficial». Se podían
        # marcar y publicar: un mes en blanco, oficial y publicado, del que el
        # siguiente heredaba otro mes en blanco.
        #
        # El motivo está escrito en `errores`; lo que hay que hacer es
        # enseñarlo, no esconderlo detrás de cinco propuestas vacías.
        if not resultado.get('horario'):
            fallos.extend(resultado.get('errores') or [])
            continue
        firma = _firma(resultado)
        if firma in vistas:
            continue
        vistas.add(firma)
        propuestas.append(resultado)

    if not propuestas:
        # Dos motivos distintos que se leían igual, y uno de los dos era mentira.
        #
        # Si **todas** las variantes reventaron con una excepción, lo que pasa
        # no es que las novedades se contradigan: es que el programa falló, y
        # decir lo contrario manda a buscar el problema donde no está. Pasó con
        # una sola solicitud de capacitación: el motor intentaba leer unas horas
        # que la tabla no guardaba, las cinco variantes morían igual, y la
        # pantalla acusaba de contradecirse a una novedad que estaba sola.
        # Si lo que hubo fueron errores de configuración de la plantilla, se
        # dicen tal cual: son accionables y se arreglan en Personal.
        de_plantilla = sorted({x for x in fallos if not x.startswith(('TypeError',
                                                                     'ValueError',
                                                                     'KeyError',
                                                                     'AttributeError'))})
        if de_plantilla:
            raise NoSePuedeGenerar(
                'No se pudo armar el horario porque la plantilla tiene algo sin '
                'resolver:\n· ' + '\n· '.join(de_plantilla[:6])
                + '\nArréglalo en Personal y vuelve a generar.')
        if fallos and len(fallos) >= intentos:
            raise NoSePuedeGenerar(
                f'No se pudo calcular {calendario.nombre_del_periodo(mes, anio)} por un '
                f'fallo del programa: {fallos[0]}. Queda apuntado con todo el detalle en '
                'el registro; pásaselo a quien mantiene la aplicación.')
        raise NoSePuedeGenerar(
            f'No se pudo armar ninguna propuesta para {calendario.nombre_del_periodo(mes, anio)}. '
            'Revisa las novedades aprobadas y las asignaciones de ese mes: puede que se '
            'contradigan entre ellas.')

    for propuesta in propuestas:
        propuesta['avisos_incorporados'] = list(avisos)

    grupo = f'{anio}-{int(mes):02d}-{uuid.uuid4().hex[:8]}'
    ids = horarios.guardar_propuestas(anio, mes, grupo, propuestas)
    # Aquí **no** se quita el aviso de desactualizado, y antes se quitaba.
    #
    # Generar deja cinco propuestas encima de la mesa; el horario del mes sigue
    # siendo el que había. Borrar el aviso al generar hacía desaparecer la
    # advertencia sin que nada hubiera cambiado: se generaba, no se elegía
    # ninguna, y el oficial seguía siendo el de antes —sin las vacaciones que se
    # acababan de aprobar dentro— pero ya sin nadie que lo dijera.
    #
    # El aviso se quita al **elegir** una propuesta, y solo los motivos
    # anteriores al momento en que esa propuesta se calculó.
    # `strict=True` a propósito: si volvieran menos identificadores que
    # propuestas, alguna se quedaría sin el suyo y no se podría marcar como
    # oficial. Sin esto, ese descuadre no da error: da una propuesta que no se
    # puede elegir y nadie sabe por qué.
    for propuesta, identificador in zip(propuestas, ids, strict=True):
        propuesta['horario_id'] = identificador
    return Generacion(anio=int(anio), mes=int(mes), grupo_id=grupo, propuestas=propuestas)


def marcar_oficial(horario_id: int) -> dict:
    """Deja una propuesta como la del mes, y avisa si eso desactualiza a otros.

    Cambiar el oficial de un mes cambia de qué parte el siguiente. No se toca
    nada por su cuenta —reescribir meses que la oficina ya tiene sería peor—
    pero se dice cuáles han quedado apoyados en algo que ya no existe.
    """
    elegido = horarios.marcar_oficial(horario_id)
    posteriores = []
    for anio, mes in horarios.meses_con_horario():
        if (anio, mes) <= (elegido['anio'], elegido['mes']):
            continue
        if horarios.oficial(anio, mes):
            posteriores.append(calendario.nombre_del_periodo(mes, anio))
    # El mes elegido queda al día **hasta donde llega esta propuesta**: lo que se
    # aprobó después de calcularla sigue fuera, y el aviso sigue diciéndolo.
    #
    # Y si la propuesta vino de reprogramar un área suelta, solo esa área queda
    # al día: las demás salieron congeladas tal y como estaban, así que lo que
    # tuvieran pendiente lo siguen teniendo. Antes se borraban también sus
    # marcas, y recalcular Gestión Social hacía desaparecer el pendiente de
    # Comunicaciones sin haberlo tocado.
    incorporados = list(elegido.get('avisos_incorporados') or [])
    areas = [a for a in ((elegido.get('reprogramacion_parcial') or {}).get('areas')
                         or []) if a]
    if areas:
        for area in areas:
            periodos.resolver(int(elegido['mes']), int(elegido['anio']),
                              incorporados, area=area)
    else:
        periodos.resolver(int(elegido['mes']), int(elegido['anio']), incorporados)
    fin = calendario.rango(int(elegido['mes']), int(elegido['anio']))[1]
    periodos.marcar_desde((fin + timedelta(days=1)).isoformat(),
                          'cambió el horario oficial del mes anterior',
                          origen='continuidad')
    return {
        'ok': True,
        'horario': elegido,
        'meses_que_dependian': posteriores,
        'mensaje': (
            'Esta propuesta queda como el horario oficial del mes. '
            + (f'Conviene volver a generar {", ".join(posteriores)}: partían del '
               'horario oficial anterior.' if posteriores else
               'El mes siguiente partirá de este horario.')),
    }
