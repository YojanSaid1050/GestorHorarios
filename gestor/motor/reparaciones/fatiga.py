"""Fatiga: responsabilidad separada de gestor/motor/reparacion.py."""
from __future__ import annotations

from typing import Optional

from gestor.motor.comun import (  # noqa: F401
    _asignar_d,
    _codigo_guia_area,
    _conflicto_pareja_para_turno,
    _conteo_area,
    _conteo_turno,
    _cuenta_descansos_semanales,
    _dia,
    _es_descanso_semanal,
    _es_excepcion_turno,
    _es_ultimo_viernes_administrativo,
    _habilitar_descanso_con_reajuste_cobertura,
    _lunes_iso_de_dia,
    _puede_descansar,
    _reparto_fijado,
    _restore_snapshot,
    _secuencia_cronologica,
    _snapshot_dia,
    _turno_semana_siguiente,
    _turnos_cobertura_dia,
    _violaciones_cambio_semanal,
    _violaciones_fatiga_laboral,
    _violaciones_max_dias_consecutivos,
    clasificar_violacion_max7,
    cobertura_valida_si_cambia,
    fechas_domingos,
    maximo_dias_consecutivos,
    minimo_area_cobertura,
    minimo_cobertura,
)
from gestor.motor.presupuesto import (
    queda_presupuesto,
)
from gestor.motor.reparaciones.base import (
    PUENTE_ADM_FATIGA,
    _restaurar_descanso_automatico_de_semana,
    _restore_base_work,
)
from gestor.motor.vocabulario import (  # noqa: F401
    _CACHE_ORDEN_FIRMA,
    DOMINGOS_MITAD_EXACTA,
    NONWORK_CODES,
    OUT_OF_VIGENCY_CODE,
    WORK_CODES,
)


def _adelantar_turno_tras_descanso(
    horario: list[dict],
    e: dict,
    fecha_pm: str,
    prev_map: Optional[dict[int, dict | list[dict]]] = None,
) -> bool:
    """Adelanta el final de la semana al turno de la semana siguiente.

    Es la alternativa barata al puente administrativo. Cuando la persona ya
    descansó dentro de esa semana y los días que le quedan son los que chocan
    con la semana siguiente, esos días pasan al turno nuevo: el descanso que ya
    tenía hace de puente y nadie gasta una jornada administrativa.

    Solo se aplica si el tramo empieza justo después del descanso, si la
    cobertura del área lo admite y si no aparece ningún conflicto nuevo.
    """
    dia_pm = _dia(e, fecha_pm)
    if not dia_pm or dia_pm.get('turno') != 'PM' or dia_pm.get('bloqueado'):
        return False
    lunes = str(dia_pm.get('lunes_semana') or _lunes_iso_de_dia(dia_pm))
    objetivo = _turno_semana_siguiente(e, lunes)
    if objetivo != 'AM':
        return False

    semana = sorted(
        (d for d in e.get('dias', []) if str(d.get('lunes_semana') or '') == lunes),
        key=lambda d: d['fecha'],
    )
    # El tramo va desde el día siguiente al último descanso de la semana hasta
    # el final de esa semana.
    ultimo_libre = None
    for d in semana:
        if d.get('turno') in NONWORK_CODES:
            ultimo_libre = d
    if not ultimo_libre:
        return False
    cola = [d for d in semana if d['fecha'] > ultimo_libre['fecha']]
    if not cola or any(d.get('bloqueado') or d.get('turno') != 'PM' for d in cola):
        return False
    if fecha_pm not in {d['fecha'] for d in cola}:
        return False
    # La cobertura del área tiene que admitir el movimiento día a día.
    if any(not cobertura_valida_si_cambia(horario, e, d, objetivo) for d in cola):
        return False

    copia = [(d, _snapshot_dia(d)) for d in cola]
    for d in cola:
        d.update(
            turno=objetivo,
            origen='adelanto_turno_por_descanso',
            bloqueado=False,
            turno_operativo_origen='PM',
            observacion=(
                'Turno adelantado al de la semana siguiente: el descanso del '
                f"{ultimo_libre['fecha']} corta la transición PM→AM sin puente administrativo."
            ),
        )
    prev_e = {int(e.get('empleado_id') or 0): (prev_map or {}).get(int(e.get('empleado_id') or 0))}
    if (
        _violaciones_fatiga_laboral([e], prev_e)
        or _violaciones_max_dias_consecutivos([e], prev_e)
        or any(_conflicto_pareja_para_turno(horario, e, d['fecha'], objetivo) for d in cola)
    ):
        for d, snap in copia:
            _restore_snapshot(d, snap)
        return False
    return True

