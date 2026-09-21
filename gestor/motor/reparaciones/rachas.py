"""Rachas: responsabilidad separada de gestor/motor/reparacion.py."""
from __future__ import annotations

from datetime import date, timedelta
from itertools import product
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
    MAX_COMBINACIONES_REPARACION,
    MAX_COMBINACIONES_SOLVER_AREA,
    limitar,
    presupuesto_agotado,
    queda_presupuesto,
)
from gestor.motor.reparaciones.base import (
    PUENTE_ADM_FATIGA,
    _cobertura_area_completa,
    _contar_violaciones_max_dias,
    _firma_estado_turnos,
    _habilitar_descanso_max6_con_reajuste,
    _restaurar_descanso_automatico_de_semana,
    _restore_base_work,
    _restore_estado_horario,
    _snapshot_estado_horario,
)
from gestor.motor.vocabulario import (  # noqa: F401
    _CACHE_ORDEN_FIRMA,
    DOMINGOS_MITAD_EXACTA,
    NONWORK_CODES,
    OUT_OF_VIGENCY_CODE,
    WORK_CODES,
)


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
