# -*- coding: utf-8 -*-
"""Las cinco etapas, en orden, y lo que se le ofrece al resto del programa.

Este módulo no calcula: llama a las etapas en el orden que toca y junta
el resultado. Si alguna vez hay que entender de dónde sale un mes,
se empieza a leer aquí.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from typing import Optional

# Reglas particulares sobre personas concretas. No tienen pantalla ni ruta:
# ver la cabecera de `backend/reglas_internas.py`.
from gestor.dominio import internas as reglas_internas

# Cómo se le cuenta a una persona un aviso de validación vive en su propio
# módulo: son ciento catorce líneas de texto que no dependen del horario.
from gestor.dominio.avisos import legible as _validacion_legible
from gestor.dominio.calendario import rango
from gestor.dominio.rotacion import validar_parejas
from gestor.motor.balance import (  # noqa: F401
    asignar_balance_especiales,
    asignar_descanso_semanal,
    repartir_domingos_continuidad,
)
from gestor.motor.comun import (  # noqa: F401
    _conteo_turno,
    _dia,
    _dias_del_mes,
    _puede_descansar,
    _turnos_cobertura_dia,
    es_dia_del_mes,
    fechas_domingos,
    fechas_festivos,
    maximo_dias_consecutivos,
)
from gestor.motor.construccion import (  # noqa: F401
    alinear_semanas_heredadas,
    aplicar_descansos_fijos,
    aplicar_dias_heredados,
    aplicar_ultimo_viernes_administrativo,
    construir_base,
)
from gestor.motor.decisiones import (  # noqa: F401
    aplicar_ajustes_manuales,
    aplicar_reemplazos,
    aplicar_requerimientos_directos,
    aplicar_solicitudes_previas,
    reubicar_descanso_fijo_por_actividad,
    reubicar_descanso_retirado_manualmente,
)
from gestor.motor.presupuesto import (
    presupuesto_agotado,
    presupuesto_busqueda,
)
from gestor.motor.reparacion import (  # noqa: F401
    _asegurar_cobertura_minima,
    limpiar_puentes_fatiga_obsoletos,
    reparar_balance_domingos_post_reglas,
    reparar_cambio_semanal,
    reparar_cobertura_adm_gs,
    reparar_cobertura_minima,
    reparar_fatiga_laboral,
    reparar_max_dias_consecutivos,
)
from gestor.motor.validacion import (  # noqa: F401
    validar_horario,
)
from gestor.motor.vocabulario import (  # noqa: F401
    _BALANCE_DOMINICAL_FLEXIBLE,
    _CACHE_ORDEN_FIRMA,
    _CACHE_SECUENCIA,
    _LIMITE_RACHA,
    DOMINGOS_MITAD_EXACTA,
    MAX_DIAS_CONSECUTIVOS,
    NONWORK_CODES,
    WORK_CODES,
)


@contextmanager
def balance_dominical_flexible(activo: bool = True):
    """Convierte el reparto dominical en aviso en vez de en error.

    Solo se usa como último recurso: primero se busca un reparto que lo cumpla
    y, si después de explorar no aparece ninguno, se vuelve a generar con esto
    puesto para no dejar el mes sin horario.
    """
    testigo = _BALANCE_DOMINICAL_FLEXIBLE.set(bool(activo))
    try:
        yield
    finally:
        _BALANCE_DOMINICAL_FLEXIBLE.reset(testigo)

@contextmanager
def limite_racha(valor: Optional[int]):
    """Fija el tope de jornadas seguidas mientras se genera un periodo."""
    if not valor:
        yield int(MAX_DIAS_CONSECUTIVOS)
        return
    testigo = _LIMITE_RACHA.set(int(valor))
    try:
        yield int(valor)
    finally:
        _LIMITE_RACHA.reset(testigo)

def limpiar_caches_generacion() -> None:
    """Vacía las memorias de orden entre generaciones independientes."""
    _CACHE_SECUENCIA.clear()
    _CACHE_ORDEN_FIRMA.clear()

def _asegurar_cobertura_pm_comunicaciones(horario: list[dict], fechas: list[str]) -> bool:
    """Compatibilidad: solo comprueba la cobertura PM de Comunicaciones."""
    if not horario or str(horario[0].get('area') or '') != 'comunicaciones':
        return True
    return _asegurar_cobertura_minima(horario, fechas)

def _habitualidad(
    e: dict,
    d: dict,
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
) -> bool:
    """Compatibilidad interna V13.

    Repetir el mismo día de descanso durante varias semanas es válido.
    Esta función se conserva únicamente para compatibilidad con llamadas
    históricas del motor y ya no limita ni pondera la planificación.
    """
    return False

def fechas_especiales(horario:list[dict]) -> list[str]:
    # Compatibilidad para estadísticas: unión de domingos y festivos.
    return sorted({
        d['fecha'] for d in _dias_del_mes(horario)
        if d['es_domingo'] or d['es_festivo']
    })

def objetivo_especiales(horario:list[dict]) -> int:
    # Se conserva para exportadores antiguos; desde V10.5 el balance real se
    # calcula por separado para domingos y festivos.
    return len(fechas_domingos(horario)) // 2

def _violaciones_habitualidad(
    e: dict,
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
) -> list[dict]:
    """V13: no existe validación por repetición del mismo día de descanso."""
    return []

def horas_dia(d:dict) -> float:
    """Horas efectivas del día para los totales informativos.

    AM/PM aportan 7 h efectivas. Cualquier jornada administrativa usa el
    horario administrativo guía ADM-GS: 7 h cualquier día (7:30–15:30 con
    una hora de descanso). Estas diferencias se muestran en los totales, pero nunca se usan
    para crear descansos ni invalidar una programación.
    """
    if d['turno'] in {'AM','PM'}:
        return 7.0
    if d['turno'] in {'ADM-GS','ADM-AC'}:
        return 7.0 if d['turno'] == 'ADM-GS' else (4.5 if d.get('es_sabado') else 7.5)
    if d['turno']=='CAP':
        return float(d.get('capacitacion_horas') or 0)
    return 0.0

def estadisticas(horario:list[dict]) -> list[dict]:
    if not horario:
        return []
    out=[]
    # Los totales mensuales solo miran los días del mes natural. Los días que
    # completan la primera y la última semana se siguen viendo en el horario y
    # cuentan para las reglas semanales, pero no inflan las horas del mes ni el
    # reparto de domingos: pertenecen al mes vecino.
    domingos=[d['fecha'] for d in horario[0]['dias'] if d['es_domingo'] and es_dia_del_mes(d)]
    festivos=[d['fecha'] for d in horario[0]['dias'] if d['es_festivo'] and es_dia_del_mes(d)]
    especiales=fechas_especiales(horario)
    for e in horario:
        propios=[d for d in e['dias'] if es_dia_del_mes(d)]
        incumpl=0
        if e.get('descanso_fijo') is not None:
            incumpl=sum(1 for d in propios if d.get('vigente', True) and d['dia_semana_numero']==e['descanso_fijo'] and d['turno'] not in {'D','VAC','INC','PER'} and not (d.get('origen') in {'requerimiento:actividad','requerimiento:asignacion_administrativa','ultimo_viernes_administrativo','ajuste_manual'} and any(x.get('lunes_semana')==d.get('lunes_semana') and x.get('turno')=='D' and x.get('origen') in {'descanso_fijo_reubicado_actividad','descanso_fijo_reubicado_manual'} for x in e['dias'])))
        domingos_vigentes=[f for f in domingos if (dia:=_dia(e,f)) and dia.get('vigente', True)]
        festivos_vigentes=[f for f in festivos if (dia:=_dia(e,f)) and dia.get('vigente', True)]
        especiales_vigentes=[f for f in especiales if (dia:=_dia(e,f)) and dia.get('vigente', True)]
        dom=sum(1 for f in domingos_vigentes if _dia(e,f)['turno'] in WORK_CODES)
        fes=sum(1 for f in festivos_vigentes if _dia(e,f)['turno'] in WORK_CODES)
        especiales_trabajados=sum(1 for f in especiales_vigentes if _dia(e,f)['turno'] in WORK_CODES)
        objetivo=len(domingos_vigentes)//2
        max_objetivo = objetivo + (0 if DOMINGOS_MITAD_EXACTA else len(domingos_vigentes) % 2)
        exento_dom = e['tipo_turno']=='administrativo' or e.get('descanso_fijo') is not None or e.get('exento_especiales')
        if exento_dom:
            limite='EXENTO'
            control='EXENTO'
        else:
            limite=objetivo if objetivo == max_objetivo else f'{objetivo}-{max_objetivo}'
            control='CUMPLE' if objetivo <= dom <= max_objetivo else 'REVISAR'
        control_desc='NO APLICA' if e.get('descanso_fijo') is None else ('CUMPLE' if incumpl==0 else 'INCUMPLE')
        out.append({
            'empleado_id':e['empleado_id'],'nombre':e['nombre'],'area':e['area'],
            'horas_mes':round(sum(horas_dia(d) for d in propios),1),
            'horas_periodo':round(sum(horas_dia(d) for d in e['dias']),1),
            'dias_trabajados':sum(1 for d in propios if d['turno'] in WORK_CODES),
            'domingos_trabajados':dom,'festivos_trabajados':fes,'especiales_trabajados':especiales_trabajados,
            'limite_domingos':limite,'objetivo_especiales':limite,'control_domingos':control,'control_especiales':control,'incumpl_descanso_fijo':incumpl,'control_descanso':control_desc,
            'turnos_am':sum(1 for d in propios if d['turno']=='AM'),
            'turnos_pm':sum(1 for d in propios if d['turno']=='PM'),
            'descansos':sum(1 for d in propios if d['turno']=='D'),
            'compensatorios_festivos':sum(1 for d in propios if d.get('origen')=='compensatorio_festivo' and d.get('turno')=='D'),
            'descansos_extra':sum(1 for d in propios if d.get('origen') in {'descanso_extra_solicitado','descanso_extra_directo'} and d.get('turno')=='D'),
            'horas_capacitacion':round(sum(float(d.get('capacitacion_horas') or 0) for d in propios),1),
        })
    return out

def _cambios_aplicados(horario: list[dict]) -> list[dict]:
    """Describe cambios exitosos para que Validación explique exactamente qué hizo."""
    nombres_dia = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
    out: list[dict] = []
    vistos: set[tuple] = set()

    for e in horario:
        for d in e.get('dias', []):
            origen = str(d.get('origen') or '')
            if origen == 'descanso_solicitado':
                key = ('descanso', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                antes = d.get('turno_original') or 'turno base'
                out.append({
                    'categoria': 'Solicitud aplicada · Mover descanso',
                    'mensaje': (
                        f"{e['nombre']}: el descanso de la semana del {d.get('lunes_semana')} quedó fijado el "
                        f"{nombres_dia[int(d['dia_semana_numero'])]} {d['fecha']}. Ese día pasó de {antes} a D. "
                        'No se asignará otro descanso ordinario en esa semana.'
                    ),
                    'sugerencia': 'Si necesitas otro día, edita la solicitud y elige otra fecha dentro de la misma semana; después vuelve a generar.',
                })
            elif origen == 'solicitud:turno_dia':
                key = ('turno', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                antes = d.get('turno_original') or 'turno base'
                out.append({
                    'categoria': 'Solicitud aplicada · Cambio de turno',
                    'mensaje': f"{e['nombre']}: el {d['fecha']} cambió de {antes} a {d['turno']}. El resto de la rotación permanece intacto.",
                    'sugerencia': 'Si el cambio no era el esperado, edita o elimina esa solicitud y vuelve a generar las alternativas.',
                })
            elif origen == 'solicitud:turno_semanas':
                key = ('turno_semanas', e['empleado_id'], d.get('solicitud_id'))
                if key in vistos:
                    continue
                vistos.add(key)
                dias = [x for x in e.get('dias', []) if x.get('solicitud_id') == d.get('solicitud_id')]
                if dias:
                    out.append({
                        'categoria': 'Solicitud aplicada · Cambio temporal por semanas',
                        'mensaje': f"{e['nombre']}: desde {dias[0]['fecha']} hasta {dias[-1]['fecha']} se aplicó temporalmente {d['turno']}. Fuera de ese rango conserva su programación normal.",
                        'sugerencia': 'Para modificar otra etapa futura, crea otra solicitud por semanas; no es necesario cambiar la base permanente del empleado.',
                    })
            elif origen == 'requerimiento:excepcion_turno':
                key = ('excepcion_turno', e['empleado_id'], d.get('requerimiento_id'), d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                out.append({
                    'categoria': 'Asignación directa · Excepción de turno',
                    'mensaje': f"{e['nombre']}: el {d['fecha']} quedó excepcionalmente en {d['turno']}. Esta fecha no aplica la regla de consistencia semanal AM/PM.",
                    'sugerencia': 'La excepción solo afecta las fechas registradas. Cobertura, pareja de PC, descansos fijos y ausencias siguen siendo obligatorios.',
                })
            elif origen == 'ajuste_manual':
                key = ('manual', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                antes = d.get('turno_original') or 'turno base'
                out.append({
                    'categoria': 'Modificación manual asistida',
                    'mensaje': f"{e['nombre']}: el {d['fecha']} quedó en {d['turno']} mediante edición manual asistida (base: {antes}).",
                    'sugerencia': 'El ajuste fue validado con las reglas generales. Si necesitas cambiarlo, vuelve a Modificar horario y genera nuevas alternativas.',
                })
            elif origen == 'descanso_extra_solicitado':
                key = ('extra', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                out.append({
                    'categoria': 'Solicitud aplicada · Descanso extra',
                    'mensaje': f"{e['nombre']}: se añadió un descanso extra el {d['fecha']}. Este D es adicional y no reemplaza el descanso semanal ni el compensatorio de un festivo.",
                    'sugerencia': 'Si deja de ser necesario, elimina la solicitud y vuelve a generar las alternativas.',
                })
            elif origen == 'compensatorio_festivo':
                key = ('comp_festivo', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                out.append({
                    'categoria': 'Ajuste automático · Compensatorio de festivo',
                    'mensaje': f"{e['nombre']}: el {d['fecha']} quedó como D compensatorio por el festivo trabajado {d.get('festivo_origen')}.",
                    'sugerencia': 'El compensatorio es adicional al descanso semanal. Si necesitas otra fecha, usa una solicitud de descanso extra o ajusta solicitudes existentes y vuelve a generar.',
                })
            elif origen == 'solicitud:adm_gs':
                key = ('admgs', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                cobertura = ', '.join(sorted(_turnos_cobertura_dia(d))) or 'ninguna'
                out.append({
                    'categoria': 'Solicitud aplicada · ADM-GS',
                    'mensaje': f"{e['nombre']}: el {d['fecha']} quedó como ADM-GS (Administrativo Guía Social) y cuenta como cobertura {cobertura}.",
                    'sugerencia': 'ADM-GS conserva el turno que la persona tenía ese día: si iba a estar en AM cuenta como AM, y si iba a estar en PM cuenta como PM. Para liberar esa cobertura, marca el reemplazo en la asignación y otra persona la garantiza.',
                })
            elif origen == 'reajuste_cobertura_adm_gs':
                key = ('reajuste_admgs', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                out.append({
                    'categoria': 'Ajuste automático · Cobertura ADM-GS',
                    'mensaje': f"{e['nombre']}: el {d['fecha']} fue reajustado a {d['turno']} para mantener mínimo 1 AM y 1 PM después de una asignación ADM-GS.",
                    'sugerencia': 'El reajuste solo se hace cuando es necesario para conservar cobertura. Si prefieres otra distribución, usa Modificar horario y fija manualmente la alternativa deseada.',
                })
            elif origen == 'reemplazo_aprobado':
                key = ('reemplazo', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                out.append({
                    'categoria': 'Solicitud aplicada · Reemplazo',
                    'mensaje': f"{e['nombre']}: el {d['fecha']} quedó en {d['turno']} como reemplazo. {d.get('observacion') or ''}".strip(),
                    'sugerencia': 'El reemplazo solo afecta ese día y no hace doble turno. Si no corresponde, selecciona otra persona en la solicitud.',
                })
            elif origen in {'intercambio_persona', 'intercambio_pareja'}:
                key = ('intercambio', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                out.append({
                    'categoria': 'Solicitud aplicada · Intercambio',
                    'mensaje': f"{e['nombre']}: el {d['fecha']} quedó en {d['turno']}. {d.get('observacion') or ''}".strip(),
                    'sugerencia': 'El intercambio solo modifica la fecha aprobada y conserva la programación normal de los demás días.',
                })
            elif origen == 'descanso_fatiga_laboral':
                key = ('fatiga_d', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                out.append({
                    'categoria': 'Ajuste automático · Fatiga laboral',
                    'mensaje': f"{e['nombre']}: el descanso semanal que ya tenía fue trasladado al {d['fecha']} para evitar una transición directa PM→AM desde {d.get('fatiga_desde') or 'la jornada anterior'}.",
                    'sugerencia': 'La fatiga nunca crea un descanso extra. Solo traslada el descanso semanal automático existente; si no puede trasladarse, el motor intenta PM → ADM → AM.',
                })
            elif origen == 'puente_fatiga_administrativo':
                key = ('fatiga_adm', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                out.append({
                    'categoria': 'Ajuste automático · Puente administrativo por fatiga',
                    'mensaje': f"{e['nombre']}: el {d['fecha']} quedó en {d['turno']} porque no había un descanso semanal existente que pudiera trasladarse de forma válida; evita PM→AM directo.",
                    'sugerencia': 'El puente administrativo es la última alternativa automática y no añade descansos. Si quieres otra solución, modifica manualmente la secuencia y revisa el diagnóstico.',
                })
            elif d.get('turno') == 'D' and 'reubicado desde' in str(d.get('observacion') or '').lower():
                key = ('auto_reubicado', e['empleado_id'], d['fecha'])
                if key in vistos:
                    continue
                vistos.add(key)
                out.append({
                    'categoria': 'Ajuste automático · Descanso',
                    'mensaje': f"{e['nombre']}: {d.get('observacion')}",
                    'sugerencia': 'El descanso fue reubicado automáticamente por una regla operativa. Si prefieres otro día, crea una solicitud de Mover descanso para esa semana.',
                })

    return out

def _es_error_forzable_manual(mensaje: str) -> bool:
    """Toda regla operativa del horario puede autorizarse manualmente.

    Las validaciones técnicas (persona/fecha/código inexistente) se detectan antes
    de llegar a esta etapa y no se convierten en excepciones.
    """
    texto=str(mensaje or '').lower()
    tecnicos=('código inválido','no existe el empleado','fecha inválida')
    return not any(x in texto for x in tecnicos)

def _error_relacionado_con_ajuste_manual(
    mensaje: str,
    horario: list[dict],
    ajustes: Optional[list[dict]],
) -> bool:
    """Evita que el modo forzado convierta en excepción errores ajenos al cambio."""
    manuales = [a for a in (ajustes or []) if not bool(a.get('preservar'))]
    if not manuales:
        return False
    texto = str(mensaje).lower()
    por_id = {int(e['empleado_id']): e for e in horario or []}
    for a in manuales:
        fecha = str(a.get('fecha') or '')
        if fecha and fecha in texto:
            return True
        try:
            lunes = (date.fromisoformat(fecha) - timedelta(days=date.fromisoformat(fecha).weekday())).isoformat()
        except Exception:                                          # noqa: BLE001
            lunes = ''          # la fecha no se pudo leer: no hay semana que comparar
        if lunes and lunes in texto:
            return True
        e = por_id.get(int(a.get('empleado_id') or 0))
        if e and str(e.get('nombre') or '').lower() in texto:
            return True
    return False

def _nota_horas_reales() -> str:
    return (
        'Las horas son informativas y reflejan la jornada realmente programada. '
        'Una semana ordinaria suele sumar 42 h; una jornada administrativa puede '
        'aportar 0.5 h adicional y un descanso compensatorio, festivo o ausencia '
        'autorizada puede reducir el total. Estas diferencias no son un conflicto '
        'y nunca generan descansos automáticos.'
    )

def generar_horario_completo(
    empleados:list[dict], solicitudes:list[dict], mes:int, anio:int,
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
    historial_no_laborados: Optional[dict[int, dict[str, set[int]]]] = None,
    historial_descansos_especiales: Optional[dict[int, dict[str, set[int]]]] = None,
    variante: int = 0,
    ajustes_manuales: Optional[list[dict]] = None,
    requerimientos: Optional[list[dict]] = None,
    permitir_excepciones_cobertura_manual: bool = False,
    turnos_previos: Optional[dict[int, str]] = None,
    dias_previos_fatiga: Optional[dict[int, dict | list[dict]]] = None,
    dias_heredados: Optional[dict[int, dict[str, dict]]] = None,
    max_dias_consecutivos: Optional[int] = None,
    aplicar_reglas_internas: bool = True,
) -> dict:
    """Construye la programación de un periodo completo.

    ``max_dias_consecutivos`` fija el tope de jornadas seguidas para **esta**
    generación. Sin él se toma el que esté configurado en la aplicación para el
    primer día del periodo, de modo que un mes ya publicado conserva la política
    con la que se hizo aunque después se cambie.
    """
    if max_dias_consecutivos is None:
        try:
            from gestor.servicios.reglas_operacion import maximo_dias
            max_dias_consecutivos = maximo_dias(rango(mes, anio)[0])
        except Exception:                                          # noqa: BLE001
            # Si no se puede leer la regla configurada se usa la de fábrica,
            # pero **se apunta**. Es el mismo silencio que hacía que el Excel
            # imprimiera «máximo 7 jornadas» con la regla puesta en 10: nadie
            # podía enterarse de que el número no era el suyo.
            from gestor.registro import obtener as _registro
            _registro().exception(
                'no se pudo leer el máximo de jornadas seguidas; se usa el de fábrica')
            max_dias_consecutivos = None
    with limite_racha(max_dias_consecutivos):
        return _generar_horario_completo(
            empleados, solicitudes, mes, anio,
            historial_descansos, historial_no_laborados, historial_descansos_especiales,
            variante, ajustes_manuales, requerimientos,
            permitir_excepciones_cobertura_manual, turnos_previos,
            dias_previos_fatiga, dias_heredados,
            aplicar_reglas_internas=aplicar_reglas_internas,
        )

def _generar_horario_completo(
    empleados:list[dict], solicitudes:list[dict], mes:int, anio:int,
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
    historial_no_laborados: Optional[dict[int, dict[str, set[int]]]] = None,
    historial_descansos_especiales: Optional[dict[int, dict[str, set[int]]]] = None,
    variante: int = 0,
    ajustes_manuales: Optional[list[dict]] = None,
    requerimientos: Optional[list[dict]] = None,
    permitir_excepciones_cobertura_manual: bool = False,
    turnos_previos: Optional[dict[int, str]] = None,
    dias_previos_fatiga: Optional[dict[int, dict | list[dict]]] = None,
    dias_heredados: Optional[dict[int, dict[str, dict]]] = None,
    aplicar_reglas_internas: bool = True,
) -> dict:
    errores_config=validar_parejas(empleados)
    # COM admite fijos, rotativos y administrativos. Solo los rotativos necesitan
    # referencia semanal; los fijos cuentan primero como cobertura real.
    comm_rot=[e for e in empleados if e['area']=='comunicaciones' and e.get('tipo_turno')=='rotativo']
    for e in comm_rot:
        if not e.get('fecha_ancla_rotacion') or not e.get('inicio_rotacion'):
            errores_config.append(f"{e['nombre']}: el rotativo de Comunicaciones necesita turno inicial y lunes de referencia.")
    ac_rot=[e for e in empleados if e['area']=='atencion_ciudadano' and e.get('tipo_turno')=='rotativo']
    for e in ac_rot:
        if not e.get('fecha_ancla_rotacion') or not e.get('inicio_rotacion'):
            errores_config.append(f"{e['nombre']}: el rotativo de Atención al Ciudadano necesita turno inicial y lunes de referencia.")
    if errores_config:
        return {'mes':mes,'anio':anio,'valido':False,'etapa':'configuracion','errores':sorted(set(errores_config)),'advertencias':[],'estadisticas':[],'horario':[]}

    # Compatibilidad arquitectonica V13.2. Las rutas modernas ya invocan el
    # motor por area, pero llamadas historicas y pruebas pueden entregar una
    # plantilla mixta. Se divide antes de construir cualquier turno aleatorio o
    # descanso y se compone literalmente al final.
    areas_presentes = [
        area for area in ('gestion_social', 'comunicaciones', 'atencion_ciudadano')
        if any(e.get('area') == area for e in empleados)
    ]
    if len(areas_presentes) > 1:
        resultados = []
        for area in areas_presentes:
            empleados_area = [e for e in empleados if e.get('area') == area]
            ids_area = {int(e['id']) for e in empleados_area}
            resultado = generar_horario_completo(
                empleados_area,
                [s for s in solicitudes if int(s.get('empleado_id') or 0) in ids_area],
                mes,
                anio,
                historial_descansos={k: v for k, v in (historial_descansos or {}).items() if int(k) in ids_area},
                historial_no_laborados={k: v for k, v in (historial_no_laborados or {}).items() if int(k) in ids_area},
                historial_descansos_especiales={k: v for k, v in (historial_descansos_especiales or {}).items() if int(k) in ids_area},
                variante=variante,
                ajustes_manuales=[a for a in (ajustes_manuales or []) if int(a.get('empleado_id') or 0) in ids_area],
                requerimientos=[r for r in (requerimientos or []) if int(r.get('empleado_id') or 0) in ids_area],
                permitir_excepciones_cobertura_manual=permitir_excepciones_cobertura_manual,
                turnos_previos={k: v for k, v in (turnos_previos or {}).items() if int(k) in ids_area},
                dias_previos_fatiga={k: v for k, v in (dias_previos_fatiga or {}).items() if int(k) in ids_area},
                dias_heredados={k: v for k, v in (dias_heredados or {}).items() if int(k) in ids_area},
                # Las reglas internas se aplican una sola vez, sobre el mes ya
                # compuesto: dentro de un área no se ve a la gente de las otras.
                aplicar_reglas_internas=False,
            )
            resultados.append(resultado)

        horario_compuesto = [e for r in resultados for e in r.get('horario', [])]
        errores_compuestos = sorted({x for r in resultados for x in r.get('errores', [])})
        avisos_compuestos = sorted({x for r in resultados for x in r.get('advertencias', [])})
        excepciones_compuestas = sorted({x for r in resultados for x in r.get('excepciones_manuales', [])})
        stats_compuestas = [x for r in resultados for x in r.get('estadisticas', [])]
        cambios_compuestos = [x for r in resultados for x in r.get('cambios_aplicados', [])]
        domingos = len(fechas_domingos(horario_compuesto)) if horario_compuesto else 0
        festivos = len(fechas_festivos(horario_compuesto)) if horario_compuesto else 0
        compuesto = {
            'mes': mes, 'anio': anio, 'valido': not errores_compuestos,
            'etapa': 'horario_completo', 'variante': int(variante),
            'errores': errores_compuestos, 'advertencias': avisos_compuestos,
            'excepcion_manual': bool(excepciones_compuestas),
            'excepciones_manuales': excepciones_compuestas,
            'nota_horas': _nota_horas_reales(),
            'estadisticas': stats_compuestas, 'horario': horario_compuesto,
            'cambios_aplicados': cambios_compuestos,
            'resumen_validacion': {
                'estado': 'valido con programacion manual forzada' if excepciones_compuestas and not errores_compuestos else ('valido' if not errores_compuestos else 'requiere revision'),
                'errores': len(errores_compuestos), 'advertencias': len(avisos_compuestos),
            },
            'validaciones': [
                *[_validacion_legible(m, 'error') for m in errores_compuestos],
                *[_validacion_legible(m, 'advertencia') for m in avisos_compuestos],
            ],
            'reglas': {
                'maximo_dias_consecutivos': maximo_dias_consecutivos(),
                'domingos_mes': domingos,
                'festivos_mes': festivos,
                'dias_especiales_mes': len(fechas_especiales(horario_compuesto)) if horario_compuesto else 0,
                'domingos_trabajo_objetivo': domingos // 2,
                'domingos_trabajo_maximo_equilibrado': domingos // 2 + domingos % 2,
                'festivos_compensacion': 'Cada festivo trabajado requiere un descanso compensatorio adicional.',
                'especiales_trabajo_objetivo': domingos // 2,
                'especiales_trabajo_maximo_equilibrado': domingos // 2 + domingos % 2,
                'festivos_trabajo_objetivo': None,
            },
        }
        return _aplicar_reglas_internas(compuesto, aplicar_reglas_internas)
    with presupuesto_busqueda() as presupuesto:
        resultado = _generar_area_unica(
            empleados, solicitudes, mes, anio,
            historial_descansos, historial_no_laborados, historial_descansos_especiales,
            variante, ajustes_manuales, requerimientos,
            permitir_excepciones_cobertura_manual, turnos_previos, dias_previos_fatiga,
            dias_heredados,
        )
        if isinstance(resultado, dict):
            resultado['presupuesto_busqueda'] = presupuesto.resumen()
        return resultado

def _aplicar_reglas_internas(resultado: dict, activo: bool = True) -> dict:
    """Aplica las reglas particulares sobre un horario con la plantilla entera.

    Se llama desde los dos sitios donde existe un mes completo: aquí, cuando la
    plantilla llega mezclada y el motor la parte por áreas y la vuelve a juntar,
    y en `schedule_routes._componer_resultado_areas`, que es por donde pasa la
    aplicación de verdad —cada área se calcula por su cuenta y la ruta compone
    el mes—.

    Nunca desde el motor de un área suelta. Ahí el horario solo tiene a una
    parte de la gente, y una regla que nombre a alguien de otra área no lo
    encontraría: una regla que pida que alguien de Gestión Social descanse
    acompañado de alguien de Atención al Ciudadano cruza las dos áreas. Además el motor
    de un área no puede saber si ese área es toda la oficina o una parte.

    Va aquí y no dentro del motor de cada área, y el motivo es concreto: las
    áreas se generan por separado y se juntan literalmente al final, así que
    dentro de un área una regla solo ve a diez de las dieciocho personas. Una
    regla que hable de alguien de Atención al Ciudadano y de alguien de Gestión
    Social no podría existir. Aquí el horario ya está completo.

    La contrapartida es que las reparaciones ya pasaron, así que la red no puede
    ser solo el núcleo normativo: se vuelve a validar el mes entero y, si
    aparece cualquier error que antes no estaba —cobertura de un área, racha,
    lo que sea—, la regla se deshace. Esa comprobación la hace
    `reglas_internas.aplicar`; aquí solo se le pasa con qué validar.

    No toca `errores` ni `advertencias` del resultado a propósito: si una regla
    hubiera ensuciado el mes, no se habría aplicado, y si se aplicó el mes sigue
    diciendo exactamente lo mismo que decía. La aplicación no deja ver que estas
    reglas existen.
    """
    horario = resultado.get('horario') or []
    if activo and horario:
        reglas_internas.aplicar(horario, validar=lambda h: validar_horario(h)[0])
    return resultado


def _generar_area_unica(
    empleados:list[dict], solicitudes:list[dict], mes:int, anio:int,
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
    historial_no_laborados: Optional[dict[int, dict[str, set[int]]]] = None,
    historial_descansos_especiales: Optional[dict[int, dict[str, set[int]]]] = None,
    variante: int = 0,
    ajustes_manuales: Optional[list[dict]] = None,
    requerimientos: Optional[list[dict]] = None,
    permitir_excepciones_cobertura_manual: bool = False,
    turnos_previos: Optional[dict[int, str]] = None,
    dias_previos_fatiga: Optional[dict[int, dict | list[dict]]] = None,
    dias_heredados: Optional[dict[int, dict[str, dict]]] = None,
) -> dict:
    """Motor de un area concreta, ya con presupuesto de busqueda activo."""
    limpiar_caches_generacion()
    horario=construir_base(empleados,mes,anio)
    aplicar_dias_heredados(horario, dias_heredados)
    alinear_semanas_heredadas(horario)
    aplicar_descansos_fijos(horario)

    # Jerarquía de cambios V11:
    # 1) ausencias/novedades aprobadas obligatorias (INC/VAC/PER/CAP),
    # 2) asignaciones directas del jefe,
    # 3) modificaciones manuales,
    # 4) demás solicitudes aprobadas de turno/descanso/intercambio,
    # 5) reglas automáticas de descanso/rotación.
    # Ante un choque, la fuente de menor prioridad no sobrescribe silenciosamente:
    # queda un conflicto para que el usuario lo resuelva desde la interfaz.
    tipos_duros={'vacaciones','incapacidad','permiso','capacitacion'}
    solicitudes_duras=[s for s in solicitudes if s.get('tipo') in tipos_duros]
    solicitudes_operativas=[s for s in solicitudes if s.get('tipo') not in tipos_duros]

    avisos_sol: list[str] = []
    errores, reemplazos=aplicar_solicitudes_previas(horario,solicitudes_duras,advertencias=avisos_sol)
    errores.extend(aplicar_reemplazos(horario,reemplazos))

    avisos_req: list[str] = []
    err_req, reemplazos_req = aplicar_requerimientos_directos(horario, requerimientos, avisos_req)
    # Qué días quedaron puestos por una regla habitual. Se marca aquí, sobre el
    # resultado, para que las solicitudes aprobadas que vienen después sepan que
    # ese día se puede reescribir.
    _ids_habituales = {
        int(x['id']) for x in (requerimientos or [])
        if x.get('id') is not None and (x.get('recurrente_indefinido') or x.get('dias_semana'))
    }
    if _ids_habituales:
        for _e in horario:
            for _d in _e.get('dias', ()):  # noqa: PLW2901
                if int(_d.get('requerimiento_id') or 0) in _ids_habituales:
                    _d['origen_habitual'] = True
    errores.extend(err_req)
    errores.extend(aplicar_reemplazos(horario, reemplazos_req))
    errores.extend(reubicar_descanso_fijo_por_actividad(horario))

    errores.extend(aplicar_ajustes_manuales(horario, ajustes_manuales))

    err_soft, reemplazos_soft = aplicar_solicitudes_previas(
        horario, solicitudes_operativas, respetar_bloqueos_existentes=True, advertencias=avisos_sol)
    errores.extend(err_soft)
    errores.extend(aplicar_reemplazos(horario,reemplazos_soft))
    advertencias=[]
    advertencias.extend(avisos_sol)
    advertencias.extend(avisos_req)
    advertencias.extend(aplicar_ultimo_viernes_administrativo(horario))
    # El último viernes administrativo tiene prioridad sobre un descanso fijo
    # que caiga ese día. Después de marcar la jornada ADM, se intenta reubicar
    # ese descanso dentro de la misma semana, igual que cuando una actividad
    # explícita ocupa el día originalmente reservado.
    errores.extend(reubicar_descanso_fijo_por_actividad(horario))
    err_manual_d, av_manual_d = reubicar_descanso_retirado_manualmente(horario, ajustes_manuales, historial_descansos)
    errores.extend(err_manual_d)
    advertencias.extend(av_manual_d)
    errores.extend(reparar_cobertura_adm_gs(horario))
    advertencias.extend(asignar_balance_especiales(
        horario, historial_descansos, variante, dias_previos_fatiga,
    ))
    advertencias.extend(repartir_domingos_continuidad(horario, variante))
    advertencias.extend(asignar_descanso_semanal(
        horario, historial_descansos, historial_no_laborados, variante, dias_previos_fatiga,
    ))
    # Los descansos recién colocados pueden dejar un turno de una sola plaza sin
    # nadie. Se reparte la cobertura dentro del área antes de las reparaciones.
    advertencias.extend(reparar_cobertura_minima(horario))
    # Las tres reparaciones se influyen entre sí. Por ejemplo, mover un descanso
    # por fatiga puede volver a unir una racha de 7 días, y un reajuste de cobertura
    # para cortar esa racha puede modificar la secuencia AM/PM. Se estabiliza el
    # horario en varias pasadas y solo la validación final decide qué conflictos
    # siguen realmente pendientes; no se arrastran errores transitorios de una
    # pasada que una reparación posterior ya haya resuelto.
    for _estabilizacion in range(8):
        if presupuesto_agotado():
            break
        firma_antes = tuple(
            (int(e.get('empleado_id') or 0), d.get('fecha'), d.get('turno'), d.get('origen'))
            for e in horario for d in e.get('dias', [])
        )
        # Compatibilidad V13.2: incluso si una llamada historica entrega las
        # tres areas juntas, cada reparador recibe exclusivamente su plantilla.
        # Un conflicto o ajuste GS no puede cambiar las decisiones COM/AC.
        for area_actual in ('gestion_social', 'comunicaciones', 'atencion_ciudadano'):
            horario_area = [e for e in horario if e.get('area') == area_actual]
            if not horario_area:
                continue
            _err_6, av_6 = reparar_max_dias_consecutivos(horario_area, dias_previos_fatiga)
            advertencias.extend(av_6)
            _err_fatiga, av_fatiga = reparar_fatiga_laboral(
                horario_area, dias_previos_fatiga, historial_descansos
            )
            advertencias.extend(av_fatiga)
            _err_turno, av_turno = reparar_cambio_semanal(horario_area, turnos_previos)
            advertencias.extend(av_turno)
            advertencias.extend(reparar_cobertura_minima(horario_area))
            advertencias.extend(
                reparar_balance_domingos_post_reglas(horario_area, dias_previos_fatiga)
            )
            advertencias.extend(
                limpiar_puentes_fatiga_obsoletos(horario_area, dias_previos_fatiga)
            )
        firma_despues = tuple(
            (int(e.get('empleado_id') or 0), d.get('fecha'), d.get('turno'), d.get('origen'))
            for e in horario for d in e.get('dias', [])
        )
        if firma_despues == firma_antes:
            break
    err2,av2=validar_horario(
        horario,
        historial_descansos,
        historial_no_laborados,
        historial_descansos_especiales,
        turnos_previos,
        dias_previos_fatiga,
    )
    errores.extend(err2)
    advertencias.extend(av2)

    excepciones_manuales = []
    if permitir_excepciones_cobertura_manual and ajustes_manuales:
        restantes = []
        for err in errores:
            if _es_error_forzable_manual(err) and _error_relacionado_con_ajuste_manual(err, horario, ajustes_manuales):
                excepciones_manuales.append(str(err))
            else:
                restantes.append(err)
        errores = restantes
        advertencias.extend(
            'Programación manual forzada: ' + x + ' El cambio se conserva por decisión expresa del administrador.'
            for x in excepciones_manuales
        )

    stats=estadisticas(horario)
    cambios = _cambios_aplicados(horario)
    errores_unicos = sorted(set(errores))
    advertencias_unicas = sorted(set(advertencias))
    return {
        'mes':mes,'anio':anio,'valido':len(errores_unicos)==0,'etapa':'horario_completo','variante':int(variante),
        'errores':errores_unicos,'advertencias':advertencias_unicas,
        'excepcion_manual': bool(excepciones_manuales),
        'excepciones_manuales': sorted(set(excepciones_manuales)),
        'nota_horas': _nota_horas_reales(),
        'estadisticas':stats,'horario':horario,'cambios_aplicados':cambios,
        'resumen_validacion':{'estado':'válido con programación manual forzada' if excepciones_manuales and not errores_unicos else ('válido' if not errores_unicos else 'requiere revisión'),'errores':len(errores_unicos),'advertencias':len(advertencias_unicas)},
        'validaciones':[_validacion_legible(m,'error') for m in errores_unicos]+[_validacion_legible(m,'advertencia') for m in advertencias_unicas],
        'reglas':{
            # El tope de jornadas seguidas es configurable, así que viaja con el
            # horario: el Excel lo necesita para decir «CUMPLE» con el número
            # que rige de verdad y no con uno escrito a mano.
            'maximo_dias_consecutivos': maximo_dias_consecutivos(),
            'domingos_mes':len(fechas_domingos(horario)) if horario else 0,
            'festivos_mes':len(fechas_festivos(horario)) if horario else 0,
            'dias_especiales_mes':len(fechas_especiales(horario)) if horario else 0,
            'domingos_trabajo_objetivo':(len(fechas_domingos(horario)) // 2) if horario else 0,
            'domingos_trabajo_maximo_equilibrado':((len(fechas_domingos(horario)) // 2) + (len(fechas_domingos(horario)) % 2)) if horario else 0,
            'festivos_compensacion': 'Cada festivo trabajado requiere un descanso compensatorio adicional.',
            # Compatibilidad con frontend/exportadores anteriores.
            'especiales_trabajo_objetivo':(len(fechas_domingos(horario)) // 2) if horario else 0,
            'especiales_trabajo_maximo_equilibrado':((len(fechas_domingos(horario)) // 2) + (len(fechas_domingos(horario)) % 2)) if horario else 0,
            'festivos_trabajo_objetivo':None,
        }
    }
