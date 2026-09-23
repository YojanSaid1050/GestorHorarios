# -*- coding: utf-8 -*-
"""Lo que usan varias etapas del motor.

Leer un día, ordenar una semana, saber si una fecha es un descanso. Está
aquí porque lo necesitan la construcción, el balance y la reparación por
igual, y duplicarlo en cada una era pedir que se separaran con el tiempo.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

# Cómo se le cuenta a una persona un aviso de validación vive en su propio
# módulo: son ciento catorce líneas de texto que no dependen del horario.
from gestor.dominio import cobertura as _cobertura
from gestor.motor.vocabulario import (  # noqa: F401
    _CACHE_SECUENCIA,
    _LIMITE_RACHA,
    FATIGUE_ADMIN_CODES,
    MAX_DIAS_CONSECUTIVOS,
    NONWORK_CODES,
    OUT_OF_VIGENCY_CODE,
    WORK_CODES,
)
from gestor.servicios.reglas_cobertura import (
    regla as regla_cobertura,
)

FATIGUE_BREAK_CODES = {'D','VAC','INC','PER',OUT_OF_VIGENCY_CODE}

def maximo_dias_consecutivos() -> int:
    """Jornadas seguidas que admite la programación que se está construyendo."""
    activo = _LIMITE_RACHA.get()
    if activo:
        return int(activo)
    return int(MAX_DIAS_CONSECUTIVOS)


def minimo_cobertura(horario: list[dict], area: str, turno: str, fecha: Optional[str] = None) -> int:
    """Personas obligatorias en ese turno, según la regla vigente del área.

    La regla vive en la base y se puede cambiar desde la aplicación con fecha de
    vigencia, de modo que un cambio de política no altera los meses ya
    oficializados.

    La misma válvula que en `minimo_area_cobertura`: un mínimo nunca puede
    exigir a toda el área a la vez, porque entonces nadie podría descansar. En
    la versión anterior la válvula solo se aplicaba al mínimo del área y no al
    de cada turno, así que un área que se quedaba con una sola persona hacía
    imposible el mes en vez de ceder.
    """
    actual = regla_cobertura(area, fecha)
    pedido = actual.am_minimo if turno == 'AM' else actual.pm_minimo
    return _cobertura.exigido(pedido, _operativos_area(horario, area, fecha))


def _fechas_semana_de(horario: list[dict], fecha: Optional[str]) -> list[str]:
    """Fechas del horario que caen en la misma semana que ``fecha``."""
    if not fecha or not horario:
        return []
    referencia = next((d for d in horario[0].get('dias', []) if d.get('fecha') == fecha), None)
    if not referencia:
        return []
    lunes = referencia.get('lunes_semana')
    return [d['fecha'] for d in horario[0].get('dias', []) if d.get('lunes_semana') == lunes]

def maximo_cobertura(horario: list[dict], area: str, turno: str, fecha: Optional[str] = None) -> Optional[int]:
    """Cuántas personas admite como mucho ese turno, o ``None`` si no hay techo.

    Es la otra mitad de la regla de cobertura: además de no quedarse corta, un
    área tampoco puede amontonar a todo el mundo en la misma franja. Con esto
    se escribe «Comunicaciones admite 0, 1 o 2 en AM y 0 o 1 en PM».

    El techo nunca se aplica por debajo del mínimo obligatorio del mismo turno:
    si la configuración quedara contradictoria, manda el suelo, porque dejar el
    área descubierta es peor que pasarse de personas en una franja.
    """
    actual = regla_cobertura(area, fecha)
    tope = actual.am_maximo if turno == 'AM' else actual.pm_maximo
    if tope is None:
        return None
    efectivo = max(int(tope), minimo_cobertura(horario, area, turno, fecha))
    # Válvula de seguridad, igual que con el suelo del área: los techos se
    # configuran con la plantilla de ese momento. Si después entra gente, entre
    # los dos techos podría no caber todo el mundo y el área dejaría de poder
    # generarse. Antes que bloquear el mes, el techo cede: nunca puede ser tan
    # bajo que alguien se quede sin turno posible.
    tope_contrario = actual.pm_maximo if turno == 'AM' else actual.am_maximo
    if tope_contrario is not None:
        # Se cuenta la plantilla de la semana, no la del día: el reparto AM/PM
        # se decide una vez por semana, así que el techo tiene que dar cabida a
        # todos los que participan en ese reparto aunque alguno descanse.
        disponibles = max(
            _operativos_area(horario, area, fecha),
            *[_operativos_area(horario, area, f) for f in _fechas_semana_de(horario, fecha)] or [0],
        )
        efectivo = max(efectivo, disponibles - int(tope_contrario))
    # Quien tiene turno fijo no se puede repartir: su franja es parte de su
    # contrato, no una decisión del reparto. Si el área tiene más gente fija en
    # un turno que el techo configurado, manda la plantilla y el techo cede;
    # de lo contrario el mes sería imposible desde el primer día.
    fijos = sum(
        1 for e in horario
        if e.get('area') == area and e.get('tipo_turno') == 'fijo'
        and str(e.get('turno_base') or '') == turno
    )
    return max(efectivo, fijos)


def minimo_area_cobertura(horario: list[dict], area: str, fecha: Optional[str] = None) -> int:
    """Personas obligatorias en el área ese día, **en cualquier turno**.

    Es la regla real de Comunicaciones y de Atención al Ciudadano: lo que no
    puede ocurrir es que el área se quede sin nadie cubriendo, da igual si quien
    queda está en la mañana o en la tarde. Gestión Social, que sí cubre las dos
    franjas, lo consigue con sus mínimos por turno.

    La válvula —que un mínimo nunca puede exigir a toda el área a la vez, porque
    entonces nadie podría descansar— la aplica `dominio.cobertura.exigido`, que
    es la misma que usa la validación.
    """
    actual = regla_cobertura(area, fecha)
    return _cobertura.exigido(actual.minimo_area, _operativos_area(horario, area, fecha))


def _operativos_area(horario: list[dict], area: str, fecha: Optional[str] = None) -> int:
    """Personas del área que **podrían** cubrir un turno ese día.

    Los administrativos permanentes no cuentan: su jornada es otra y no releva a
    nadie. Es el tope de lo que se le puede exigir al área.
    """
    if fecha is None:
        return sum(1 for e in horario
                   if e.get('area') == area and e.get('tipo_turno') != 'administrativo')
    return _cobertura.conteo(horario, area, fecha).operativos


def _cuenta_como_cobertura(e: dict, d: dict) -> bool:
    """¿Esta persona sirve ese día para cumplir el mínimo de su área?

    Hay quien solo cubre ciertos días de la semana. El resto de días trabaja
    igual —sale con su turno de siempre— pero no vale como la persona que
    sostiene el turno, así que el área necesita a otra.

    Lo contesta el dominio. Todo lo que en este archivo tiene que ver con
    cobertura delega ahí: tener aquí una segunda implementación es lo que hizo
    que el motor y su propia validación discreparan tres veces.
    """
    return _cobertura.cubre_ese_dia(e, d)



def _conteo_area(horario: list[dict], area: str, fecha_iso: str, excluir: Optional[int] = None) -> int:
    """Personas del área que ese día cubren un turno operativo, AM o PM."""
    return _cobertura.conteo(horario, area, fecha_iso, excluir).cubriendo


def _reparto_fijado(area: str, fecha: Optional[str] = None) -> bool:
    """True si el área tiene un reparto AM/PM decidido por configuración.

    Solo en ese caso tiene sentido mover a alguien de un turno al otro para
    conservar la cobertura: es la contrapartida de fijar, por ejemplo, 2 AM y
    1 PM. Un área basada en turnos fijos personales (Gestión Social) no se
    reorganiza por su cuenta.
    """
    return regla_cobertura(area, fecha).am_objetivo is not None

def _es_ultimo_viernes_administrativo(d: Optional[dict]) -> bool:
    return bool(d and d.get('es_ultimo_viernes_administrativo'))

def _codigo_administrativo_area(area: str) -> Optional[str]:
    return {
        'gestion_social': 'ADM-GS',
        'atencion_ciudadano': 'ADM-AC',
        'comunicaciones': 'ADM-GS',
    }.get(area)

def turno_base_de(empleado: dict) -> Optional[str]:
    """Lo que se enseña en la columna «Base» del horario.

    Estaba escrito dos veces y las dos no decían lo mismo. El motor ponía
    `AM/PM` a quien rota y el código de su área a quien es administrativo; la
    siembra de los meses transcritos copiaba `turno_fijo` a secas, que para esas
    dos clases de persona vale `None`. Resultado: en agosto y septiembre de 2026
    —los dos meses que la oficina tiene de verdad— la columna «Base» enseñaba la
    palabra **«null»** en siete filas.

    Una regla, un sitio. Quien la cambie la cambia para los dos.
    """
    tipo = empleado.get('tipo_turno')
    if tipo == 'administrativo':
        return _codigo_administrativo_area(empleado.get('area'))
    if tipo == 'rotativo':
        return 'AM/PM'
    return empleado.get('turno_fijo')


def _codigo_guia_area(area: str) -> Optional[str]:
    """Código administrativo temporal/operativo correspondiente al área."""
    return {
        'gestion_social': 'ADM-GS',
        'atencion_ciudadano': 'ADM-GS',
        'comunicaciones': 'ADM-GS',
    }.get(area)

def _fila(horario: list[dict], eid: int) -> Optional[dict]:
    return next((e for e in horario if e['empleado_id'] == eid), None)

def _dia(fila: dict, fecha_iso: str) -> Optional[dict]:
    return next((d for d in fila['dias'] if d['fecha'] == fecha_iso), None)

def _es_excepcion_turno(d: Optional[dict]) -> bool:
    # Tanto la excepción directa como un cambio de turno solicitado y aprobado
    # son decisiones explícitas del usuario; por eso no se interpretan como un
    # error de consistencia semanal en esa fecha concreta.
    if not d:
        return False
    # Un día heredado se decidió y se publicó con el mes anterior. No es una
    # excepción que alguien haya autorizado hoy, pero tampoco algo que este
    # periodo pueda cambiar, así que no cuenta como cambio de turno a mitad de
    # semana: la semana se lee desde el turno con el que quedó publicada.
    if d.get('heredado'):
        return True
    # Día en que empieza a regir un cambio de configuración decidido en
    # «Asignaciones y ajustes» (por ejemplo, pasar de turno fijo a rotativo).
    # El turno cambia porque el usuario lo pidió, no por un error de la semana.
    if d.get('cambio_vigencia'):
        return True
    origen = str(d.get('origen') or '')
    return bool(
        origen.startswith('requerimiento:')
        or origen in {
            'ajuste_manual', 'solicitud:turno_dia', 'solicitud:turno_semanas',
            # Un intercambio aprobado cambia el turno de ese día por
            # definición: es la decisión explícita del usuario, no un error de
            # consistencia semanal.
            'intercambio_pareja', 'intercambio_persona',
            'reajuste_cobertura_max_6', 'reajuste_cobertura_domingo',
            # El turno adelantado al de la semana siguiente usa el descanso ya
            # programado como puente. Es una decisión explícita del motor para
            # evitar una jornada administrativa innecesaria.
            'adelanto_turno_por_descanso',
            # El puente administrativo es la solución que la propia regla de
            # fatiga contempla: ese día la persona hace jornada de oficina para
            # cortar el PM→AM, así que no es el reparto del área el que se ha
            # pasado del techo.
            'puente_fatiga_administrativo',
        }
    )

def _turno_operativo_semanal(d: Optional[dict]) -> Optional[str]:
    """Devuelve AM/PM para comprobar consistencia semanal.

    Los códigos ADM son jornadas independientes y no participan. Las fechas
    registradas como excepciones o cambios de turno aprobados se excluyen expresamente de la regla.
    """
    if not d:
        return None
    turno = d.get('turno')
    return str(turno) if turno in {'AM', 'PM'} else None

def _turno_semana_siguiente(e: dict, lunes: str) -> Optional[str]:
    """Turno operativo con el que la persona trabaja la semana que empieza el lunes siguiente."""
    try:
        siguiente = (date.fromisoformat(lunes) + timedelta(days=7)).isoformat()
    except ValueError:
        return None
    turnos = {
        d['turno'] for d in e.get('dias', [])
        if str(d.get('lunes_semana') or '') == siguiente and d.get('turno') in {'AM', 'PM'}
    }
    return turnos.pop() if len(turnos) == 1 else None

def _adelanta_turno_tras_descanso(e: dict, tramo: list[dict], lunes: str) -> bool:
    """¿Ese tramo adelanta el turno de la semana siguiente después del descanso?

    Es la excepción que pidió la operación, y es poco frecuente: alguien que
    descansa el sábado, trabaja el domingo y el lunes cambia a AM. Dejar ese
    domingo también en AM evita la transición PM→AM sin gastar un puente
    administrativo: el descanso que ya tenía hace de puente.

    Para que valga, el tramo tiene que empezar justo después de un día no
    laborado de esa misma semana y llevar exactamente el turno con el que la
    persona trabaja la semana siguiente. Cualquier otro cambio a mitad de
    semana sigue siendo un error.
    """
    if not tramo:
        return False
    turnos = {d['turno'] for d in tramo}
    if len(turnos) != 1:
        return False
    turno = turnos.pop()
    if turno != _turno_semana_siguiente(e, lunes):
        return False
    inicio = date.fromisoformat(tramo[0]['fecha'])
    anterior = next(
        (d for d in e.get('dias', [])
         if d.get('fecha') == (inicio - timedelta(days=1)).isoformat()),
        None,
    )
    if not anterior or anterior.get('turno') not in NONWORK_CODES:
        return False
    # El día no laborado tiene que pertenecer a la misma semana: si estuviera
    # en la anterior, no habría descanso que sirviera de puente aquí.
    return str(anterior.get('lunes_semana') or '') == lunes

def _violaciones_cambio_semanal(
    horario: list[dict],
    turnos_previos: Optional[dict[int, str]] = None,
) -> list[dict]:
    """Valida únicamente que AM/PM no cambien a mitad de una semana.

    Esta función solo valida consistencia AM/PM *dentro* de la semana. La regla
    de fatiga PM→AM se evalúa por separado sobre la secuencia diaria completa.
    Por eso un cambio entre semanas puede ser consistente semanalmente y, aun
    así, requerir D/VAC/INC/PER o un puente ADM antes del primer AM.

    El personal con descanso fijo se mantiene como excepción operativa, tal
    como se venía gestionando mediante Mover descanso, Modificación manual o
    Excepción de turno cuando se requieran patrones particulares.
    """
    violaciones: list[dict] = []
    for e in horario:
        if e.get('tipo_turno') == 'administrativo' or e.get('descanso_fijo') is not None:
            continue
        dias=sorted(e.get('dias', []), key=lambda x: x['fecha'])
        semanas=_semanas(e)

        # Si el mes comienza a mitad de una semana, conserva el turno operativo
        # del horario oficial anterior mientras no haya D/ADM/ausencia o una
        # excepción directa que corte esa continuidad.
        if dias and date.fromisoformat(dias[0]['fecha']).weekday() != 0:
            previo=(turnos_previos or {}).get(int(e['empleado_id']))
            primero=dias[0]
            turno_primero=_turno_operativo_semanal(primero)
            if (
                previo in {'AM','PM'} and turno_primero in {'AM','PM'}
                and not _es_excepcion_turno(primero) and turno_primero != previo
            ):
                violaciones.append({
                    'empleado':e,'tipo':'intra_semana','lunes':primero.get('lunes_semana'),
                    'fecha':primero['fecha'],'anterior':previo,'nuevo':turno_primero,
                    'mensaje':'El mes continúa una semana ya iniciada con otro turno.',
                })

        transiciones=set(e.get('transiciones_config') or [])
        for lunes, week_days in semanas.items():
            regulares=[
                d for d in sorted(week_days, key=lambda x:x['fecha'])
                if _turno_operativo_semanal(d) in {'AM','PM'} and not _es_excepcion_turno(d)
            ]
            # Un cambio de configuración con fecha de vigencia parte la semana
            # en dos tramos: lo que regía antes y lo que rige desde ese día.
            # Cada tramo se valida por separado; el salto entre ambos es la
            # decisión que el usuario tomó en «Asignaciones y ajustes».
            tramos=[[]]
            for d in regulares:
                if d['fecha'] in transiciones and tramos[-1]:
                    tramos.append([])
                tramos[-1].append(d)
            # Excepción autorizada: la cola de la semana que va justo después
            # del descanso puede adelantar el turno de la semana siguiente. Es
            # la forma de usar un descanso ya programado como puente PM→AM y
            # ahorrarse el administrativo. Se comprueba sobre los últimos días
            # del tramo final y, si califica, se retiran de la comprobación.
            ultimo = tramos[-1] if tramos else []
            for corte in range(1, len(ultimo)):
                cola = ultimo[corte:]
                if _adelanta_turno_tras_descanso(e, cola, lunes):
                    tramos[-1] = ultimo[:corte]
                    break
            for tramo in tramos:
                if not tramo:
                    continue
                turnos={d['turno'] for d in tramo}
                if len(turnos) > 1:
                    primero=tramo[0]
                    violaciones.append({
                        'empleado':e,'tipo':'intra_semana','lunes':lunes,
                        'fecha':primero['fecha'],'turnos':sorted(turnos),
                        'mensaje':'AM y PM aparecen dentro de la misma semana sin una excepción explícita.',
                    })
    return violaciones

_ORDINALES_ISO: dict[str, int] = {}

def _ordinal_iso(fecha_iso: str) -> int:
    """Ordinal de una fecha ISO con memoria.

    Las reparaciones consultan la misma fecha millones de veces por generación.
    Convertirla una sola vez reduce de forma decisiva el coste del motor sin
    cambiar ningún resultado.
    """
    valor = _ORDINALES_ISO.get(fecha_iso)
    if valor is None:
        try:
            valor = date.fromisoformat(fecha_iso).toordinal()
        except ValueError:
            valor = -1
        _ORDINALES_ISO[fecha_iso] = valor
    return valor

def _dias_ordenados(e: dict) -> list[tuple[int, dict, bool]]:
    """Jornadas del mes en curso, ordenadas y con el orden memorizado.

    Solo cambia el contenido de cada día, nunca su orden, así que basta con
    calcular la lista una vez por generación.
    """
    dias = e.get('dias') or []
    clave = id(e)
    entrada = _CACHE_SECUENCIA.get(clave)
    if entrada is not None and entrada[0] is e and entrada[1] is dias and entrada[2] == len(dias):
        return entrada[3]
    items = [(_ordinal_iso(str(d.get('fecha') or '')), d, False) for d in dias]
    items.sort(key=lambda x: x[0])
    _CACHE_SECUENCIA[clave] = (e, dias, len(dias), items)
    return items

def _secuencia_cronologica(e: dict, previo) -> list[tuple[int, dict, bool]]:
    """Días del empleado ordenados, con los del periodo anterior marcados.

    Las jornadas del periodo anterior se entregan como copias: pertenecen a un
    mes ya oficializado y ninguna reparación automática puede modificarlas. Se
    rehacen en cada consulta para que un intento de reparación descartado no
    quede recordado por error.
    """
    actuales = _dias_ordenados(e)
    if not previo:
        return actuales
    anteriores = previo if isinstance(previo, list) else [previo]
    marcados: list[tuple[int, dict, bool]] = []
    for x in anteriores:
        copia = dict(x)
        copia['_periodo_anterior'] = True
        marcados.append((_ordinal_iso(str(copia.get('fecha') or '')), copia, True))
    marcados.sort(key=lambda x: x[0])
    if marcados and actuales and marcados[-1][0] >= actuales[0][0]:
        combinada = marcados + actuales
        combinada.sort(key=lambda x: x[0])
        return combinada
    return marcados + actuales

def _violaciones_fatiga_laboral(
    horario: list[dict],
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
) -> list[dict]:
    """Detecta transiciones PM→AM sin una jornada puente aceptable.

    Regla V12.6:
    - D/VAC/INC/PER cortan la cadena porque son días no laborados.
    - ADM-GS/ADM-AC también cortan la cadena como *último recurso*
      administrativo autorizado por la operación (PM → ADM → AM).
    - CAP u otras jornadas trabajadas no cortan la cadena.
    - AM→PM no genera fatiga.

    Se incorpora, cuando existe, el último día del horario oficial anterior para
    detectar transiciones en el cambio de mes.
    """
    violaciones: list[dict] = []
    prev_map = dias_previos or {}
    for e in horario:
        if e.get('tipo_turno') == 'administrativo':
            continue
        eid = int(e.get('empleado_id') or 0)
        secuencia = _secuencia_cronologica(e, prev_map.get(eid))

        pm_pendiente: Optional[dict] = None
        intermedios: list[dict] = []
        for _orden, d, es_previo in secuencia:
            turno = str(d.get('turno') or '')
            if turno == 'PM':
                pm_pendiente = d
                intermedios = []
                continue
            if turno in FATIGUE_BREAK_CODES or turno in FATIGUE_ADMIN_CODES:
                pm_pendiente = None
                intermedios = []
                continue
            if turno == 'AM':
                # Las bases manuales se conservan tal como fueron recibidas.
                # Solo se exime una transición enteramente histórica; si el AM
                # o una jornada intermedia son nuevos, la regla sigue vigente.
                historica = pm_pendiente is not None and all(
                    str(x.get('origen') or '').startswith('base_')
                    for x in [pm_pendiente, *intermedios, d])
                if pm_pendiente is not None and not es_previo and not historica:
                    violaciones.append({
                        'empleado': e,
                        'tipo': 'fatiga_pm_am',
                        'fecha_pm': str(pm_pendiente.get('fecha') or ''),
                        'fecha_am': str(d.get('fecha') or ''),
                        'dia_pm': pm_pendiente,
                        'dia_am': d,
                        'intermedios': [str(x.get('fecha') or '') for x in intermedios],
                        'mensaje': 'Transición PM→AM sin descanso ni puente administrativo.',
                    })
                pm_pendiente = None
                intermedios = []
                continue
            # CAP y cualquier otra jornada/código no reconocido no constituyen
            # descanso ni el puente administrativo excepcional. Se conservan
            # para que el diagnóstico pueda explicar la secuencia real.
            if pm_pendiente is not None:
                intermedios.append(d)
    return violaciones

# Orígenes que representan una decisión explícita ya autorizada. El motor
# automático nunca los sobreescribe: una asignación directa, una solicitud
# aprobada o una modificación manual solo puede cambiarlas el usuario.
ORIGENES_DECISION_EXPLICITA = (
    'requerimiento:', 'solicitud:', 'ajuste_manual', 'preservado_parcial',
)

ORIGENES_INMOVIBLES_EXTRA = {
    'ultimo_viernes_administrativo', 'fuera_vigencia', 'reemplazo_aprobado',
    'intercambio_persona', 'intercambio_pareja', 'continuidad_semana_anterior',
}

def _origen_es_decision_explicita(origen: str) -> bool:
    texto = str(origen or '')
    return texto.startswith(ORIGENES_DECISION_EXPLICITA)

def _dia_liberable_por_reparacion(d: dict) -> bool:
    """Dice si una jornada puede convertirse en descanso por reparación automática.

    Un día del periodo anterior ya está oficializado y congelado. Un día fijado
    por una asignación, una solicitud aprobada o una modificación manual es una
    decisión del usuario que el motor no puede deshacer por su cuenta.
    """
    if d.get('_periodo_anterior'):
        # Copia de un mes ya oficializado: intocable.
        return False
    if d.get('turno') not in WORK_CODES:
        return False
    origen = str(d.get('origen') or '')
    if _origen_es_decision_explicita(origen) or origen in ORIGENES_INMOVIBLES_EXTRA:
        return False
    if d.get('bloqueado') and origen not in {
        'reajuste_cobertura_max_6', 'reajuste_cobertura_domingo', 'descanso_max_6_dias',
    }:
        return False
    return True

def _diagnostico_bloqueo_max7(tramo: list[dict], previos: Optional[list[bool]] = None) -> dict:
    """Explica por qué una racha de 8 jornadas no admite reubicación.

    Si ninguna de las ocho jornadas puede convertirse en descanso, no existe
    ninguna combinación de traslados capaz de cortarla: el conflicto es
    matemáticamente imposible dentro del periodo abierto y buscar más
    combinaciones solo consume tiempo.
    """
    marcas = previos if previos is not None else [False] * len(tramo)
    liberables: list[str] = []
    dias_liberables: list[dict] = []
    congelados: list[str] = []
    explicitos: list[str] = []
    requerimientos: set = set()
    solicitudes: set = set()
    # Una marca por día del tramo: si dejaran de coincidir, se estarían
    # leyendo días con la marca de otro.
    for d, es_previo in zip(tramo, marcas, strict=True):
        fecha = str(d.get('fecha') or '')
        if es_previo:
            congelados.append(fecha)
            continue
        origen = str(d.get('origen') or '')
        if _origen_es_decision_explicita(origen):
            explicitos.append(fecha)
            # El identificador puede faltar en datos históricos; el origen ya
            # dice de qué tipo de decisión se trata.
            if d.get('requerimiento_id'):
                requerimientos.add(int(d['requerimiento_id']))
            elif origen.startswith('requerimiento:'):
                requerimientos.add(fecha)
            if d.get('solicitud_id'):
                solicitudes.add(int(d['solicitud_id']))
            elif origen.startswith('solicitud:'):
                solicitudes.add(fecha)
        if _dia_liberable_por_reparacion(d):
            liberables.append(fecha)
            dias_liberables.append(d)
    return {
        'irreparable': not liberables,
        'fechas_liberables': liberables,
        'dias_liberables': dias_liberables,
        'fechas_periodo_anterior': congelados,
        'fechas_decision_explicita': explicitos,
        'requerimientos': sorted(str(x) for x in requerimientos),
        'solicitudes': sorted(str(x) for x in solicitudes),
    }

def _texto_max7(v: dict) -> str:
    return (
        f"{v['empleado']['nombre']} llegaría a 8 jornadas seguidas el {v['fecha']} "
        f"({', '.join(v['racha'])})"
    )

def _bloqueo_por_cobertura_max7(horario: list[dict], v: dict) -> Optional[dict]:
    """Comprueba si la racha no puede cortarse por cobertura mínima del área.

    Hay casos en los que la persona afectada no tiene ninguna jornada fijada por
    una decisión explícita, pero tampoco puede descansar: sus compañeros de área
    están ocupados por una asignación directa o una solicitud aprobada y, si ella
    descansa, el área se queda por debajo de la cobertura obligatoria. El
    conflicto existe, pero su causa está en esas decisiones autorizadas, no en el
    reparto automático.
    """
    empleado = v.get('empleado') or {}
    # Solo las jornadas del mes en curso que el motor podría convertir en
    # descanso. Las del periodo anterior llegan como copias congeladas.
    liberables = list((v.get('bloqueo') or {}).get('dias_liberables') or ())
    if not liberables:
        return None
    if any(_puede_descansar(horario, empleado, d) for d in liberables):
        return None
    fechas = {str(d.get('fecha') or '') for d in liberables}
    responsables: dict[str, set] = {}
    for otro in horario:
        if otro is empleado or otro.get('area') != empleado.get('area'):
            continue
        for d in otro.get('dias', ()):
            fecha = str(d.get('fecha') or '')
            if fecha not in fechas:
                continue
            if _origen_es_decision_explicita(str(d.get('origen') or '')):
                responsables.setdefault(str(otro.get('nombre') or ''), set()).add(fecha)
    if not responsables:
        return None
    return {
        'fechas': sorted(fechas),
        'responsables': {k: sorted(x) for k, x in responsables.items()},
    }

def clasificar_violacion_max7(v: dict, horario: Optional[list[dict]] = None) -> tuple[str, str]:
    """Decide si una racha de 8 jornadas es un error o una excepción autorizada.

    Cuando las ocho jornadas están fijadas por decisiones ya autorizadas —una
    asignación directa, una solicitud aprobada o un mes oficial anterior— no
    existe ninguna reubicación posible del descanso semanal. En ese caso el
    conflicto no se oculta ni bloquea el mes completo: queda registrado como
    excepción autorizada, visible en la validación y en el historial, para que
    el usuario decida si recorta la asignación o la mantiene.
    """
    bloqueo = v.get('bloqueo') or {}
    causas = []
    if bloqueo.get('requerimientos'):
        causas.append('una asignación directa vigente')
    if bloqueo.get('solicitudes'):
        causas.append('una solicitud aprobada')
    if bloqueo.get('fechas_periodo_anterior'):
        causas.append('jornadas del mes oficial anterior, que ya no pueden modificarse')
    autorizada = bool(
        bloqueo.get('requerimientos')
        or bloqueo.get('solicitudes')
        or bloqueo.get('fechas_decision_explicita')
        # Una racha que vive entera en el mes anterior ya publicado no se puede
        # deshacer desde aquí: pasa a ser una excepción visible en vez de un
        # error que impide generar. Ocurre, por ejemplo, al bajar el máximo de
        # jornadas seguidas: los días ya publicados se hicieron con el máximo
        # anterior y no cambian.
        or (bloqueo.get('fechas_periodo_anterior') and bloqueo.get('irreparable'))
    )
    if not autorizada and horario is not None:
        cobertura = _bloqueo_por_cobertura_max7(horario, v)
        if cobertura:
            quienes = ', '.join(
                f"{nombre} ({', '.join(fechas)})"
                for nombre, fechas in sorted(cobertura['responsables'].items())
            )
            return 'excepcion', (
                f"Excepción autorizada de máximo 7 días consecutivos: {_texto_max7(v)}. "
                "No queda ningún día donde ubicar su descanso semanal sin dejar el área por debajo de "
                f"la cobertura mínima, porque esas fechas están comprometidas por decisiones ya autorizadas: {quienes}. "
                "Para eliminarla, recorta esa asignación o solicitud, o amplía el personal disponible del área."
            )
    if not autorizada:
        # Nadie autorizó estas jornadas: sigue siendo un conflicto que el
        # usuario debe resolver antes de oficializar el mes.
        return 'error', (
            f"Máximo {maximo_dias_consecutivos()} días consecutivos: {_texto_max7(v)}. "
            "No existe una reubicación automática del descanso que reduzca el conflicto sin romper una regla superior."
        )
    if not causas:
        causas.append('decisiones fijadas manualmente')
    if bloqueo.get('irreparable'):
        detalle = (
            f"Todas esas jornadas están fijadas por {' y '.join(causas)}, "
            "así que no queda ningún día donde ubicar el descanso semanal."
        )
    else:
        detalle = (
            f"La racha nace de {' y '.join(causas)}. "
            "El motor intentó reubicar el descanso semanal en cada día disponible, pero cualquier traslado "
            "dejaría el área sin la cobertura mínima obligatoria."
        )
    return 'excepcion', (
        f"Excepción autorizada de máximo 7 días consecutivos: {_texto_max7(v)}. "
        f"{detalle} "
        "Para eliminarla, recorta la asignación o la solicitud que ocupa uno de esos días, "
        "o amplía el personal disponible del área."
    )

def _violaciones_max_dias_consecutivos(
    horario: list[dict],
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
    detallado: bool = False,
) -> list[dict]:
    """Detecta una octava jornada consecutiva, incluso al cruzar de mes.

    ``detallado`` añade el diagnóstico de bloqueo de la racha. Solo lo necesitan
    la clasificación final y el filtro de reparaciones; los bucles internos que
    únicamente cuentan conflictos lo omiten para no pagar ese coste.
    """
    out: list[dict] = []
    prev_map = dias_previos or {}
    limite = maximo_dias_consecutivos() + 1
    for e in horario:
        eid = int(e.get('empleado_id') or 0)
        secuencia = _secuencia_cronologica(e, prev_map.get(eid))
        racha: list[dict] = []
        marcas: list[bool] = []
        ultimo_ord = None
        for orden, d, es_previo in secuencia:
            if orden < 0:
                continue
            if ultimo_ord is not None and orden != ultimo_ord + 1:
                racha = []
                marcas = []
            ultimo_ord = orden
            if d.get('turno') in WORK_CODES:
                racha.append(d)
                marcas.append(es_previo)
                if len(racha) >= limite and not es_previo:
                    tramo = racha[-limite:]
                    if all(str(x.get('origen') or '').startswith('base_') for x in tramo):
                        # No corregir el pasado. Se conserva la racha para que
                        # extenderla con una jornada nueva sí se compruebe.
                        continue
                    violacion = {
                        'empleado': e, 'dia': d, 'fecha': str(d.get('fecha') or ''),
                        'racha': [str(x.get('fecha') or '') for x in racha[-7:]],
                    }
                    if detallado:
                        violacion['tramo'] = tramo
                        violacion['bloqueo'] = _diagnostico_bloqueo_max7(
                            tramo, marcas[-limite:]
                        )
                    out.append(violacion)
            else:
                racha = []
                marcas = []
    return out

def _habilitar_descanso_con_reajuste_cobertura(
    horario: list[dict], e: dict, d: dict, motivo: str = 'máximo 7 días',
) -> tuple[bool, Optional[dict]]:
    """Intenta liberar cobertura para que ``e`` pueda descansar ese día.

    Si el descanso por sí solo deja un hueco, mueve temporalmente a otra persona
    flexible del área al turno que se necesita. Es lo que permite que, con un
    reparto de 2 AM + 1 PM, la persona que ese día cubre PM pueda descansar: otra
    del área pasa de AM a PM esa jornada. El reajuste queda identificado y se
    vuelve a validar después por fatiga, pareja y cobertura.
    """
    if _puede_descansar(horario,e,d):
        return True, None
    turno=d.get('turno')
    if turno not in {'AM','PM'}:
        return False, None
    for otra in horario:
        if otra is e or otra.get('area')!=e.get('area') or otra.get('tipo_turno')=='administrativo':
            continue
        od=_dia(otra,d['fecha'])
        if not od or (od.get('bloqueado') and od.get('origen') not in {'reajuste_cobertura_max_6','descanso_max_6_dias'}) or od.get('turno') not in {'AM','PM'} or od.get('turno')==turno:
            continue
        if _conflicto_pareja_para_turno(horario,otra,d['fecha'],turno):
            continue
        if not cobertura_valida_si_cambia(horario,otra,od,turno):
            continue
        snap=_snapshot_dia(od)
        anterior=od.get('turno')
        od.update(
            turno=turno, origen='reajuste_cobertura_max_6', bloqueado=True,
            observacion=f'Reajuste de cobertura para permitir el descanso por {motivo}: {anterior} → {turno}',
            cobertura_operativa=None, turno_operativo_origen=anterior,
        )
        if _puede_descansar(horario,e,d):
            return True, {'persona':otra.get('nombre'),'fecha':d['fecha'],'antes':anterior,'despues':turno}
        _restore_snapshot(od,snap)
    return False, None

def es_dia_del_mes(d: dict) -> bool:
    """¿El día pertenece al mes natural, o solo completa la semana?"""
    return bool(d.get('mes_propio', True))


def _turnos_cobertura_dia(d: dict) -> set[str]:
    """Turnos operativos que una casilla cubre a efectos de dotación mínima.

    Delega en el dominio, que es donde está escrito qué cubre cada código:
    ADM-GS conserva la franja que la persona tenía, ADM-AC no cubre nada.
    Se pasa una persona vacía a propósito: aquí solo se pregunta por el código,
    y los días de cobertura de cada cual los mira `_cuenta_como_cobertura`.
    """
    franja = _cobertura.franja_cubierta({}, d)
    return {franja} if franja else set()



def _conteo_turno(horario: list[dict], area: str, fecha_iso: str, turno: str,
                  excluir: Optional[int] = None) -> int:
    cuenta = _cobertura.conteo(horario, area, fecha_iso, excluir)
    return cuenta.am if turno == 'AM' else cuenta.pm


def cobertura_valida_si_cambia(
    horario: list[dict], e: dict, d: dict, nuevo_turno: str,
    respetar_maximo: bool = True,
) -> bool:
    """¿El área conserva su cobertura si esa persona pasa a ese turno?

    ``respetar_maximo`` distingue las dos naturalezas de la regla. El **suelo**
    es una obligación operativa y no se salta nunca: un turno sin nadie es un
    turno sin nadie. El **techo** es una política de reparto, y una asignación
    o una excepción decidida en «Asignaciones y ajustes» está por encima de
    ella: el usuario ya dijo que ese día quiere a esa persona en ese turno.
    """
    area=e['area']
    fecha=d['fecha']
    actual_cobertura = _turnos_cobertura_dia(d)

    def cobertura_nueva() -> set[str]:
        # Recibía un parámetro que no llegaba a mirar: usaba `nuevo_turno` del
        # ámbito de fuera. Leerla hacía pensar que servía para varios turnos.
        if nuevo_turno in {'AM', 'PM'}:
            return {nuevo_turno}
        if nuevo_turno == 'ADM-GS':
            # Igual que en `_turnos_cobertura_dia`: la jornada administrativa
            # conserva el turno que la persona tenía ese día.
            return _turnos_cobertura_dia({**d, 'turno': 'ADM-GS'})
        return set()

    nueva_cobertura = cobertura_nueva()

    # Simula retirar la cobertura actual y agregar la nueva.
    def despues(turno):
        base=_conteo_turno(horario,area,fecha,turno)
        if turno in actual_cobertura:
            base-=1
        if turno in nueva_cobertura:
            base+=1
        return base
    if despues('AM') < minimo_cobertura(horario, area, 'AM', fecha):
        return False
    if despues('PM') < minimo_cobertura(horario, area, 'PM', fecha):
        return False
    # Y tampoco al revés: un reajuste no puede amontonar en una franja más
    # personas de las que el área admite. Solo se comprueba el turno al que se
    # mueve a alguien; el otro únicamente pierde gente.
    for turno in ('AM', 'PM') if respetar_maximo else ():
        if turno not in nueva_cobertura:
            continue
        tope = maximo_cobertura(horario, area, turno, fecha)
        if tope is not None and despues(turno) > tope:
            return False
    # Además del suelo de cada turno, el área tiene su propio suelo de personas.
    # En Comunicaciones y en Atención al Ciudadano es el único que manda: da
    # igual el turno, lo que no puede es quedarse sin nadie.
    operaba = bool(actual_cobertura & {'AM', 'PM'})
    operara = bool(nueva_cobertura & {'AM', 'PM'})
    if operaba and not operara:
        total = _conteo_area(horario, area, fecha) - 1
        if total < minimo_area_cobertura(horario, area, fecha):
            return False
    return True

def _conflicto_pareja_para_turno(horario: list[dict], e: dict, fecha: str, turno: str) -> bool:
    pareja = _fila(horario, e.get('pareja_id')) if e.get('pareja_id') else None
    if not pareja:
        return False
    dp = _dia(pareja, fecha)
    return bool(dp and dp.get('turno') == turno)

def _semanas(e:dict) -> dict[str,list[dict]]:
    g=defaultdict(list)
    for d in e['dias']:
        g[d['lunes_semana']].append(d)
    return dict(sorted(g.items()))

AUSENCIAS_APROBADAS = {'VAC', 'INC', 'PER'}

def _semana_sin_jornada(dias) -> bool:
    """¿La persona no trabaja ni un día de esta semana?

    Cuando la semana entera está cubierta por ausencias aprobadas no hay dónde
    colocar el descanso semanal ni a quién dárselo: no se exige.
    """
    return not any(
        d.get('turno') not in AUSENCIAS_APROBADAS
        for d in dias
        if d.get('vigente', True) and d.get('turno') != OUT_OF_VIGENCY_CODE
    )

def _es_descanso_semanal(d: dict) -> bool:
    """Día que satisface el descanso semanal ordinario.

    Un festivo es siempre un concepto separado: aunque coincida con D, VAC,
    INC o PER, esa fecha no sustituye el descanso semanal ordinario. Esto evita
    que una reparación de máximo 6 convierta accidentalmente un festivo en el
    único descanso de la semana.

    El permiso tampoco cuenta. Vacaciones e incapacidad son días de reposo y
    cubren el descanso de esa semana; un permiso es una diligencia personal, así
    que quien pide un permiso el martes sigue teniendo derecho a su descanso en
    otro día. Antes el permiso ocupaba ese sitio y la persona acababa
    trabajando seis días seguidos sin librar de verdad.
    """
    if d.get('es_festivo'):
        return False
    if d.get('turno') == 'PER':
        return False
    if d.get('turno') in {'VAC', 'INC'}:
        return True
    if d.get('turno') != 'D':
        return False
    return d.get('origen') not in {
        'descanso_festivo',
        'compensatorio_festivo',
        'descanso_extra_solicitado',
        'descanso_extra_directo',
    }

def _cuenta_descansos_semanales(e: dict, lunes: str) -> int:
    """Descansos semanales ordinarios que tiene la persona esa semana."""
    return sum(
        1 for x in e.get('dias', ())
        if str(x.get('lunes_semana') or _lunes_iso_de_dia(x)) == lunes and _es_descanso_semanal(x)
    )

def _historial_semana(
    historial: Optional[dict[int, dict[str, set[int]]]],
    e: dict,
    lunes_iso: str,
) -> set[int]:
    if not historial:
        return set()
    return set(historial.get(int(e['empleado_id']), {}).get(str(lunes_iso), set()))

def _puede_descansar(horario:list[dict], e:dict, d:dict) -> bool:
    if d['turno'] not in {'AM','PM'}:
        return False
    # Un día bloqueado no se toca, con una excepción: la asignación que solo
    # fija el turno (AM o PM) deja abierta la posibilidad del descanso semanal.
    if d['bloqueado'] and not d.get('descanso_permitido'):
        return False
    return cobertura_valida_si_cambia(horario,e,d,'D')

def _lunes_iso_de_dia(d: dict) -> str:
    if d.get('lunes_semana'):
        return str(d['lunes_semana'])
    f = date.fromisoformat(d['fecha'])
    return (f - timedelta(days=f.weekday())).isoformat()

def _asignar_d(d:dict, origen:str, obs:str):
    motivos={
        'descanso_automatico':'distribucion_normal',
        'descanso_fijo':'descanso_fijo',
        'descanso_max_6_dias':'maximo_7',
        'descanso_fatiga_laboral':'fatiga',
        'descanso_domingo':'domingo',
        'descanso_domingo_reubicado':'domingo',
        'descanso_solicitado':'solicitud',
        'descanso_reubicado_manual':'solicitud',
        'descanso_fijo_reubicado_manual':'solicitud',
        'descanso_fijo_reubicado_actividad':'cobertura',
    }
    payload={'turno':'D','origen':origen,'bloqueado':True,'observacion':obs}
    if origen in motivos:
        payload['origen_descanso']='descanso_semanal'
        payload['motivo_descanso']=motivos[origen]
    d.update(**payload)

# Los días que solo completan la semana (el lunes que viene del mes anterior y
# la cola que entra en el siguiente) se muestran y se tienen en cuenta para las
# reglas semanales, pero no cuentan como domingos, festivos ni horas del mes:
# esos totales hablan del mes natural.
def _dias_del_mes(horario: list[dict]) -> list[dict]:
    if not horario:
        return []
    return [d for d in horario[0]['dias'] if es_dia_del_mes(d)]

def fechas_domingos(horario: list[dict]) -> list[str]:
    return [d['fecha'] for d in _dias_del_mes(horario) if d['es_domingo']]

def fechas_festivos(horario: list[dict]) -> list[str]:
    return [d['fecha'] for d in _dias_del_mes(horario) if d['es_festivo']]

def _snapshot_dia(d: dict) -> dict:
    keys = (
        'turno', 'turno_original', 'origen', 'bloqueado', 'observacion', 'solicitud_id',
        'reemplaza_a', 'reemplazado_por', 'capacitacion_horas',
        'cobertura_operativa', 'turno_operativo_origen', 'festivo_origen', 'requerimiento_id',
        'fatiga_desde', 'fatiga_hacia', 'origen_descanso', 'motivo_descanso',
        'descanso_permitido',
    )
    return {k: d.get(k) for k in keys}

def _restore_snapshot(d: dict, snapshot: dict) -> None:
    d.update(snapshot)