def reparar_fatiga_laboral(
    horario: list[dict],
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
) -> tuple[list[str], list[str]]:
    """Repara PM→AM sin crear descansos semanales adicionales.

    Regla V12.8:
    1. Si entre PM y AM ya existe D/VAC/INC/PER, no hay fatiga que reparar.
    2. Para convertir el primer AM en D *debe existir* otro descanso ordinario
       dentro de esa misma semana que pueda trasladarse. Puede ser el descanso
       automático o el ya colocado para cortar una racha de seis días. El motor
       nunca crea un segundo descanso semanal para resolver fatiga.
    3. Si no hay un descanso automático trasladable, si moverlo rompe cobertura
       o si el traslado genera otra incompatibilidad, se intenta el puente
       administrativo del área: PM → ADM-* → AM.
    4. Una celda fijada expresamente por solicitud, asignación o modificación
       manual no se sobrescribe de forma silenciosa; se devuelve el conflicto.

    Así se mantiene el descanso semanal total: la fatiga puede *mover* un D,
    pero no regalar uno adicional.
    """
    errores: list[str] = []
    avisos: list[str] = []
    prev_map = dias_previos or {}

    # Cada reparación elimina al menos una violación. El límite evita ciclos si
    # una combinación histórica corrupta no pudiera progresar.
    for _ in range(128):
        if not queda_presupuesto():
            break
        violaciones = _violaciones_fatiga_laboral(horario, prev_map)
        if not violaciones:
            break
        progreso = False
        for v in violaciones:
            e = v['empleado']
            d = v['dia_am']
            fecha_pm = v['fecha_pm']
            fecha_am = v['fecha_am']

            # Las decisiones explícitas tienen prioridad semántica: el motor no
            # las reemplaza silenciosamente. La validación/forzado manual podrá
            # decidir qué hacer con ese conflicto. Una regla habitual no es una
            # decisión sobre este día concreto, así que sí se puede mover para
            # cortar la fatiga: si no, un «todos los miércoles en AM» dentro de
            # una semana de tarde dejaba el mes sin poder generarse.
            if d.get('bloqueado') and not d.get('origen_habitual'):
                # En una reprogramación parcial el AM puede estar fuera del
                # rango editable y, por tanto, congelado. Si el PM que origina
                # la transición sí es automático y editable, todavía existe un
                # puente válido: transformar ese PM en la jornada ADM del área.
                # La secuencia queda PM (jornada anterior) → ADM → AM sin tocar
                # la celda preservada ni crear un descanso adicional.
                dia_pm = v.get('dia_pm')
                codigo_adm = _codigo_guia_area(str(e.get('area') or '')) if PUENTE_ADM_FATIGA else None
                if (
                    codigo_adm
                    and dia_pm
                    and not dia_pm.get('_periodo_anterior')
                    and not dia_pm.get('bloqueado')
                    and dia_pm.get('turno') == 'PM'
                ):
                    dia_pm.update(
                        turno=codigo_adm,
                        origen='puente_fatiga_administrativo',
                        bloqueado=True,
                        observacion=(
                            f'Puente administrativo por fatiga laboral: {fecha_pm} '
                            f'{codigo_adm} antes de {fecha_am} AM'
                        ),
                        cobertura_operativa=None,
                        turno_operativo_origen='PM',
                        fatiga_desde=fecha_pm,
                        fatiga_hacia=fecha_am,
                    )
                    avisos.append(
                        f"{e['nombre']}: el AM del {fecha_am} estaba preservado; "
                        f"se aplicó {codigo_adm} el {fecha_pm} como puente de último recurso sin modificar el día congelado."
                    )
                    progreso = True
                continue

            # Opción preferida: trasladar un descanso semanal automático que ya
            # existe. Si no hay uno, NO se crea un D adicional.
            lunes = str(d.get('lunes_semana') or _lunes_iso_de_dia(d))
            destino_snapshot = _snapshot_dia(d)
            # Un festivo nunca puede hacer de descanso semanal ordinario
            # (regla: festivo y descanso semanal son conceptos distintos). Si el
            # día donde habría que colocar el descanso es festivo, trasladarlo
            # allí dejaría a la persona sin descanso semanal esa semana, así que
            # se pasa directamente al puente administrativo.
            traslado = (
                None if d.get('es_festivo')
                else _restaurar_descanso_automatico_de_semana(e, lunes, excluir=d)
            )
            if traslado:
                trasladado_d, traslado_snapshot = traslado
                if _puede_descansar(horario, e, d):
                    _asignar_d(
                        d,
                        'descanso_fatiga_laboral',
                        f'Descanso semanal trasladado por fatiga laboral: evita transición PM {fecha_pm} → AM {fecha_am}',
                    )
                    d['fatiga_desde'] = fecha_pm
                    d['fatiga_hacia'] = fecha_am
                    # El traslado solo es válido si ese mismo descanso también
                    # mantiene el máximo de seis jornadas. Si adelantarlo deja
                    # una racha de siete días al final de la semana, se revierte
                    # y se usa el puente ADM; añadir otro D violaría la regla de
                    # un único descanso ordinario semanal.
                    # El traslado solo vale si la semana conserva exactamente un
                    # descanso semanal ordinario y no aparece una racha de siete.
                    if (
                        not _violaciones_max_dias_consecutivos([e], prev_map)
                        and _cuenta_descansos_semanales(e, lunes) == 1
                        and _cuenta_descansos_semanales(
                            e, str(trasladado_d.get('lunes_semana') or _lunes_iso_de_dia(trasladado_d))
                        ) == 1
                    ):
                        avisos.append(
                            f"{e['nombre']}: el descanso semanal se trasladó de {trasladado_d['fecha']} a {fecha_am} "
                            f"para evitar fatiga PM→AM desde {fecha_pm}; no se añadió un descanso extra."
                        )
                        progreso = True
                        continue
                    _restore_snapshot(d, destino_snapshot)
                    _restore_snapshot(trasladado_d, traslado_snapshot)
                else:
                    # Se restauró el D al probar el traslado. Si el día destino
                    # no puede descansar por cobertura, devolvemos el descanso a
                    # su sitio original antes de intentar ADM.
                    _restore_snapshot(trasladado_d, traslado_snapshot)

            # Antes del puente administrativo: usar como puente el descanso
            # que la persona ya tiene esa semana. Si descansó, por ejemplo, el
            # sábado y el domingo trabaja PM justo antes de una semana AM, se
            # adelanta ese domingo a AM. El descanso del sábado corta la
            # transición y no hace falta gastar una jornada administrativa.
            if _adelantar_turno_tras_descanso(horario, e, fecha_pm, prev_map):
                avisos.append(
                    f"{e['nombre']}: el {fecha_pm} se adelantó al turno de la semana siguiente. "
                    'El descanso que ya tenía esa semana corta la transición PM→AM, '
                    'así que no hizo falta un puente administrativo.'
                )
                progreso = True
                continue

            # Última alternativa automática: PM → ADM → AM. El ADM conserva la
            # cobertura operativa AM del día sustituido cuando corresponde.
            codigo_adm = _codigo_guia_area(str(e.get('area') or '')) if PUENTE_ADM_FATIGA else None
            if codigo_adm:
                d.update(
                    turno=codigo_adm,
                    origen='puente_fatiga_administrativo',
                    bloqueado=True,
                    observacion=(
                        f'Puente administrativo por fatiga laboral: {fecha_pm} PM → '
                        f'{fecha_am} {codigo_adm} → siguiente jornada AM'
                    ),
                    cobertura_operativa='AM' if codigo_adm == 'ADM-GS' else None,
                    turno_operativo_origen='AM',
                    fatiga_desde=fecha_pm,
                    fatiga_hacia=fecha_am,
                )
                avisos.append(
                    f"{e['nombre']}: no había un descanso semanal automático trasladable o moverlo no era viable; "
                    f"se aplicó {codigo_adm} como puente de último recurso para evitar PM→AM directo."
                )
                progreso = True

        if not progreso:
            break

    for v in _violaciones_fatiga_laboral(horario, prev_map):
        e = v['empleado']
        inter = v.get('intermedios') or []
        detalle = f" Hay jornada(s) intermedia(s) trabajada(s): {', '.join(inter)}." if inter else ''
        errores.append(
            f"Fatiga laboral: {e['nombre']} termina PM el {v['fecha_pm']} y pasaría a AM el {v['fecha_am']} "
            f"sin un descanso ya existente que pueda trasladarse ni un puente administrativo ADM entre ambas jornadas.{detalle}"
        )
    return sorted(set(errores)), sorted(set(avisos))

