"""Cobertura: responsabilidad separada de gestor/motor/reparacion.py."""
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


def _asegurar_cobertura_minima(
    horario: list[dict], fechas: list[str], registro: Optional[list[dict]] = None,
) -> bool:
    """Reparte la cobertura obligatoria dentro del área en las fechas indicadas.

    Cuando un traslado de descanso deja un turno por debajo de su mínimo, esta
    función busca en la propia área a alguien que ese día trabaje el turno
    contrario y no tenga la jornada fijada, y lo cambia. Es exactamente lo que
    exige alternar la responsabilidad de un turno con una sola plaza: con un
    reparto de 2 AM + 1 PM, quien cubre PM puede descansar porque otra persona
    del área pasa ese día de AM a PM.

    Nunca trae personal de otra área ni crea descansos. Devuelve ``False`` si
    alguna fecha no puede cubrirse.
    """
    if not horario:
        return True
    area = str(horario[0].get('area') or '')
    for fecha in fechas:
        for turno, contrario in (('PM', 'AM'), ('AM', 'PM')):
            exigido = minimo_cobertura(horario, area, turno, fecha)
            if exigido <= 0:
                continue
            faltan = exigido - _conteo_turno(horario, area, fecha, turno)
            while faltan > 0:
                cubierto = False
                # Primera pasada: solo cambios que no crean una transición
                # PM→AM nueva. Segunda pasada: se acepta el cambio aunque
                # aparezca fatiga, porque la cobertura obligatoria está por
                # encima de la fatiga en el orden de prioridades; la reparación
                # de fatiga añadirá después el puente administrativo.
                for evitar_fatiga in (True, False):
                    for candidato in horario:
                        if candidato.get('tipo_turno') == 'administrativo':
                            continue
                        dia = _dia(candidato, fecha)
                        if (
                            not dia or dia.get('turno') != contrario or dia.get('bloqueado')
                            or _conflicto_pareja_para_turno(horario, candidato, fecha, turno)
                        ):
                            continue
                        # No dejar el turno contrario por debajo de su propio mínimo.
                        minimo_contrario = minimo_cobertura(horario, area, contrario, fecha)
                        if _conteo_turno(horario, area, fecha, contrario) - 1 < minimo_contrario:
                            continue
                        fatiga_antes = len(_violaciones_fatiga_laboral([candidato]))
                        snap = _snapshot_dia(dia)
                        dia.update(
                            turno=turno, origen='reajuste_cobertura_domingo', bloqueado=True,
                            observacion=(
                                f'Cobertura {turno} conservada al repartir los turnos del área'
                            ),
                            cobertura_operativa=None, turno_operativo_origen=contrario,
                        )
                        if evitar_fatiga and len(_violaciones_fatiga_laboral([candidato])) > fatiga_antes:
                            _restore_snapshot(dia, snap)
                            continue
                        if _conteo_turno(horario, area, fecha, turno) > exigido - faltan:
                            cubierto = True
                            if registro is not None:
                                registro.append({
                                    'persona': candidato.get('nombre'), 'fecha': fecha,
                                    'antes': contrario, 'despues': turno,
                                })
                            break
                        _restore_snapshot(dia, snap)
                    if cubierto:
                        break
                if not cubierto:
                    return False
                faltan -= 1
    return True

def reparar_cobertura_minima(horario: list[dict]) -> list[str]:
    """Reparte los turnos del área para respetar su mínimo obligatorio cada día.

    Un descanso puede dejar un turno sin nadie cuando ese turno tiene una sola
    plaza —el caso típico de un reparto 2 AM + 1 PM—. En vez de retirar el
    descanso, la persona que ese día trabajaba el turno contrario lo cubre. Es un
    intercambio interno del área, sin descansos adicionales ni apoyo de otras
    áreas.
    """
    if not horario:
        return []
    area = str(horario[0].get('area') or '')
    avisos: list[str] = []
    registro: list[dict] = []
    if not _reparto_fijado(area):
        return []
    for base in horario[0].get('dias', []):
        if _es_ultimo_viernes_administrativo(base):
            continue
        fecha = str(base.get('fecha') or '')
        # Solo se reorganiza cuando falta gente en un turno concreto. Si el área
        # solo exige un mínimo de personas (Comunicaciones, Atención al
        # Ciudadano), mover a alguien de AM a PM no cambia ese total: no hay
        # nada que reparar y no se toca el horario sin motivo.
        necesita = any(
            _conteo_turno(horario, area, fecha, turno) < minimo_cobertura(horario, area, turno, fecha)
            for turno in ('AM', 'PM')
        )
        if not necesita:
            continue
        _asegurar_cobertura_minima(horario, [fecha], registro)
    for cambio in registro:
        avisos.append(
            f"{cambio['persona']}: el {cambio['fecha']} pasó de {cambio['antes']} a {cambio['despues']} "
            'para conservar la cobertura obligatoria del área mientras otra persona descansa.'
        )
    return sorted(set(avisos))

def reparar_cobertura_adm_gs(horario: list[dict]) -> list[str]:
    """Reajusta AM/PM cuando una asignación ADM-GS manual deja un hueco.

    Solo mueve celdas operativas flexibles de Gestión Social en la misma fecha.
    Las solicitudes aprobadas, descansos fijos y otras novedades bloqueadas no se
    alteran. De esta manera un ajuste manual a ADM-GS puede ser una restricción
    dura sin obligar al usuario a crear además una solicitud de cambio de turno.
    """
    errores: list[str] = []
    if not horario:
        return errores

    fechas = [d['fecha'] for d in horario[0].get('dias', [])]
    for fecha in fechas:
        meta = _dia(horario[0], fecha)
        if _es_ultimo_viernes_administrativo(meta):
            continue
        gs = [e for e in horario if e.get('area') == 'gestion_social']
        if not gs or not any((_dia(e, fecha) or {}).get('turno') == 'ADM-GS' for e in gs):
            continue

        for faltante, origen in (('AM', 'PM'), ('PM', 'AM')):
            if _conteo_turno(horario, 'gestion_social', fecha, faltante) >= minimo_cobertura(horario, 'gestion_social', faltante, fecha):
                continue

            candidatos = []
            for e in gs:
                d = _dia(e, fecha)
                if not d or d.get('turno') != origen or d.get('bloqueado'):
                    continue
                if _conflicto_pareja_para_turno(horario, e, fecha, faltante):
                    continue
                if cobertura_valida_si_cambia(horario, e, d, faltante):
                    candidatos.append((e, d))

            candidatos.sort(key=lambda par: (int(par[0].get('empleado_id', 0)), par[0].get('nombre', '')))
            if not candidatos:
                errores.append(
                    f'Gestión Social queda sin {faltante} el {fecha} después de una asignación ADM-GS y no existe una persona flexible que pueda reajustarse desde {origen}.'
                )
                continue

            e, d = candidatos[0]
            anterior = d['turno']
            d.update(
                turno=faltante,
                origen='reajuste_cobertura_adm_gs',
                bloqueado=True,
                observacion=f'Reajuste automático por ADM-GS: {anterior} → {faltante} para conservar cobertura mínima',
            )

    return errores
