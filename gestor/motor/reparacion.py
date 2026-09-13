# -*- coding: utf-8 -*-
"""4 · Arreglar lo que quedó mal.

Después de repartir pueden quedar rachas demasiado largas, un área sin
cubrir o un cambio PM→AM sin corte. Aquí se intenta resolver cada cosa
sin deshacer lo que alguien decidió a propósito.
"""
from __future__ import annotations

from datetime import date, timedelta
from itertools import combinations, product
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

# Cómo se le cuenta a una persona un aviso de validación vive en su propio
# módulo: son ciento catorce líneas de texto que no dependen del horario.
from gestor.motor.presupuesto import (
    MAX_COMBINACIONES_REPARACION,
    MAX_COMBINACIONES_SOLVER_AREA,
    limitar,
    presupuesto_agotado,
    queda_presupuesto,
)
from gestor.motor.vocabulario import (  # noqa: F401
    _CACHE_ORDEN_FIRMA,
    DOMINGOS_MITAD_EXACTA,
    NONWORK_CODES,
    OUT_OF_VIGENCY_CODE,
    WORK_CODES,
)

# Puente administrativo por fatiga (último recurso).
# Cuando alguien sale de PM (termina a las 21:00) y entraría a AM (empieza a las
# 5:00), quedan ocho horas entre jornadas. Lo primero que intenta el motor es
# mover el descanso semanal a ese día; si no puede, convierte la jornada en
# administrativa (7:30–15:30), que sí deja un descanso razonable entre turnos.
# Poniendo esto en False el puente deja de existir: los casos que no se puedan
# resolver moviendo un descanso quedarán como conflicto de fatiga.
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

