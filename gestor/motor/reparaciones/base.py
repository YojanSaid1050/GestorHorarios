"""Base: responsabilidad separada de gestor/motor/reparacion.py."""
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
from gestor.motor.vocabulario import (  # noqa: F401
    _CACHE_ORDEN_FIRMA,
    DOMINGOS_MITAD_EXACTA,
    NONWORK_CODES,
    OUT_OF_VIGENCY_CODE,
    WORK_CODES,
)

PUENTE_ADM_FATIGA = True


def _contar_violaciones_max_dias(
    horario: list[dict],
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
) -> int:
    """Cuenta octavas jornadas sin construir el detalle de cada conflicto.

    Las reparaciones comparan miles de veces el número de conflictos antes y
    después de un movimiento; para eso basta el recuento.
    """
    prev_map = dias_previos or {}
    limite = maximo_dias_consecutivos() + 1
    total = 0
    for e in horario:
        largo = 0
        ultimo_ord = None
        for orden, d, es_previo in _secuencia_cronologica(e, prev_map.get(int(e.get('empleado_id') or 0))):
            if orden < 0:
                continue
            if ultimo_ord is not None and orden != ultimo_ord + 1:
                largo = 0
            ultimo_ord = orden
            if d.get('turno') in WORK_CODES:
                largo += 1
                if largo >= limite and not es_previo:
                    total += 1
            else:
                largo = 0
    return total

def _habilitar_descanso_max6_con_reajuste(horario: list[dict], e: dict, d: dict) -> tuple[bool, Optional[dict]]:
    """Compatibilidad: reajuste de cobertura para cortar una racha de siete días."""
    return _habilitar_descanso_con_reajuste_cobertura(horario, e, d, 'máximo 7 días consecutivos')

def _orden_dias_estable(horario: list[dict]) -> list[tuple[int, dict]]:
    """Pares (empleado_id, día) en orden estable, sin reordenar cada vez."""
    clave = id(horario)
    entrada = _CACHE_ORDEN_FIRMA.get(clave)
    if entrada is not None and entrada[0] is horario and entrada[1] == len(horario):
        return entrada[2]
    pares: list[tuple[int, dict]] = []
    for e in sorted(horario, key=lambda x: int(x.get('empleado_id') or 0)):
        eid = int(e.get('empleado_id') or 0)
        for d in sorted(e.get('dias', []), key=lambda x: str(x.get('fecha') or '')):
            pares.append((eid, d))
    _CACHE_ORDEN_FIRMA[clave] = (horario, len(horario), pares)
    return pares

def _firma_estado_turnos(horario: list[dict]) -> tuple:
    """Firma mínima para detectar ciclos durante reparaciones automáticas."""
    return tuple(
        (eid, d.get('fecha'), d.get('turno'), d.get('origen'))
        for eid, d in _orden_dias_estable(horario)
    )

def _snapshot_estado_horario(horario: list[dict]) -> list[tuple[dict, dict]]:
    # Los días contienen únicamente metadatos JSON simples; una copia completa
    # permite revertir también cambios colaterales de cobertura y del descanso
    # semanal, no solo la celda destino.
    return [(d, dict(d)) for e in horario for d in e.get('dias', [])]

def _restore_estado_horario(snapshot: list[tuple[dict, dict]]) -> None:
    for d, previo in snapshot:
        d.clear()
        d.update(previo)

def _cobertura_area_completa(horario: list[dict]) -> bool:
    if not horario:
        return True
    area = str(horario[0].get('area') or '')
    for base in horario[0].get('dias', []):
        if _es_ultimo_viernes_administrativo(base):
            continue
        fecha = base['fecha']
        am = sum(1 for e in horario if 'AM' in _turnos_cobertura_dia(_dia(e, fecha)))
        pm = sum(1 for e in horario if 'PM' in _turnos_cobertura_dia(_dia(e, fecha)))
        if am < minimo_cobertura(horario, area, 'AM', fecha):
            return False
        if pm < minimo_cobertura(horario, area, 'PM', fecha):
            return False
        if _conteo_area(horario, area, fecha) < minimo_area_cobertura(horario, area, fecha):
            return False
    return True

def _restaurar_descanso_automatico_de_semana(
    e: dict,
    lunes: str,
    excluir: Optional[dict] = None,
    origenes: Optional[set[str]] = None,
) -> Optional[tuple[dict, dict]]:
    """Devuelve a trabajo un descanso ordinario trasladable para usarlo en fatiga.

    Puede mover tanto el descanso semanal automático como el descanso colocado
    para cortar una racha de seis días. Ambos representan el mismo único
    descanso ordinario de la semana. Descansos solicitados, fijos, festivos,
    compensatorios y otras novedades permanecen intactos.
    """
    trasladables = origenes or {'descanso_automatico', 'descanso_max_6_dias', 'descanso_domingo', 'descanso_domingo_reubicado'}
    candidatos = [
        d for d in e.get('dias', [])
        if d is not excluir
        and str(d.get('lunes_semana') or '') == str(lunes)
        and d.get('turno') == 'D'
        and d.get('origen') in trasladables
    ]
    # Un descanso recién puesto en domingo para cuadrar el reparto no puede ser
    # el que se mueva para cortar una racha: volvería al sitio de donde venía y
    # el balance quedaría igual que antes. Quien lo protege se encarga de
    # descartar el intento entero si no hay otro descanso que mover.
    candidatos = [d for d in candidatos if not d.get('protegido_balance_dominical')]
    candidatos.sort(key=lambda d: d.get('fecha', ''), reverse=True)
    for d in candidatos:
        snapshot = _snapshot_dia(d)
        if _restore_base_work(d):
            return d, snapshot
    return None

def _admite_descanso(d: dict) -> bool:
    """¿Se puede colocar el descanso semanal en este día?

    Un cambio de turno aprobado dice en qué turno trabaja la persona ese día,
    no que tenga que trabajar los siete. Por eso esos días quedan bloqueados
    pero marcados con `descanso_permitido`: el descanso semanal —que es
    obligatorio— sí puede caer ahí. Sin esto, una solicitud de turno por
    semanas dejaba el domingo intocable y el reparto dominical se volvía
    imposible de cumplir.
    """
    return not d.get('bloqueado') or bool(d.get('descanso_permitido'))

def _restore_base_work(d: dict) -> bool:
    base = d.get('turno_original')
    if base not in {'AM', 'PM'}:
        return False
    d.update(
        turno=base,
        origen='turno_base',
        bloqueado=False,
        observacion='',
        solicitud_id=None,
        reemplaza_a=None,
        reemplazado_por=None,
        capacitacion_horas=0.0,
        cobertura_operativa=None,
        turno_operativo_origen=None,
        origen_descanso=None,
        motivo_descanso=None,
    )
    return True
