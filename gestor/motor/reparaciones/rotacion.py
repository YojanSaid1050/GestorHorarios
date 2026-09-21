"""Rotacion: responsabilidad separada de gestor/motor/reparacion.py."""
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


def reparar_habitualidad(
    horario: list[dict],
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
) -> tuple[list[str], list[str]]:
    """Compatibilidad interna: V13 no reubica descansos por repetición."""
    return [], []

def reparar_cambio_semanal(
    horario: list[dict],
    turnos_previos: Optional[dict[int, str]] = None,
) -> tuple[list[str], list[str]]:
    """Comprueba consistencia AM/PM dentro de cada semana.

    Si el mes comienza a mitad de semana, conserva hasta el domingo el turno
    operativo con el que esa semana quedó iniciada en el horario oficial
    anterior. Esto es especialmente importante al añadir personal nuevo a una
    rotación: el tamaño del grupo puede cambiar el cálculo modular, pero la nueva
    distribución solo debe empezar el lunes siguiente.

    No gestiona fatiga: únicamente estabiliza/comprueba la consistencia AM/PM.
    La reparación PM→AM se ejecuta de nuevo en la siguiente pasada del motor.
    """
    avisos: list[str] = []
    for v in _violaciones_cambio_semanal(horario, turnos_previos):
        e=v['empleado']
        anterior = v.get('anterior')
        lunes = str(v.get('lunes') or '')
        if v.get('tipo') == 'intra_semana' and anterior in {'AM', 'PM'} and lunes:
            cambiados: list[str] = []
            candidatos = [
                d for d in e.get('dias', [])
                if str(d.get('lunes_semana') or '') == lunes
                and d.get('turno') in {'AM', 'PM'}
                and not d.get('bloqueado')
                and not _es_excepcion_turno(d)
            ]
            snapshots: list[tuple[dict, dict]] = []
            compatible = True
            for d in candidatos:
                if d.get('turno') == anterior:
                    continue
                if not cobertura_valida_si_cambia(horario, e, d, anterior):
                    compatible = False
                    break
                snapshots.append((d, _snapshot_dia(d)))
                d.update(
                    turno=anterior,
                    turno_original=anterior,
                    origen='continuidad_semana_anterior',
                    observacion='Turno conservado hasta terminar la semana iniciada en el mes anterior',
                    cobertura_operativa=None,
                    turno_operativo_origen=None,
                )
                cambiados.append(d['fecha'])
            if compatible and cambiados:
                avisos.append(
                    f"{e['nombre']}: se conservó {anterior} del {cambiados[0]} al {cambiados[-1]} "
                    f"para terminar la semana del {lunes}; la nueva rotación comienza el lunes siguiente."
                )
                continue
            if not compatible:
                for d, snapshot in reversed(snapshots):
                    _restore_snapshot(d, snapshot)
                cambiados = []
        avisos.append(
            f"{e['nombre']}: se detectó un cambio AM/PM dentro de la semana del {v.get('lunes')}; "
            "la validación final comprobará si existe una excepción de turno autorizada."
        )
    return [], sorted(set(avisos))