def _intentar_reparacion_max6_coordinada(
    horario: list[dict],
    dias_previos: Optional[dict[int, dict | list[dict]]],
    visitados: set[tuple],
    profundidad: int = 0,
) -> Optional[str]:
    """Confirma varios traslados semanales como una unica transaccion."""
    todas = _violaciones_max_dias_consecutivos(horario, dias_previos, detallado=True)
    # Las rachas cuyas ocho jornadas están congeladas no se pueden cortar con
    # ninguna combinación; se excluyen del árbol de búsqueda.
    violaciones = [v for v in todas if not (v.get('bloqueo') or {}).get('irreparable')]
    if not violaciones:
        return None
    conflictos_antes = len(todas)
    fatiga_antes = len(_violaciones_fatiga_laboral(horario, dias_previos))
    original = _snapshot_estado_horario(horario)
    dias_lineales = [d for e in horario for d in e.get('dias', [])]
    trasladables = {
        'descanso_automatico', 'descanso_max_6_dias', 'descanso_fatiga_laboral',
        'descanso_domingo', 'descanso_domingo_reubicado', 'descanso_fijo',
    }
    afectados = []
    ids_vistos = set()
    for violacion in violaciones:
        empleado = violacion['empleado']
        eid = int(empleado.get('empleado_id') or 0)
        if eid not in ids_vistos:
            ids_vistos.add(eid)
            afectados.append(empleado)

    for empleado in afectados:
        if presupuesto_agotado():
            break
        semanas_objetivo = set()
        for violacion in (v for v in violaciones if v['empleado'] is empleado):
            for fecha_iso in violacion.get('racha', []):
                dia = _dia(empleado, fecha_iso)
                if dia:
                    semanas_objetivo.add(str(dia.get('lunes_semana') or _lunes_iso_de_dia(dia)))
            fin = date.fromisoformat(violacion['fecha'])
            semanas_objetivo.add((fin - timedelta(days=fin.weekday()) + timedelta(days=7)).isoformat())

        semanas = []
        for lunes in sorted(semanas_objetivo):
            dias_semana = [
                d for d in empleado.get('dias', [])
                if str(d.get('lunes_semana') or _lunes_iso_de_dia(d)) == lunes
            ]
            descansos = [
                d for d in dias_semana
                if d.get('turno') == 'D' and _es_descanso_semanal(d)
                and d.get('origen') in trasladables and not d.get('preservado_parcial')
            ]
            if len(descansos) != 1:
                continue
            actual = descansos[0]
            destinos = [actual] + [
                d for d in dias_semana
                if d is not actual and d.get('turno') in {'AM', 'PM'}
                and not d.get('bloqueado') and not d.get('es_festivo')
            ]
            destinos.sort(key=lambda d: (d is not actual, str(d.get('fecha') or '')))
            semanas.append((lunes, actual, destinos))
        # Si la racha solo ocupa una o dos semanas visibles, incluir la semana
        # anterior permite desplazar toda la cadena sin elevar el producto a
        # cuatro semanas (7^4 combinaciones) en los casos normales.
        if semanas and len(semanas) < 3:
            lunes_previo = (date.fromisoformat(semanas[0][0]) - timedelta(days=7)).isoformat()
            dias_previos_semana = [
                d for d in empleado.get('dias', [])
                if str(d.get('lunes_semana') or _lunes_iso_de_dia(d)) == lunes_previo
            ]
            descansos_previos = [
                d for d in dias_previos_semana
                if d.get('turno') == 'D' and _es_descanso_semanal(d)
                and d.get('origen') in trasladables and not d.get('preservado_parcial')
            ]
            if len(descansos_previos) == 1:
                actual = descansos_previos[0]
                destinos = [actual] + [
                    d for d in dias_previos_semana
                    if d is not actual and d.get('turno') in {'AM', 'PM'}
                    and not d.get('bloqueado') and not d.get('es_festivo')
                ]
                destinos.sort(key=lambda d: (d is not actual, str(d.get('fecha') or '')))
                semanas.insert(0, (lunes_previo, actual, destinos))
        semanas = semanas[:3]
        if not semanas:
            continue

        mejor_estado = None
        mejor_puntaje = None
        mejor_movimientos = []
        mejor_intercambios = []
        mejor_puentes = []
        mejor_encadenadas = []
        for seleccion in limitar(
            product(*(semana[2] for semana in semanas)), MAX_COMBINACIONES_REPARACION
        ):
            if all(destino is semanas[i][1] for i, destino in enumerate(seleccion)):
                continue
            _restore_estado_horario(original)
            valido = True
            movimientos = []
            intercambios = []
            puentes = []
            encadenadas = []

            for _lunes, actual, _destinos in semanas:
                if not _restore_base_work(actual):
                    valido = False
                    break
                turno = str(actual.get('turno') or '')
                if turno in {'AM', 'PM'} and _conflicto_pareja_para_turno(
                    horario, empleado, actual['fecha'], turno
                ):
                    valido = False
                    break
            if not valido:
                continue

            for i, destino in enumerate(seleccion):
                actual = semanas[i][1]
                if not _puede_descansar(horario, empleado, destino):
                    # Primero reutilizamos el reajuste de cobertura de la ruta
                    # rápida. Si existe una persona flexible en el mismo área,
                    # no hace falta permutar descansos y se conserva la
                    # operación como una única transacción.
                    habilitado, reajuste = _habilitar_descanso_max6_con_reajuste(
                        horario, empleado, destino
                    )
                    if habilitado:
                        if reajuste:
                            intercambios.append((reajuste['persona'], reajuste['fecha'], destino['fecha']))
                        _asignar_d(
                            destino, 'descanso_max_6_dias',
                            'Descanso semanal reubicado por reparacion coordinada de maximo 6 dias',
                        )
                        if destino is not actual:
                            movimientos.append((actual['fecha'], destino['fecha']))
                        continue
                    intercambio_ok = False
                    for otra in horario:
                        if (
                            otra is empleado or otra.get('area') != empleado.get('area')
                            or otra.get('tipo_turno') == 'administrativo'
                        ):
                            continue
                        otro_destino = _dia(otra, destino['fecha'])
                        otro_origen = _dia(otra, actual['fecha'])
                        if (
                            not otro_destino or not otro_origen
                            or otro_destino.get('turno') != 'D'
                            or not _es_descanso_semanal(otro_destino)
                            or otro_destino.get('origen') not in trasladables
                            or otro_destino.get('preservado_parcial')
                            or otro_origen.get('turno') not in {'AM', 'PM'}
                            or otro_origen.get('bloqueado')
                        ):
                            continue
                        intento = _snapshot_estado_horario(horario)
                        if not _restore_base_work(otro_destino):
                            _restore_estado_horario(intento)
                            continue
                        turno_otro = str(otro_destino.get('turno') or '')
                        if _conflicto_pareja_para_turno(
                            horario, otra, otro_destino['fecha'], turno_otro
                        ) or not _puede_descansar(horario, otra, otro_origen):
                            _restore_estado_horario(intento)
                            continue
                        _asignar_d(
                            otro_origen, 'descanso_max_6_dias',
                            f"Intercambio de descanso para cubrir a {empleado['nombre']} el {destino['fecha']}",
                        )
                        if _puede_descansar(horario, empleado, destino):
                            intercambios.append((otra['nombre'], otro_destino['fecha'], otro_origen['fecha']))
                            intercambio_ok = True
                            break
                        _restore_estado_horario(intento)
                    if not intercambio_ok:
                        valido = False
                        break
                _asignar_d(
                    destino, 'descanso_max_6_dias',
                    'Descanso semanal reubicado por reparacion coordinada de maximo 6 dias',
                )
                if destino is not actual:
                    movimientos.append((actual['fecha'], destino['fecha']))
            if not valido:
                continue

            for lunes, _actual, _destinos in semanas:
                if sum(
                    1 for d in empleado.get('dias', [])
                    if str(d.get('lunes_semana') or _lunes_iso_de_dia(d)) == lunes
                    and _es_descanso_semanal(d)
                ) != 1:
                    valido = False
                    break
            if not valido:
                continue

            # Si el intercambio de cobertura trasladó una racha a la persona
            # que cubre, resolver también esa cadena dentro de la misma
            # transacción antes de decidir si el conjunto mejora realmente.
            conflictos_intermedios = (_contar_violaciones_max_dias(horario, dias_previos))
            if conflictos_intermedios >= conflictos_antes and intercambios and profundidad < 1:
                reparacion_encadenada = _intentar_reparacion_max6_coordinada(
                    horario, dias_previos, visitados, profundidad + 1
                )
                if reparacion_encadenada:
                    encadenadas.append(reparacion_encadenada)

            fatiga_nueva = _violaciones_fatiga_laboral(horario, dias_previos)
            if len(fatiga_nueva) > fatiga_antes:
                for violacion_fatiga in fatiga_nueva:
                    if violacion_fatiga['empleado'] is not empleado:
                        continue
                    dia_am = violacion_fatiga['dia_am']
                    codigo_adm = _codigo_guia_area(str(empleado.get('area') or '')) if PUENTE_ADM_FATIGA else None
                    if (
                        dia_am.get('bloqueado') or dia_am.get('turno') != 'AM'
                        or not codigo_adm
                        or not cobertura_valida_si_cambia(horario, empleado, dia_am, codigo_adm)
                    ):
                        valido = False
                        break
                    dia_am.update(
                        turno=codigo_adm, origen='puente_fatiga_administrativo', bloqueado=True,
                        observacion='Puente administrativo de ultimo recurso dentro de reparacion coordinada',
                        cobertura_operativa='AM' if codigo_adm == 'ADM-GS' else None,
                        turno_operativo_origen='AM',
                        fatiga_desde=violacion_fatiga['fecha_pm'], fatiga_hacia=violacion_fatiga['fecha_am'],
                    )
                    puentes.append(dia_am['fecha'])
            if not valido:
                continue

            conflictos_despues = (_contar_violaciones_max_dias(horario, dias_previos))
            fatiga_despues = len(_violaciones_fatiga_laboral(horario, dias_previos))
            firma = _firma_estado_turnos(horario)
            if (
                conflictos_despues >= conflictos_antes
                or fatiga_despues > fatiga_antes
                or firma in visitados
            ):
                continue
            puntaje = (conflictos_despues, len(puentes), len(intercambios), len(movimientos))
            if mejor_puntaje is None or puntaje < mejor_puntaje:
                mejor_puntaje = puntaje
                mejor_estado = [dict(d) for d in dias_lineales]
                mejor_movimientos = movimientos
                mejor_intercambios = intercambios
                mejor_puentes = puentes
                mejor_encadenadas = encadenadas
                if conflictos_despues == 0:
                    break

        _restore_estado_horario(original)
        if mejor_estado is not None:
            # El estado guardado tiene una entrada por día; si no, se
            # restauraría el horario a medias sin que nadie lo notara.
            for dia, guardado in zip(dias_lineales, mejor_estado, strict=True):
                dia.clear()
                dia.update(guardado)
            visitados.add(_firma_estado_turnos(horario))
            detalle = ', '.join(f'{origen} a {destino}' for origen, destino in mejor_movimientos)
            if mejor_intercambios:
                detalle += '; cobertura: ' + ', '.join(
                    f'{nombre} {origen} a {destino}' for nombre, origen, destino in mejor_intercambios
                )
            if mejor_puentes:
                detalle += '; ADM ultimo recurso: ' + ', '.join(mejor_puentes)
            if mejor_encadenadas:
                detalle += '; reparacion encadenada: ' + ' | '.join(mejor_encadenadas)
            return (
                f"{empleado['nombre']}: reparacion coordinada de descansos ({detalle}); "
                f"conflictos maximo 6: {conflictos_antes} a {mejor_puntaje[0]}."
            )
    _restore_estado_horario(original)
    return None

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

