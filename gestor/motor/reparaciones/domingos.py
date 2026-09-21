"""Domingos: responsabilidad separada de gestor/motor/reparacion.py."""
from __future__ import annotations

from datetime import date
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
from gestor.motor.presupuesto import (
    MAX_COMBINACIONES_REPARACION,
    limitar,
    presupuesto_agotado,
)
from gestor.motor.reparaciones.base import (
    PUENTE_ADM_FATIGA,
    _admite_descanso,
    _cobertura_area_completa,
    _contar_violaciones_max_dias,
    _restore_base_work,
    _restore_estado_horario,
    _snapshot_estado_horario,
)
from gestor.motor.reparaciones.cobertura import (
    _asegurar_cobertura_minima,
)
from gestor.motor.reparaciones.rachas import (
    reparar_max_dias_consecutivos,
)
from gestor.motor.vocabulario import (  # noqa: F401
    _CACHE_ORDEN_FIRMA,
    DOMINGOS_MITAD_EXACTA,
    NONWORK_CODES,
    OUT_OF_VIGENCY_CODE,
    WORK_CODES,
)


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
