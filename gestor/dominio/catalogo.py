# -*- coding: utf-8 -*-
"""Las reglas, explicadas para quien usa la aplicación.

Esto no es donde viven las reglas —viven en el motor y en `dominio`— sino donde
se cuentan. La diferencia importa: aquí no hay ninguna lógica, solo el texto
que la pantalla de Validación enseña para que alguien pueda entender por qué la
aplicación no le deja publicar algo.

Están en tres niveles, y el nivel es lo único que la pantalla necesita para
agruparlas:

* **bloqueante** — protege algo ya decidido. No se salta: se deshace la decisión
  primero (abrir la semana cerrada, por ejemplo).
* **decisión** — la aplicación la cumple sola al armar el mes, y una persona
  puede saltársela a mano explicando por qué.
* **advertencia** — señala algo para que se mire. No impide dar el mes por bueno.

El texto de «qué hacer» no es un adorno. Un aviso que dice qué está mal y no
qué hacer con ello obliga a adivinar, y lo que se adivina en una oficina con
prisa es «pulsar otra vez».
"""
from __future__ import annotations

REGLAS: dict[str, dict] = {
    'SEMANA_CERRADA': {
        'prioridad': 100, 'nivel': 'bloqueante', 'forzable': False,
        'nombre': 'Semana cerrada',
        'descripcion': 'Una semana cerrada se conserva exactamente como se publicó.',
        'que_hacer': 'Ábrela desde Horario o desde Modificar horario antes de cambiarla.'},
    'INCAPACIDAD': {
        'prioridad': 96, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Incapacidad aprobada',
        'descripcion': 'La persona está incapacitada: ese día no puede llevar un turno normal.',
        'que_hacer': 'Corrige o cancela la incapacidad si se registró por error.'},
    'VACACIONES': {
        'prioridad': 95, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Vacaciones aprobadas',
        'descripcion': 'Las vacaciones mandan sobre la programación ordinaria.',
        'que_hacer': 'Corrige o cancela las vacaciones si las fechas cambiaron.'},
    'PERMISO': {
        'prioridad': 94, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Permiso aprobado',
        'descripcion': 'El permiso protege esa fecha.',
        'que_hacer': 'Modifica o cancela el permiso si ya no corresponde.'},
    'ASIGNACION_EXPLICITA': {
        'prioridad': 90, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Asignación directa',
        'descripcion': 'Hay una actividad o una jornada administrativa puesta a propósito.',
        'que_hacer': 'Revisa la asignación y decide si se mantiene o se cancela.'},
    'ASIGNACIONES_INCOMPATIBLES': {
        'prioridad': 89, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Dos asignaciones que se contradicen',
        'descripcion': ('La misma persona tiene ese día otra asignación que fija una '
                        'jornada distinta. Un día solo se resuelve de una manera: o '
                        'descansa, o trabaja en un turno, o hace jornada administrativa.'),
        'que_hacer': 'Cancela o cambia la asignación anterior, o elige otra fecha.'},
    'FESTIVO': {
        'prioridad': 85, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Festivo',
        'descripcion': ('Quien trabaja un domingo o un festivo tiene después un día de '
                        'descanso compensatorio.'),
        'que_hacer': 'Si el festivo se trasladó, cámbialo en Configuración.'},
    'ULTIMO_VIERNES_ADM': {
        'prioridad': 80, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Último viernes administrativo',
        'descripcion': ('El último viernes del mes toda la oficina hace jornada '
                        'administrativa.'),
        'que_hacer': 'Solo una ausencia o una asignación directa cambia esa jornada.'},
    'MAX_JORNADAS_SEGUIDAS': {
        'prioridad': 79, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Máximo de jornadas seguidas',
        'descripcion': ('Nadie encadena más jornadas seguidas que el tope configurado. '
                        'La aplicación intenta cortar la racha moviendo un descanso '
                        'antes de dar el mes por imposible.'),
        'que_hacer': ('Deja que la aplicación mueva un descanso. Si hace falta de '
                      'verdad, autoriza el día a mano y explica por qué.')},
    'FATIGA_PM_AM': {
        'prioridad': 78, 'nivel': 'decision', 'forzable': True,
        'nombre': 'De la tarde a la mañana siguiente',
        'descripcion': ('No se pasa de PM directamente a AM al día siguiente: son menos '
                        'horas de descanso de las que caben en una noche. Un descanso, '
                        'unas vacaciones o una incapacidad por medio ya cortan la '
                        'secuencia.'),
        'que_hacer': 'Mete un descanso entre los dos días, o cambia uno de los turnos.'},
    'DESCANSO_FIJO': {
        'prioridad': 70, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Descanso fijo',
        'descripcion': 'Esa persona tiene un día fijo de descanso puesto en Personal.',
        'que_hacer': 'Si el día cambió de forma permanente, actualízalo en Personal.'},
    'COBERTURA_AREA': {
        'prioridad': 70, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Cobertura mínima del área',
        'descripcion': ('Cada área tiene un mínimo de gente por día, según el reparto '
                        'vigente. Un mínimo nunca puede exigir al área entera: si lo '
                        'hiciera, nadie podría descansar, así que se pide como mucho '
                        'todos menos uno.'),
        'que_hacer': ('Mueve un descanso, cambia un turno, o ajusta el reparto del área '
                      'en Configuración.')},
    'PAREJA_MISMO_TURNO': {
        'prioridad': 70, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Pareja en el mismo turno',
        'descripcion': ('Dos personas emparejadas se cubren entre sí, así que no van en '
                        'el mismo turno: si coincidieran, el otro turno quedaría sin '
                        'ninguna de las dos.'),
        'que_hacer': ('Cambia el turno de una. Si la coincidencia viene de una '
                      'asignación directa, la aplicación ya la acepta.')},
    'DESCANSO_SEMANAL': {
        'prioridad': 65, 'nivel': 'decision', 'forzable': True,
        'nombre': 'Descanso semanal',
        'descripcion': 'Cada persona operativa descansa un día de cada semana.',
        'que_hacer': 'Mueve el descanso a otro día de esa misma semana.'},
    'ROTACION': {
        'prioridad': 50, 'nivel': 'advertencia', 'forzable': True,
        'nombre': 'Rotación semanal',
        'descripcion': 'El turno se aparta de la rotación configurada para esa persona.',
        'que_hacer': 'Mira si es algo de esta semana o si hay que cambiarle la base.'},
    'HORAS_DE_LA_SEMANA': {
        'prioridad': 40, 'nivel': 'advertencia', 'forzable': True,
        'nombre': 'Horas de la semana',
        'descripcion': ('Una semana normal suma 42 horas. Un festivo, un descanso '
                        'compensatorio o una ausencia aprobada la bajan, y una jornada '
                        'administrativa la sube media hora.'),
        'que_hacer': 'Es información, no un problema. No hace falta corregir nada.'},
}