def limpiar_puentes_fatiga_obsoletos(
    horario: list[dict],
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
) -> list[str]:
    """Retira un ADM automático cuando ya existe un corte no laborado válido.

    Otras reparaciones pueden mover el descanso después de haber creado el
    puente de último recurso. Se restaura el turno operativo original si con
    ello no reaparecen fatiga, una octava jornada ni un hueco de cobertura.
    """
    avisos: list[str] = []
    for e in horario:
        eid = int(e.get('empleado_id') or 0)
        prev_e = {eid: (dias_previos or {}).get(eid)}
        for d in e.get('dias', []):
            if d.get('origen') != 'puente_fatiga_administrativo':
                continue
            if d.get('preservado_parcial'):
                # Celda de una semana cerrada o de una reprogramación parcial:
                # se conserva exactamente como estaba, aunque el puente ya no
                # fuera necesario con la programación nueva.
                continue
            original = _snapshot_dia(d)
            turno = str(d.get('turno_operativo_origen') or '')
            if turno not in {'AM', 'PM'}:
                if not _restore_base_work(d):
                    continue
            else:
                d.update(
                    turno=turno, origen='turno_base', bloqueado=False,
                    observacion='', cobertura_operativa=None,
                    turno_operativo_origen=None, fatiga_desde=None, fatiga_hacia=None,
                )
            if (
                _violaciones_fatiga_laboral([e], prev_e)
                or _violaciones_max_dias_consecutivos([e], prev_e)
            ):
                _restore_snapshot(d, original)
                continue
            avisos.append(
                f"{e['nombre']}: se retiró el puente administrativo del {d['fecha']} "
                "porque un día no laborado ya corta la transición PM→AM."
            )
    return avisos