def _intentar_reparacion_max6_area_conjunta(
    horario: list[dict],
    dias_previos: Optional[dict[int, dict | list[dict]]],
    visitados: set[tuple],
) -> Optional[str]:
    """Combina planes de descanso ya validos de varias personas del area."""
    todas = _violaciones_max_dias_consecutivos(horario, dias_previos, detallado=True)
    violaciones = [v for v in todas if not (v.get('bloqueo') or {}).get('irreparable')]
    if not violaciones or not horario:
        return None
    conflictos_antes = len(todas)
    fatiga_antes = len(_violaciones_fatiga_laboral(horario, dias_previos))
    trasladables = {
        'descanso_automatico', 'descanso_max_6_dias', 'descanso_fatiga_laboral',
        'descanso_domingo', 'descanso_domingo_reubicado', 'descanso_fijo',
    }
    semanas_objetivo = set()
    for violacion in violaciones:
        for fecha_iso in violacion.get('racha', []):
            dia = _dia(violacion['empleado'], fecha_iso)
            if dia:
                semanas_objetivo.add(str(dia.get('lunes_semana') or _lunes_iso_de_dia(dia)))
    if not semanas_objetivo:
        return None
    primer_lunes = min(semanas_objetivo)
    semanas_objetivo.add((date.fromisoformat(primer_lunes) - timedelta(days=7)).isoformat())
    # Con continuidad mensual, la racha puede comenzar en la última semana
    # del mes anterior. Conservamos cuatro semanas (incluida la precedente)
    # para que el intercambio atómico tenga una fecha real donde cortar la
    # cadena; limitarlo a tres podía dejar intacta una racha 8→14 aunque el
    # descanso de la semana anterior fuese trasladable.
    semanas = sorted(semanas_objetivo)[-4:]
    original = _snapshot_estado_horario(horario)
    planes_por_persona = []

    for empleado in horario:
        if empleado.get('tipo_turno') == 'administrativo':
            continue
        if presupuesto_agotado():
            break
        definiciones = []
        for lunes in semanas:
            dias_semana = [d for d in empleado.get('dias', []) if str(d.get('lunes_semana') or '') == lunes]
            descansos = [
                d for d in dias_semana if d.get('turno') == 'D'
                and _es_descanso_semanal(d) and d.get('origen') in trasladables
                and not d.get('preservado_parcial')
            ]
            if len(descansos) != 1:
                continue
            actual = descansos[0]
            opciones = [actual] + [
                d for d in dias_semana if d is not actual and d.get('turno') in {'AM', 'PM'}
                and not d.get('bloqueado') and not d.get('es_festivo')
            ]
            definiciones.append((lunes, actual, opciones))
        if not definiciones:
            continue

        planes = []
        prev_empleado = {
            int(empleado['empleado_id']): (dias_previos or {}).get(int(empleado['empleado_id']))
        }
        fatiga_persona_antes = len(_violaciones_fatiga_laboral([empleado], prev_empleado))
        for seleccion in limitar(
            product(*(x[2] for x in definiciones)), MAX_COMBINACIONES_REPARACION
        ):
            _restore_estado_horario(original)
            if not all(_restore_base_work(x[1]) for x in definiciones):
                continue
            for destino in seleccion:
                _asignar_d(destino, 'descanso_max_6_dias', 'Descanso coordinado por solver de area')
            if _violaciones_max_dias_consecutivos([empleado], prev_empleado):
                continue
            if len(_violaciones_fatiga_laboral([empleado], prev_empleado)) > fatiga_persona_antes:
                continue
            cambios = sum(1 for i, destino in enumerate(seleccion) if destino is not definiciones[i][1])
            planes.append((cambios, tuple(d['fecha'] for d in seleccion)))
        _restore_estado_horario(original)
        if not planes:
            continue
        planes.sort(key=lambda x: (x[0], x[1]))
        planes_por_persona.append((empleado, definiciones, planes[:32]))

    if not planes_por_persona:
        return None
    explorados = 0
    for combinacion in limitar(
        product(*(x[2] for x in planes_por_persona)), MAX_COMBINACIONES_SOLVER_AREA
    ):
        explorados += 1
        _restore_estado_horario(original)
        for empleado, definiciones, _planes in planes_por_persona:
            for _lunes, actual, _opciones in definiciones:
                _restore_base_work(actual)
        for indice, (empleado, definiciones, _planes) in enumerate(planes_por_persona):
            fechas = combinacion[indice][1]
            for fecha_iso in fechas:
                _asignar_d(_dia(empleado, fecha_iso), 'descanso_max_6_dias', 'Descanso coordinado por solver de area')
        # Una permuta de descansos puede dejar un rotativo de COM como única
        # persona PM en una fecha. Antes de descartar la combinación, permite
        # un reajuste interno AM→PM de la misma área, siempre que no aumente
        # máximo-6 ni fatiga. Nunca se cruza personal entre áreas.
        area_plan = str(horario[0].get('area') or '') if horario else ''
        if area_plan == 'comunicaciones':
            for base_dia in (horario[0].get('dias', []) if horario else []):
                fecha_iso = str(base_dia.get('fecha') or '')
                if _conteo_turno(horario, area_plan, fecha_iso, 'PM') >= minimo_cobertura(horario, area_plan, 'PM', fecha_iso):
                    continue
                conflicto_base = (_contar_violaciones_max_dias(horario, dias_previos))
                fatiga_base = len(_violaciones_fatiga_laboral(horario, dias_previos))
                reajustado = False
                # Si todos los posibles cubridores quedaron descansando ese
                # día, intercambiar atómicamente uno de esos descansos por
                # otra fecha de su misma semana y dejarlo PM. Es la situación
                # típica de COM con un único PM disponible; no se trae apoyo
                # de GS/AC ni crea un segundo descanso.
                for cubridor in horario:
                    dia_descanso = _dia(cubridor, fecha_iso)
                    if not dia_descanso or dia_descanso.get('turno') != 'D' or not _es_descanso_semanal(dia_descanso):
                        continue
                    lunes_cubridor = str(dia_descanso.get('lunes_semana') or '')
                    for nuevo_descanso in [
                        x for x in cubridor.get('dias', [])
                        if str(x.get('lunes_semana') or '') == lunes_cubridor
                        and x.get('turno') in {'AM', 'PM'}
                        and not x.get('bloqueado') and not x.get('es_festivo')
                    ]:
                        estado = _snapshot_estado_horario(horario)
                        if not _restore_base_work(dia_descanso):
                            _restore_estado_horario(estado)
                            continue
                        _asignar_d(nuevo_descanso, 'descanso_max_6_dias', 'Descanso intercambiado para conservar cobertura PM de Comunicaciones')
                        dia_descanso.update(
                            turno='PM', origen='reajuste_cobertura_max_6', bloqueado=True,
                            observacion='Cobertura PM conservada durante intercambio atomico de descansos',
                            cobertura_operativa=None, turno_operativo_origen='AM',
                        )
                        if (
                            _conteo_turno(horario, area_plan, fecha_iso, 'PM') >= minimo_cobertura(horario, area_plan, 'PM', fecha_iso)
                            and (_contar_violaciones_max_dias(horario, dias_previos)) <= conflicto_base
                            and len(_violaciones_fatiga_laboral(horario, dias_previos)) <= fatiga_base
                        ):
                            reajustado = True
                            break
                        _restore_estado_horario(estado)
                    if reajustado:
                        break
                if reajustado:
                    continue
                for candidato in horario:
                    dia_candidato = _dia(candidato, fecha_iso)
                    if (
                        not dia_candidato or candidato.get('tipo_turno') == 'administrativo'
                        or dia_candidato.get('turno') != 'AM'
                        or dia_candidato.get('bloqueado')
                        or _conflicto_pareja_para_turno(horario, candidato, fecha_iso, 'PM')
                    ):
                        continue
                    estado = _snapshot_estado_horario(horario)
                    dia_candidato.update(
                        turno='PM', origen='reajuste_cobertura_max_6', bloqueado=True,
                        observacion='Reajuste de cobertura COM durante intercambio atomico de descansos',
                        cobertura_operativa=None, turno_operativo_origen='AM',
                    )
                    if (
                        _conteo_turno(horario, area_plan, fecha_iso, 'PM') >= minimo_cobertura(horario, area_plan, 'PM', fecha_iso)
                        and (_contar_violaciones_max_dias(horario, dias_previos)) <= conflicto_base
                        and len(_violaciones_fatiga_laboral(horario, dias_previos)) <= fatiga_base
                    ):
                        reajustado = True
                        break
                    _restore_estado_horario(estado)
                if not reajustado:
                    _restore_estado_horario(original)
                    break
            if not _cobertura_area_completa(horario):
                _restore_estado_horario(original)
                continue
        firma = _firma_estado_turnos(horario)
        if firma in visitados or not _cobertura_area_completa(horario):
            continue
        conflictos_despues = (_contar_violaciones_max_dias(horario, dias_previos))
        fatiga_despues = len(_violaciones_fatiga_laboral(horario, dias_previos))
        if conflictos_despues < conflictos_antes and fatiga_despues <= fatiga_antes:
            visitados.add(firma)
            return (
                f"Reparacion conjunta de descansos en {horario[0].get('area')}: "
                f"{len(planes_por_persona)} personas coordinadas; conflictos maximo 6: "
                f"{conflictos_antes} a {conflictos_despues}."
            )
    _restore_estado_horario(original)
    return None