def catalogo() -> list[dict]:
    """Las reglas ordenadas por importancia, con el tope real ya escrito.

    El tope de jornadas se lee de la configuración y no se escribe aquí a mano.
    En la versión anterior el catálogo decía «máximo 7» mientras la regla
    configurada era de 10, y quien llegaba nuevo se creía lo que veía.
    """
    try:
        from gestor.servicios.reglas_operacion import maximo_dias
        tope = maximo_dias()
    except Exception:                                              # noqa: BLE001
        tope = None

    salida = []
    for clave, regla in sorted(REGLAS.items(),
                               key=lambda kv: (-kv[1]['prioridad'], kv[0])):
        ficha = {'id': clave, **regla}
        if tope and 'jornadas seguidas' in ficha['nombre']:
            ficha['nombre'] = f'Máximo {tope} jornadas seguidas'
            ficha['descripcion'] = ficha['descripcion'].replace(
                'más jornadas seguidas que el tope configurado',
                f'más de {tope} jornadas seguidas')
        salida.append(ficha)
    return salida


def conflicto(clave: str, mensaje: str, *, empleado_id=None, fecha=None,
              datos: dict | None = None) -> dict:
    """Un incumplimiento concreto, con la ficha de su regla pegada.

    Así la pantalla puede enseñar el qué (el mensaje), el porqué (la
    descripción) y el qué hacer sin tener que buscar nada.
    """
    ficha = REGLAS.get(clave, {
        'prioridad': 50, 'nivel': 'bloqueante', 'forzable': False,
        'nombre': 'Regla de programación', 'descripcion': '',
        'que_hacer': 'Revisa la programación.'})
    return {'regla': clave, 'mensaje': mensaje, 'empleado_id': empleado_id,
            'fecha': fecha, 'datos': datos or {},
            'nivel': ficha['nivel'], 'forzable': ficha['forzable'],
            'prioridad': ficha['prioridad'], 'nombre': ficha['nombre'],
            'descripcion': ficha['descripcion'], 'que_hacer': ficha['que_hacer']}
