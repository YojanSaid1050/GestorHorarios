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

from gestor.datos import horarios, novedades, personal
from gestor.dominio import calendario
from gestor.registro import obtener
from gestor.servicios import continuidad, periodos

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


def generar(mes: int, anio: int, cuantas: int = PROPUESTAS) -> Generacion:
    """Calcula las propuestas del mes y las guarda."""
    from gestor.motor.orquestacion import generar_horario_completo

    aviso = continuidad.falta_el_mes_anterior(mes, anio)
    if aviso:
        raise NoSePuedeGenerar(aviso)

    empleados = personal.listar()
    if not empleados:
        raise NoSePuedeGenerar(
            'No hay nadie en la plantilla, así que no hay horario que armar. '
            'Añade personal en la pantalla de Personal.')

    solicitudes = novedades.solicitudes_para_el_motor(mes, anio)
    asignaciones = novedades.asignaciones_para_el_motor(mes, anio)
    contexto = continuidad.todo(mes, anio)

    vistas: set[tuple] = set()
    propuestas: list[dict] = []
    for variante in range(VARIANTES):
        if len(propuestas) >= cuantas:
            break
        try:
            resultado = generar_horario_completo(
                empleados, solicitudes, int(mes), int(anio),
                variante=variante, requerimientos=asignaciones, **contexto)
        except Exception:                                          # noqa: BLE001
            # Que una variante falle no puede tumbar la generación entera: se
            # deja constancia y se sigue con la siguiente. Antes, un fallo en la
            # tercera variante dejaba al usuario sin ninguna propuesta y sin
            # saber por qué.
            obtener().exception('la variante %s de %s-%s no se pudo calcular',
                                variante, anio, mes)
            continue
        firma = _firma(resultado)
        if firma in vistas:
            continue
        vistas.add(firma)
        propuestas.append(resultado)

    if not propuestas:
        raise NoSePuedeGenerar(
            f'No se pudo armar ninguna propuesta para {calendario.nombre_del_periodo(mes, anio)}. '
            'Revisa las novedades aprobadas y las asignaciones de ese mes: puede que se '
            'contradigan entre ellas.')

    grupo = f'{anio}-{int(mes):02d}-{uuid.uuid4().hex[:8]}'
    ids = horarios.guardar_propuestas(anio, mes, grupo, propuestas)
    # El mes se acaba de rehacer con lo que hay ahora mismo: deja de estar
    # desactualizado, y con él desaparecen los motivos que lo habían marcado.
    periodos.limpiar(int(mes), int(anio))
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
    # El mes elegido queda al día; los de después pasan a estar apoyados en un
    # horario que ya no es el que se usó para armarlos.
    periodos.limpiar(int(elegido['mes']), int(elegido['anio']))
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