def reparar_max_dias_consecutivos(
    horario: list[dict],
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
) -> tuple[list[str], list[str]]:
    """Corta rachas de siete días sin trasladar el problema a otra fecha.

    Cada movimiento se prueba de forma transaccional en memoria. Solo se conserva
    si reduce estrictamente el número de violaciones de máximo 7 y no repite un
    estado visitado. Así se evitan oscilaciones A→B→A y falsos arreglos que
    únicamente mueven la octava jornada.
    """
    avisos: list[str] = []
    visitados={_firma_estado_turnos(horario)}
    limite_estados=128
    for _ in range(limite_estados):
        if not queda_presupuesto():
            break
        todas = _violaciones_max_dias_consecutivos(horario, dias_previos, detallado=True)
        # Una racha cuyas ocho jornadas están congeladas no admite ninguna
        # reubicación. Buscar combinaciones para ella solo consume el
        # presupuesto y retrasa la respuesta, así que se aparta desde el
        # principio y se informa como excepción autorizada.
        viol = [v for v in todas if not (v.get('bloqueo') or {}).get('irreparable')]
        if not viol:
            break
        conflictos_antes=len(todas)
        progreso = False
        for v in viol:
            e=v['empleado']
            fechas=set(v['racha'])
            candidatos=[]
            for d in e.get('dias', []):
                if d.get('fecha') not in fechas or d.get('turno') not in WORK_CODES or (d.get('bloqueado') and d.get('origen') not in {'reajuste_cobertura_max_6','descanso_max_6_dias'}):
                    continue
                es_especial = bool(d.get('es_domingo') or d.get('es_festivo'))
                candidatos.append((1 if es_especial else 0, -date.fromisoformat(d['fecha']).toordinal(), d))
            candidatos.sort(key=lambda x:(x[0],x[1]))
            for _especial,_ord,d in candidatos:
                estado_previo=_snapshot_estado_horario(horario)

                # Un festivo no trabajado es adicional al descanso semanal. Si
                # la octava jornada cae en festivo, probar primero dejar de
                # trabajarlo y retirar el compensatorio automático asociado.
                # Así se corta la racha sin convertir el festivo en descanso
                # semanal ni regalar un segundo D ordinario.
                if d.get('es_festivo'):
                    compensatorios=[
                        x for x in e.get('dias',[])
                        if x.get('origen')=='compensatorio_festivo'
                        and x.get('festivo_origen')==d.get('fecha')
                    ]
                    restaurables=True
                    for comp in compensatorios:
                        if comp.get('preservado_parcial') or comp.get('origen')!='compensatorio_festivo':
                            restaurables=False
                            break
                        if not _restore_base_work(comp):
                            restaurables=False
                            break
                    if restaurables and _puede_descansar(horario,e,d):
                        anterior=d.get('turno')
                        d.update(
                            turno='D',origen='descanso_festivo',bloqueado=True,
                            observacion='Festivo no trabajado para cortar una racha superior a 6 días sin usar el descanso semanal',
                            origen_descanso=None,motivo_descanso=None,
                        )
                        conflictos_despues=(_contar_violaciones_max_dias(horario,dias_previos))
                        firma=_firma_estado_turnos(horario)
                        if conflictos_despues < conflictos_antes and firma not in visitados:
                            visitados.add(firma)
                            avisos.append(
                                f"{e['nombre']}: el festivo {d['fecha']} pasó de {anterior} a no trabajado para cortar una racha de 7 días; "
                                f"conflictos máximo 7: {conflictos_antes} → {conflictos_despues}. "
                                "El descanso semanal ordinario se conserva aparte."
                            )
                            progreso=True
                            break
                    _restore_estado_horario(estado_previo)
                    # Si el festivo no puede liberarse, se continúa con la ruta
                    # ordinaria solo para candidatos no festivos.
                    continue

                lunes_d = str(d.get('lunes_semana') or _lunes_iso_de_dia(d))
                traslado = _restaurar_descanso_automatico_de_semana(
                    e,
                    lunes_d,
                    excluir=d,
                    origenes={'descanso_automatico','descanso_fatiga_laboral','descanso_max_6_dias','descanso_domingo','descanso_domingo_reubicado'},
                )
                # El descanso semanal es uno solo. Si esa semana ya tiene el
                # suyo y no se ha podido mover —porque es un descanso pedido,
                # fijo o protegido— convertir este día en descanso dejaría dos
                # en la misma semana, que es justo lo que la regla 1.1
                # prohíbe. En ese caso se prueba otro día de la racha.
                if traslado is None and _cuenta_descansos_semanales(e, lunes_d):
                    _restore_estado_horario(estado_previo)
                    continue
                habilitado,reajuste=_habilitar_descanso_max6_con_reajuste(horario,e,d)
                if not habilitado:
                    _restore_estado_horario(estado_previo)
                    continue
                anterior=d.get('turno')
                _asignar_d(d,'descanso_max_6_dias','Descanso necesario para evitar más de 7 días consecutivos de trabajo')
                conflictos_despues=(_contar_violaciones_max_dias(horario,dias_previos))
                firma=_firma_estado_turnos(horario)
                # Requisito de seguridad: un movimiento solo vale si mejora la
                # función objetivo; empatar significa trasladar el problema.
                if conflictos_despues >= conflictos_antes or firma in visitados:
                    _restore_estado_horario(estado_previo)
                    continue
                visitados.add(firma)
                detalle=(f"; {reajuste['persona']} cambió {reajuste['antes']} → {reajuste['despues']} para conservar cobertura" if reajuste else '')
                if traslado:
                    detalle += f"; el descanso ordinario se trasladó desde {traslado[0]['fecha']}"
                avisos.append(
                    f"{e['nombre']}: se trasladó el descanso semanal al {d['fecha']} para cortar una racha de 7 días "
                    f"({anterior} → D); conflictos máximo 7: {conflictos_antes} → {conflictos_despues}{detalle}."
                )
                progreso=True
                break
            if progreso:
                break
        if not progreso:
            aviso_coordinado = _intentar_reparacion_max6_coordinada(
                horario, dias_previos, visitados
            )
            if aviso_coordinado:
                avisos.append(aviso_coordinado)
                # La reparación individual puede reducir la cantidad de
                # conflictos sin eliminarla por completo. En ese caso se debe
                # intentar inmediatamente la permuta coordinada del área; de
                # lo contrario la estabilización puede quedarse en un estado
                # parcial aunque exista una solución colectiva.
                if _violaciones_max_dias_consecutivos(horario, dias_previos):
                    aviso_area = _intentar_reparacion_max6_area_conjunta(
                        horario, dias_previos, visitados
                    )
                    if aviso_area:
                        avisos.append(aviso_area)
            else:
                aviso_area = _intentar_reparacion_max6_area_conjunta(
                    horario, dias_previos, visitados
                )
                if aviso_area:
                    avisos.append(aviso_area)
                else:
                    break
    errores=[]
    for v in _violaciones_max_dias_consecutivos(horario,dias_previos,detallado=True):
        nivel, mensaje = clasificar_violacion_max7(v, horario)
        if nivel == 'error':
            errores.append(mensaje)
        else:
            avisos.append(mensaje)
    return sorted(set(errores)), sorted(set(avisos))

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

