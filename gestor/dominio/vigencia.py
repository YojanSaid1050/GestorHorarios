"""Configuración de una persona que cambia dentro del mismo periodo.

Hasta ahora la aplicación resolvía **una sola configuración por periodo**: se
tomaba la última que estuviera vigente al terminar el mes y se aplicaba a los
treinta días. Eso impedía decir algo tan normal como «Fulano y Mengana eran fijos
hasta el domingo 20 y rotan desde el lunes 21»: al ponerles el ancla de rotación
el 21, también rotaban hacia atrás.

Este módulo resuelve esa parte. Guarda, junto a la configuración final de la
persona, la que tenía al empezar el periodo y la lista de cambios con la fecha
desde la que rige cada uno, y permite preguntar «¿cómo estaba configurada esta
persona el día X?».

Regla de oro: un cambio que afecta al turno (fijo↔rotativo, turno fijo, ancla,
orden de rotación) rige **desde un lunes**. El carrusel de turnos gira por
semanas, así que una persona que pasara a rotativo un miércoles cambiaría de AM
a PM a mitad de semana y arrastraría a su pareja con ella, que es justo lo que
prohíbe la regla de consistencia semanal. Los cambios que no tocan el turno
—descanso fijo, exención de especiales— pueden regir cualquier día.
"""

from __future__ import annotations

from datetime import date, timedelta

# Campos cuya variación cambia el turno o el descanso de un día concreto.
CAMPOS_CONFIG_DIARIA = (
    'area',
    'tipo_turno',
    'turno_fijo',
    'descanso_fijo',
    'inicio_rotacion',
    'fecha_ancla_rotacion',
    'orden_rotacion',
    'pareja_id',
    'exento_especiales',
)

# Campos que obligan a que el cambio empiece en lunes.
CAMPOS_SEMANALES = (
    'area',
    'tipo_turno',
    'turno_fijo',
    'inicio_rotacion',
    'fecha_ancla_rotacion',
    'orden_rotacion',
)


def _iso(valor) -> str:
    if valor is None:
        return ''
    if hasattr(valor, 'isoformat'):
        return valor.isoformat()[:10]
    return str(valor)[:10]


def instantanea(cfg: dict) -> dict:
    """Reduce una configuración a los campos que deciden el día a día."""
    return {campo: cfg.get(campo) for campo in CAMPOS_CONFIG_DIARIA}


def lunes_de(fecha: str | date) -> date:
    f = date.fromisoformat(fecha) if isinstance(fecha, str) else fecha
    return f - timedelta(days=f.weekday())


def proximo_lunes(fecha: str | date) -> date:
    """Lunes en el que puede empezar a regir un cambio de turno.

    Si la fecha ya es lunes, es esa misma. Si no, el lunes siguiente: nunca se
    adelanta un cambio a días que la persona ya tenía decididos.
    """
    f = date.fromisoformat(fecha) if isinstance(fecha, str) else fecha
    dias = (7 - f.weekday()) % 7
    return f + timedelta(days=dias)


def afecta_al_turno(anterior: dict, nuevo: dict) -> bool:
    return any(anterior.get(c) != nuevo.get(c) for c in CAMPOS_SEMANALES)


def normalizar_cambios(base: dict, cambios: list[dict],
                       inicio_periodo: str | date | None = None) -> list[dict]:
    """Deja solo los cambios que realmente modifican algo, en orden.

    Los snapshots se guardan también cuando se edita cualquier otro dato de la
    ficha (nombre, cargo, teléfono) y cuando la aplicación configura sola a
    alguien recién dado de alta. Si no se filtraran, cada edición se leería como
    una transición y el motor trataría esa semana como excepción sin que nada
    hubiera cambiado en el turno.

    Un cambio que sí toca el turno se lleva al lunes de su semana. El reparto
    AM/PM se decide una vez por semana y vale los siete días: aplicarlo a mitad
    de semana obligaría a la persona —y a su pareja— a cambiar de turno un
    miércoles, que es justo lo que prohíbe la regla de consistencia semanal.
    Nunca se lleva más atrás del primer día del periodo, que ya está decidido.
    """
    piso = _iso(inicio_periodo) if inicio_periodo else ''
    actual = instantanea(base)
    salida: list[dict] = []
    for cambio in sorted(cambios, key=lambda c: (_iso(c.get('desde')), int(c.get('orden') or 0))):
        desde = _iso(cambio.get('desde'))
        if not desde:
            continue
        propuesta = cambio.get('cfg') or {}
        nuevo = {c: propuesta.get(c, actual.get(c)) for c in CAMPOS_CONFIG_DIARIA}
        if nuevo == actual:
            continue
        toca_turno = afecta_al_turno(actual, nuevo)
        if toca_turno:
            desde = max(piso, lunes_de(desde).isoformat())
        salida.append({'desde': desde, 'cfg': nuevo, 'afecta_turno': toca_turno})
        actual = nuevo
    # Al alinear a lunes, dos cambios de la misma semana pueden quedar en la
    # misma fecha. Manda el último: es la configuración con la que se cierra.
    fusionados: list[dict] = []
    for cambio in salida:
        if fusionados and fusionados[-1]['desde'] == cambio['desde']:
            fusionados[-1] = cambio
        else:
            fusionados.append(cambio)
    return fusionados


def separar_cambios(base: dict, cambios: list[dict],
                    inicio_periodo: str | date | None = None) -> tuple[dict, list[dict]]:
    """Configuración con la que arranca el periodo y transiciones posteriores.

    Un cambio que, alineado a lunes, cae justo el primer día del periodo no es
    una transición: es sencillamente la configuración con la que ese periodo
    empieza. Devolverlo como transición marcaría el día 1 como excepción sin
    que nada cambie ese día.
    """
    piso = _iso(inicio_periodo) if inicio_periodo else ''
    normalizados = normalizar_cambios(base, cambios, inicio_periodo)
    arranque = instantanea(base)
    posteriores = []
    for cambio in normalizados:
        if piso and cambio['desde'] <= piso:
            arranque = cambio['cfg']
        else:
            posteriores.append(cambio)
    return arranque, posteriores


def config_en_fecha(empleado: dict, fecha: str | date) -> dict:
    """Cómo estaba configurada esa persona ese día.

    Devuelve el mismo diccionario cuando no hay transiciones, para no pagar una
    copia por persona y día en el caso normal, que es el de siempre.
    """
    cambios = empleado.get('cambios_config') or []
    if not cambios:
        return empleado
    dia = _iso(fecha)
    vigente = None
    for cambio in cambios:
        if cambio['desde'] <= dia:
            vigente = cambio
        else:
            break
    if vigente is None:
        inicial = empleado.get('config_inicial')
        return {**empleado, **inicial} if inicial else empleado
    return {**empleado, **vigente['cfg']}


def fechas_de_transicion(empleado: dict) -> set[str]:
    """Días en que empieza a regir un cambio de turno para esa persona."""
    return {c['desde'] for c in (empleado.get('cambios_config') or []) if c.get('afecta_turno')}