def reparar_balance_domingos_post_reglas(
    horario: list[dict],
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
) -> list[str]:
    """Reequilibra domingos moviendo el único descanso semanal, nunca duplicándolo.

    Se ejecuta después de máximo 7 y fatiga. Si una reparación superior movió
    un descanso hacia o desde domingo, esta fase intenta recuperar el rango
    mensual mediante intercambios atómicos dentro de la misma semana. Un cambio
    se conserva solo si no empeora máximo 7/fatiga, mantiene cobertura y no crea
    coincidencia de pareja.
    """
    if not horario:
        return []
    domingos=fechas_domingos(horario)
    if not domingos:
        return []
    minimo=len(domingos)//2
    # Con la regla estricta el objetivo es exactamente la mitad hacia abajo:
    # de cinco domingos se trabajan dos y se descansan tres. Sin ella se
    # admitía el redondeo hacia arriba, y entonces esta fase daba por bueno un
    # reparto que la validación final sí contaba como desviación.
    maximo=minimo if DOMINGOS_MITAD_EXACTA else minimo+(len(domingos)%2)
    avisos=[]
    trasladables={
        'descanso_automatico','descanso_max_6_dias','descanso_fatiga_laboral',
        'descanso_domingo','descanso_domingo_reubicado','descanso_fijo',
    }

    def _higher_conflicts() -> tuple[int,int]:
        return (
            (_contar_violaciones_max_dias(horario,dias_previos)),
            len(_violaciones_fatiga_laboral(horario,dias_previos)),
        )

    def _intercambio_dominical_coordinado(e: dict, trabajados: int, antes: tuple[int, int]) -> list[str] | None:
        """Mueve varios descansos de una persona como una sola transacción.

        Hay configuraciones donde trasladar solo una semana a domingo une una
        racha a ambos lados y parece inválido, aunque trasladar simultáneamente
        dos semanas sí conserve máximo 7, fatiga y cobertura. El reparador
        individual no puede atravesar ese estado intermedio. Este paso explora
        únicamente las combinaciones mínimas necesarias y revierte por completo
        cualquier intento que no mejore el balance.
        """
        necesarios = max(0, trabajados - maximo)
        if necesarios <= 0:
            return None
        opciones: list[tuple[dict, Optional[dict]]] = []
        try:
            ingreso = date.fromisoformat(str(e.get('vigente_desde') or '')[:10])
        except ValueError:
            ingreso = None
        for fecha_domingo in domingos:
            dom = _dia(e, fecha_domingo)
            if not dom or dom.get('turno') not in {'AM', 'PM'} or dom.get('bloqueado'):
                continue
            lunes = str(dom.get('lunes_semana') or _lunes_iso_de_dia(dom))
            descansos_semana = [
                x for x in e.get('dias', [])
                if x is not dom
                and str(x.get('lunes_semana') or '') == lunes
                and x.get('turno') == 'D'
                and _es_descanso_semanal(x)
            ]
            descansos = [
                x for x in descansos_semana
                if x.get('origen') in trasladables
                and not x.get('preservado_parcial')
            ]
            if len(descansos) == 1:
                opciones.append((dom, descansos[0]))
            elif not descansos_semana:
                # La primera semana parcial puede tener su tramo anterior en el
                # mes oficial previo. Si tampoco allí existe un día no laborado
                # dentro de esta semana (o la persona acaba de ingresar), el
                # domingo puede convertirse en su único descanso ordinario sin
                # crear un segundo D.
                lunes_fecha = date.fromisoformat(lunes)
                prev = (dias_previos or {}).get(int(e.get('empleado_id') or 0))
                prev_items = prev if isinstance(prev, list) else ([prev] if prev else [])
                descanso_previo = any(
                    str(x.get('turno') or '') in NONWORK_CODES
                    and lunes_fecha <= date.fromisoformat(str(x.get('fecha') or '')) <= date.fromisoformat(fecha_domingo)
                    for x in prev_items
                    if x.get('fecha')
                )
                ingreso_en_semana = ingreso is not None and lunes_fecha <= ingreso <= date.fromisoformat(fecha_domingo)
                if ingreso_en_semana or not descanso_previo:
                    opciones.append((dom, None))
        if len(opciones) < necesarios:
            return None

        for seleccion in limitar(
            combinations(opciones, necesarios), MAX_COMBINACIONES_REPARACION
        ):
            snap = _snapshot_estado_horario(horario)
            movimientos: list[tuple[str, str]] = []
            valido = True
            for dom, descanso_actual in seleccion:
                origen = descanso_actual.get('fecha') if descanso_actual else 'inicio de vigencia'
                if descanso_actual is not None:
                    if not _restore_base_work(descanso_actual):
                        valido = False
                        break
                    turno_restaurado = descanso_actual.get('turno')
                    if (
                        turno_restaurado in {'AM', 'PM'}
                        and _conflicto_pareja_para_turno(
                            horario, e, descanso_actual['fecha'], turno_restaurado
                        )
                    ):
                        valido = False
                        break
                _asignar_d(
                    dom,
                    'descanso_domingo',
                    'Descanso semanal trasladado mediante balance dominical coordinado',
                )
                movimientos.append((str(origen), str(dom.get('fecha'))))
            if valido:
                # Trasladar un descanso a domingo puede dejar un turno del área
                # por debajo de su mínimo. Antes de descartar la combinación se
                # intenta repartir la cobertura dentro de la misma área.
                fechas_afectadas = [str(dom.get('fecha')) for dom, _x in seleccion]
                valido = (
                    _asegurar_cobertura_minima(horario, fechas_afectadas)
                    if _reparto_fijado(str(e.get('area') or ''), fechas_afectadas[0] if fechas_afectadas else None)
                    else True
                )
            if valido:
                domingos_despues = sum(
                    1 for fecha_domingo in domingos
                    if (_dia(e, fecha_domingo) or {}).get('turno') in WORK_CODES
                )
                conflictos = _higher_conflicts()
                valido = (
                    minimo <= domingos_despues <= maximo
                    and conflictos[0] <= antes[0]
                    and conflictos[1] <= antes[1]
                    and _cobertura_area_completa(horario)
                )
            if valido:
                return [
                    f"{e['nombre']}: balance dominical coordinado; el descanso semanal se trasladó de {origen} al domingo {destino} sin crear descansos adicionales."
                    for origen, destino in movimientos
                ]
            _restore_estado_horario(snap)
        return None

    def _mover_unico_descanso_a_domingo(e: dict, fecha_domingo: str) -> tuple[bool, str]:
        dom = _dia(e, fecha_domingo)
        if not dom or dom.get('turno') not in {'AM', 'PM'} or dom.get('bloqueado'):
            return False, ''
        lunes = str(dom.get('lunes_semana') or _lunes_iso_de_dia(dom))
        descansos_semana = [
            x for x in e.get('dias', [])
            if x is not dom and str(x.get('lunes_semana') or '') == lunes
            and x.get('turno') == 'D' and _es_descanso_semanal(x)
        ]
        descansos = [
            x for x in descansos_semana
            if x.get('origen') in trasladables and not x.get('preservado_parcial')
        ]
        origen = 'inicio de vigencia'
        if len(descansos) == 1:
            origen = str(descansos[0].get('fecha'))
            if not _restore_base_work(descansos[0]):
                return False, ''
            turno = descansos[0].get('turno')
            if turno in {'AM', 'PM'} and _conflicto_pareja_para_turno(
                horario, e, descansos[0]['fecha'], turno
            ):
                return False, ''
        elif descansos_semana:
            return False, ''
        else:
            lunes_fecha = date.fromisoformat(lunes)
            prev = (dias_previos or {}).get(int(e.get('empleado_id') or 0))
            prev_items = prev if isinstance(prev, list) else ([prev] if prev else [])
            if any(
                str(x.get('turno') or '') in NONWORK_CODES
                and lunes_fecha <= date.fromisoformat(str(x.get('fecha') or '')) <= date.fromisoformat(fecha_domingo)
                for x in prev_items if x.get('fecha')
            ):
                return False, ''
        _asignar_d(dom, 'descanso_domingo', 'Descanso semanal trasladado mediante permuta dominical de área')
        return True, origen

    def _permuta_domingos_entre_personas() -> list[str]:
        """Intercambia domingos de dos personas como una sola operación.

        Permite que quien cubre todos los domingos tome los descansos de otra
        persona del mismo turno, mientras esa segunda persona traslada los suyos
        a domingos diferentes. La cobertura nunca se evalúa en el estado
        intermedio; solo se confirma la permuta completa.
        """
        elegibles = [
            e for e in horario
            if e.get('tipo_turno') != 'administrativo'
            and e.get('descanso_fijo') is None
            and not e.get('exento_especiales')
        ]
        avisos_permuta: list[str] = []
        for sobrecargado in elegibles:
            if presupuesto_agotado():
                break
            trabaja_s = [f for f in domingos if (_dia(sobrecargado, f) or {}).get('turno') in WORK_CODES]
            faltan = len(trabaja_s) - maximo
            if faltan <= 0:
                continue
            solucion = False
            for donante in elegibles:
                if donante is sobrecargado:
                    continue
                descansa_d = [
                    f for f in domingos
                    if (_dia(donante, f) or {}).get('turno') == 'D'
                    and (_dia(donante, f) or {}).get('origen') in trasladables
                ]
                trabaja_d = [f for f in domingos if (_dia(donante, f) or {}).get('turno') in WORK_CODES]
                cede = [f for f in descansa_d if f in trabaja_s]
                recibe = [f for f in trabaja_d if f in trabaja_s]
                if len(cede) < faltan or len(recibe) < faltan:
                    continue
                for domingos_cedidos in limitar(
                    combinations(cede, faltan), MAX_COMBINACIONES_REPARACION
                ):
                    for domingos_recibidos in limitar(
                        combinations([f for f in recibe if f not in domingos_cedidos], faltan),
                        MAX_COMBINACIONES_REPARACION,
                    ):
                        snap = _snapshot_estado_horario(horario)
                        antes = _higher_conflicts()
                        movimientos: list[str] = []
                        destinos_donante: list[list[dict]] = []
                        valido = True

                        # El donante libera los domingos que cede y después
                        # ubicará su descanso en otro día de esas mismas semanas.
                        for f in domingos_cedidos:
                            dom = _dia(donante, f)
                            if (
                                not dom or dom.get('turno') != 'D'
                                or dom.get('origen') not in trasladables
                                or not _restore_base_work(dom)
                            ):
                                valido = False
                                break
                            turno = dom.get('turno')
                            if turno in {'AM', 'PM'} and _conflicto_pareja_para_turno(
                                horario, donante, f, turno
                            ):
                                valido = False
                                break
                            lunes = str(dom.get('lunes_semana') or _lunes_iso_de_dia(dom))
                            opciones_semana = [
                                x for x in donante.get('dias', [])
                                if x is not dom and str(x.get('lunes_semana') or '') == lunes
                                and not x.get('es_domingo') and not x.get('es_festivo')
                                and x.get('turno') in {'AM', 'PM'} and _admite_descanso(x)
                            ]
                            if not opciones_semana:
                                valido = False
                                break
                            destinos_donante.append(opciones_semana)
                        if valido:
                            for f in domingos_cedidos:
                                ok, origen = _mover_unico_descanso_a_domingo(sobrecargado, f)
                                if not ok:
                                    valido = False
                                    break
                                movimientos.append(f"{sobrecargado['nombre']}: {origen} → {f}")
                        if valido:
                            for f in domingos_recibidos:
                                ok, origen = _mover_unico_descanso_a_domingo(donante, f)
                                if not ok:
                                    valido = False
                                    break
                                movimientos.append(f"{donante['nombre']}: {origen} → {f}")
                        if not valido:
                            _restore_estado_horario(snap)
                            continue

                        preparado = _snapshot_estado_horario(horario)
                        for destinos in limitar(
                            product(*destinos_donante), MAX_COMBINACIONES_REPARACION
                        ):
                            _restore_estado_horario(preparado)
                            if len({d['fecha'] for d in destinos}) != len(destinos):
                                continue
                            # El nuevo descanso del donante también puede
                            # necesitar que otra persona del área cubra su turno
                            # ese día; con repartos como 2 AM + 1 PM es lo
                            # habitual. Se intenta dentro de la misma área.
                            posible = True
                            for d in destinos:
                                if _reparto_fijado(donante.get('area'), d.get('fecha')):
                                    habilitado, _reajuste = _habilitar_descanso_con_reajuste_cobertura(
                                        horario, donante, d, 'el balance de domingos'
                                    )
                                else:
                                    habilitado = _puede_descansar(horario, donante, d)
                                if not habilitado:
                                    posible = False
                                    break
                            if not posible:
                                continue
                            for d in destinos:
                                _asignar_d(
                                    d,
                                    'descanso_domingo_reubicado',
                                    'Descanso semanal reubicado durante permuta dominical de área',
                                )
                            # Repartir los domingos puede dejar una fecha de
                            # Comunicaciones sin PM. Antes de descartar la
                            # permuta se intenta cubrirla dentro de la misma
                            # área, que es justamente lo que exige alternar la
                            # responsabilidad del único PM.
                            if not _asegurar_cobertura_minima(
                                horario, sorted(set(domingos_cedidos) | set(domingos_recibidos))
                            ):
                                continue
                            conteo_s = sum(1 for f in domingos if (_dia(sobrecargado, f) or {}).get('turno') in WORK_CODES)
                            conteo_d = sum(1 for f in domingos if (_dia(donante, f) or {}).get('turno') in WORK_CODES)
                            despues = _higher_conflicts()
                            if (
                                minimo <= conteo_s <= maximo
                                and minimo <= conteo_d <= maximo
                                and despues[0] <= antes[0]
                                and despues[1] <= antes[1]
                                and _cobertura_area_completa(horario)
                            ):
                                avisos_permuta.append(
                                    'Permuta dominical coordinada entre '
                                    f"{sobrecargado['nombre']} y {donante['nombre']}: "
                                    + '; '.join(movimientos)
                                    + '. Se conservaron cobertura, fatiga y máximo 7.'
                                )
                                solucion = True
                                break
                        if solucion:
                            break
                        _restore_estado_horario(snap)
                    if solucion:
                        break
                if solucion:
                    break
        return avisos_permuta

    for e in horario:
        if e.get('tipo_turno')=='administrativo' or e.get('descanso_fijo') is not None or e.get('exento_especiales'):
            continue
        # Los domingos de esta persona son los que caen dentro de su vigencia.
        # Quien entra el día 8 solo alcanza dos de los cuatro del mes, y su
        # reparto es «trabaja uno, descansa uno». Medirlo sobre el mes entero
        # daba por bueno que trabajase los dos: el reparto salía cuadrado aquí
        # y la validación final lo marcaba como desviación, sin que nadie
        # hubiera intentado arreglarlo.
        domingos_e = [
            f for f in domingos
            if (x := _dia(e, f)) and x.get('vigente', True)
            and x.get('turno') != OUT_OF_VIGENCY_CODE
        ]
        if not domingos_e:
            continue
        minimo_e = len(domingos_e) // 2
        maximo_e = minimo_e if DOMINGOS_MITAD_EXACTA else minimo_e + (len(domingos_e) % 2)
        for _ in range(len(domingos_e)+2):
            trabajados=sum(1 for f in domingos_e if (_dia(e,f) or {}).get('turno') in WORK_CODES)
            if minimo_e <= trabajados <= maximo_e:
                break
            antes=_higher_conflicts()
            progreso=False

            if trabajados > maximo_e:
                # Trabaja demasiados domingos: mover el descanso ordinario de
                # esa semana al domingo, restaurando primero su ubicación actual.
                candidatos=[]
                for f in domingos_e:
                    dom=_dia(e,f)
                    if not dom or dom.get('turno') not in {'AM','PM'} or not _admite_descanso(dom):
                        continue
                    lunes=str(dom.get('lunes_semana') or _lunes_iso_de_dia(dom))
                    descansos=[x for x in e.get('dias',[]) if x is not dom and str(x.get('lunes_semana') or '')==lunes and x.get('turno')=='D' and _es_descanso_semanal(x) and x.get('origen') in trasladables]
                    if descansos:
                        candidatos.append((f,dom,descansos))
                # Preferir el domingo más tardío para alterar lo mínimo posible la continuidad previa.
                candidatos.sort(key=lambda x:x[0], reverse=True)
                for f,dom,descansos in candidatos:
                    snap=_snapshot_estado_horario(horario)
                    origen_desc=sorted(descansos,key=lambda x:x.get('fecha',''),reverse=True)[0]
                    if not _restore_base_work(origen_desc):
                        _restore_estado_horario(snap)
                        continue
                    turno_restaurado=origen_desc.get('turno')
                    if turno_restaurado in {'AM','PM'} and _conflicto_pareja_para_turno(horario,e,origen_desc['fecha'],turno_restaurado):
                        _restore_estado_horario(snap)
                        continue
                    if not _puede_descansar(horario,e,dom):
                        _restore_estado_horario(snap)
                        continue
                    _asignar_d(dom,'descanso_domingo','Descanso semanal trasladado al domingo para equilibrar los domingos trabajados')
                    despues=_higher_conflicts()
                    if despues[0] > antes[0]:
                        # El intercambio dominical puede unir dos rachas a
                        # ambos lados del antiguo descanso. Antes de renunciar
                        # al balance, repara de forma atómica el descanso de la
                        # semana adyacente dentro de esta misma área. El cambio
                        # completo solo se conserva si el domingo objetivo
                        # sigue en D y desaparece la nueva violación.
                        dom['protegido_balance_dominical'] = True
                        try:
                            err_coordinado,_ = reparar_max_dias_consecutivos(horario,dias_previos)
                        finally:
                            dom.pop('protegido_balance_dominical', None)
                        despues=_higher_conflicts()
                        if err_coordinado or dom.get('turno')!='D':
                            _restore_estado_horario(snap)
                            continue
                    if despues[1] > antes[1]:
                        # Si el descanso dominical ya quedó coordinado con las
                        # semanas vecinas pero expuso un PM→AM, no se devuelve
                        # de inmediato el descanso al lunes (eso desharía el
                        # balance). Tras agotar el intercambio de descansos,
                        # se permite el puente ADM como última opción.
                        codigo_adm=_codigo_guia_area(str(e.get('area') or '')) if PUENTE_ADM_FATIGA else None
                        for violacion in _violaciones_fatiga_laboral([e],dias_previos):
                            dia_am=violacion.get('dia_am')
                            if not codigo_adm or not dia_am or dia_am.get('bloqueado'):
                                continue
                            fecha_pm=violacion.get('fecha_pm')
                            fecha_am=violacion.get('fecha_am')
                            dia_am.update(
                                turno=codigo_adm,
                                origen='puente_fatiga_administrativo',
                                bloqueado=True,
                                observacion=(
                                    f'Puente administrativo de último recurso para conservar balance dominical: '
                                    f'{fecha_pm} PM → {fecha_am} {codigo_adm} → siguiente jornada AM'
                                ),
                                cobertura_operativa='AM' if codigo_adm == 'ADM-GS' else None,
                                turno_operativo_origen='AM',
                                fatiga_desde=fecha_pm,
                                fatiga_hacia=fecha_am,
                            )
                        despues=_higher_conflicts()
                    if despues[0] > antes[0] or despues[1] > antes[1]:
                        _restore_estado_horario(snap)
                        continue
                    avisos.append(f"{e['nombre']}: el descanso semanal se trasladó de {origen_desc['fecha']} al domingo {f} para recuperar el balance mensual sin crear un segundo descanso.")
                    progreso=True
                    break

            else:
                # Trabaja pocos domingos: sacar un descanso dominical hacia otro
                # día editable de la misma semana. Sigue existiendo exactamente un D.
                candidatos=[]
                for f in domingos_e:
                    dom=_dia(e,f)
                    if not dom or dom.get('turno')!='D' or dom.get('origen') not in trasladables or dom.get('preservado_parcial'):
                        continue
                    candidatos.append((f,dom))
                candidatos.sort(key=lambda x:x[0], reverse=True)
                for f,dom in candidatos:
                    snap=_snapshot_estado_horario(horario)
                    if not _restore_base_work(dom):
                        _restore_estado_horario(snap)
                        continue
                    turno_dom=dom.get('turno')
                    if turno_dom in {'AM','PM'} and _conflicto_pareja_para_turno(horario,e,dom['fecha'],turno_dom):
                        _restore_estado_horario(snap)
                        continue
                    lunes=str(dom.get('lunes_semana') or _lunes_iso_de_dia(dom))
                    destinos=[
                        x for x in e.get('dias',[])
                        if x is not dom and str(x.get('lunes_semana') or '')==lunes
                        and not x.get('es_festivo') and not x.get('es_domingo')
                        and x.get('turno') in {'AM','PM'} and _admite_descanso(x)
                    ]
                    destinos.sort(key=lambda x:(-_conteo_turno(horario,e['area'],x['fecha'],x['turno']),x['fecha']))
                    elegido=None
                    for dest in destinos:
                        if _puede_descansar(horario,e,dest):
                            _asignar_d(dest,'descanso_domingo_reubicado',f'Descanso semanal trasladado desde el domingo {f} para equilibrar los domingos trabajados')
                            despues=_higher_conflicts()
                            if despues[0] <= antes[0] and despues[1] <= antes[1]:
                                elegido=dest
                                break
                            _restore_estado_horario(snap)
                            # hay que volver a restaurar domingo antes de probar otro destino
                            if not _restore_base_work(dom):
                                break
                        else:
                            continue
                    if elegido is not None:
                        avisos.append(f"{e['nombre']}: el descanso del domingo {f} se trasladó al {elegido['fecha']} para recuperar el balance mensual sin duplicar descansos.")
                        progreso=True
                        break
                    _restore_estado_horario(snap)

            if not progreso and trabajados > maximo_e:
                # Una semana que la persona no vive entera —entra el martes o se
                # retira el jueves— no lleva descanso asignado, así que no hay
                # ninguno que mover al domingo. Si esa semana no tiene descanso
                # y el domingo se puede librar, se coloca ahí: no es un descanso
                # de más, es el único de esa semana, y además cuadra su reparto.
                for f in sorted(domingos_e, reverse=True):
                    dom = _dia(e, f)
                    if not dom or dom.get('turno') not in {'AM', 'PM'} or not _admite_descanso(dom):
                        continue
                    lunes = str(dom.get('lunes_semana') or _lunes_iso_de_dia(dom))
                    if _cuenta_descansos_semanales(e, lunes):
                        continue
                    snap = _snapshot_estado_horario(horario)
                    if not _puede_descansar(horario, e, dom):
                        _restore_estado_horario(snap)
                        continue
                    _asignar_d(
                        dom, 'descanso_domingo',
                        'Descanso semanal de una semana incompleta, colocado en domingo '
                        'para cuadrar el reparto dominical',
                    )
                    despues = _higher_conflicts()
                    if despues[0] > antes[0] or despues[1] > antes[1]:
                        _restore_estado_horario(snap)
                        continue
                    avisos.append(
                        f"{e['nombre']}: el descanso de la semana del {lunes} se colocó en el "
                        f"domingo {f}; esa semana no la trabaja entera y así le cuadra el "
                        'reparto de domingos.'
                    )
                    progreso = True
                    break

            if not progreso:
                coordinado = _intercambio_dominical_coordinado(e, trabajados, antes)
                if coordinado:
                    avisos.extend(coordinado)
                    progreso = True
                else:
                    # La validación final explicará el balance no alcanzable. No
                    # se fuerza una solución peor que rompa una regla superior.
                    break
    avisos.extend(_permuta_domingos_entre_personas())
    return sorted(set(avisos))

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
