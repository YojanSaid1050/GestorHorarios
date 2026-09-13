# -*- coding: utf-8 -*-
"""5 · Decir qué salió bien y qué no.

Recorre el mes ya armado y devuelve los errores y las advertencias, sin
tocar nada. Es lo que alimenta la pantalla de Validación.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from gestor.dominio import nucleo as nucleo_normativo
from gestor.motor.comun import (  # noqa: F401
    _codigo_administrativo_area,
    _conteo_area,
    _cuenta_como_cobertura,
    _dia,
    _es_descanso_semanal,
    _es_excepcion_turno,
    _es_ultimo_viernes_administrativo,
    _historial_semana,
    _semana_sin_jornada,
    _semanas,
    _turnos_cobertura_dia,
    _violaciones_cambio_semanal,
    _violaciones_fatiga_laboral,
    _violaciones_max_dias_consecutivos,
    clasificar_violacion_max7,
    fechas_domingos,
    fechas_festivos,
    maximo_cobertura,
    maximo_dias_consecutivos,
    minimo_area_cobertura,
    minimo_cobertura,
)

# Cómo se le cuenta a una persona un aviso de validación vive en su propio
# módulo: son ciento catorce líneas de texto que no dependen del horario.
from gestor.motor.vocabulario import (  # noqa: F401
    _BALANCE_DOMINICAL_FLEXIBLE,
    ALL_CODES,
    DOMINGOS_MITAD_EXACTA,
    OUT_OF_VIGENCY_CODE,
    WORK_CODES,
)


def balance_dominical_es_flexible() -> bool:
    return bool(_BALANCE_DOMINICAL_FLEXIBLE.get())

def validar_horario(
    horario:list[dict],
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
    historial_no_laborados: Optional[dict[int, dict[str, set[int]]]] = None,
    historial_descansos_especiales: Optional[dict[int, dict[str, set[int]]]] = None,
    turnos_previos: Optional[dict[int, str]] = None,
    dias_previos_fatiga: Optional[dict[int, dict | list[dict]]] = None,
) -> tuple[list[str],list[str]]:
    errores=[]
    avisos=[]
    # códigos y administrativos
    for e in horario:
        for d in e['dias']:
            if d['turno'] not in ALL_CODES:
                errores.append(f"{e['nombre']}: código inválido {d['turno']} el {d['fecha']}.")
            if d.get('turno') == OUT_OF_VIGENCY_CODE or not d.get('vigente', True):
                continue
            # Un día heredado ocurrió bajo la configuración de SU mes: la
            # persona podía tener entonces otro tipo de turno, otro descanso
            # fijo o incluso otra área. Ya se validó allí y aquí no se puede
            # cambiar, así que juzgarlo con las reglas de hoy solo produce
            # conflictos que nadie puede resolver. Las reglas que abarcan
            # varios días —descanso semanal, máximo de jornadas seguidas,
            # fatiga y cobertura— sí lo siguen teniendo en cuenta.
            if d.get('heredado'):
                continue
            if e['tipo_turno']=='administrativo':
                codigo_administrativo = _codigo_administrativo_area(e.get('area'))
                es_actividad_directa = d.get('origen') in {'requerimiento:actividad','requerimiento:asignacion_administrativa'}
                es_viernes_general = d.get('origen') == 'ultimo_viernes_administrativo' and d.get('turno') == 'ADM-GS'
                descanso_reubicado = d.get('origen') == 'descanso_administrativo_reubicado_actividad'
                if (d['es_domingo'] or d['es_festivo']) and d['turno'] not in {'D','VAC','INC','PER','CAP'}:
                    if not (es_actividad_directa and d['turno'] == codigo_administrativo):
                        errores.append(f"{e['nombre']}: administrativo debe descansar el {d['fecha']} por domingo/festivo.")
                if not (d['es_domingo'] or d['es_festivo']) and d['turno'] not in {codigo_administrativo,'VAC','INC','PER','CAP'}:
                    if es_viernes_general:
                        continue
                    if not (descanso_reubicado and d['turno'] == 'D'):
                        errores.append(
                            f"{e['nombre']} es personal administrativo permanente: el {d['fecha']} "
                            f"solo puede llevar {codigo_administrativo} (o una ausencia aprobada), "
                            f"y quedó como {d['turno']}. Los administrativos no cubren turnos AM/PM."
                        )
    # Fatiga laboral PM→AM: una transición pendiente en este punto significa
    # que no pudo repararse automáticamente o fue fijada por una decisión explícita.
    for v in _violaciones_fatiga_laboral(horario, dias_previos_fatiga):
        e = v['empleado']
        errores.append(
            f"Fatiga laboral: {e['nombre']} termina PM el {v['fecha_pm']} y pasaría a AM el {v['fecha_am']} "
            "sin D/VAC/INC/PER ni un puente administrativo ADM entre ambas jornadas."
        )

    # Máximo siete jornadas consecutivas. Una racha totalmente fijada por
    # decisiones ya autorizadas se reporta como excepción visible, no como
    # error que bloquee el mes completo.
    for v in _violaciones_max_dias_consecutivos(horario, dias_previos_fatiga, detallado=True):
        nivel, mensaje = clasificar_violacion_max7(v, horario)
        if nivel == 'error':
            errores.append(
                f"Máximo {maximo_dias_consecutivos()} días consecutivos: {v['empleado']['nombre']} llegaría a "
                f"{maximo_dias_consecutivos() + 1} jornadas seguidas el {v['fecha']} ({', '.join(v['racha'])}). "
                'Debe existir un día no laborado antes de continuar.'
            )
        else:
            avisos.append(mensaje)

    # cobertura diaria
    if horario:
        for base in horario[0]['dias']:
            f=base['fecha']
            # El último viernes es una jornada administrativa corporativa para
            # todas las áreas; por diseño no exige cobertura operativa AM/PM.
            if _es_ultimo_viernes_administrativo(base):
                continue
            for area_cobertura, nombre_area in (
                ('gestion_social', 'Gestión Social'),
                ('comunicaciones', 'Comunicaciones'),
                ('atencion_ciudadano', 'Atención al Ciudadano'),
            ):
                personas = [e for e in horario if e['area'] == area_cobertura]
                if not personas:
                    continue
                # Un día heredado se decidió y se publicó con el mes anterior.
                # Este período no puede cambiarlo, así que lo que venga mal de
                # ahí se avisa —para que se vea— pero no impide programar el mes.
                heredado_dia = any((_dia(e, f) or {}).get('heredado') for e in personas)
                anotar_cobertura = avisos.append if heredado_dia else errores.append
                sufijo_heredado = (
                    ' Viene del mes anterior ya publicado, así que este período no puede cambiarlo.'
                    if heredado_dia else ''
                )
                for turno in ('AM', 'PM'):
                    exigido = minimo_cobertura(horario, area_cobertura, turno, f)
                    if exigido <= 0:
                        continue
                    # Quien no cubre ese día de la semana no cuenta para el
                    # mínimo, aunque esté trabajando. Este conteo se había
                    # quedado fuera: `_conteo_turno` y `_conteo_area` sí lo
                    # miraban, pero la validación por turno no, que es justo la
                    # regla de Gestión Social —la que motivó la función—.
                    presentes = sum(
                        1 for e in personas
                        if turno in _turnos_cobertura_dia(_dia(e, f))
                        and _cuenta_como_cobertura(e, _dia(e, f))
                    )
                    if presentes < exigido:
                        anotar_cobertura(
                            f'{nombre_area} tiene {presentes} persona(s) {turno} el {f}; '
                            f'el mínimo obligatorio es {exigido}.' + sufijo_heredado
                        )
                # Techo por turno: el área tampoco puede amontonar en una
                # franja más gente de la que su regla admite. Es lo que impide
                # que diez personas rotativas acaben las diez en AM.
                #
                # No se aplica a los días heredados: ese día ya se decidió y se
                # publicó con el periodo anterior, y este mes no puede
                # cambiarlo. Exigirle el techo de hoy sería reprochar al mes
                # una decisión que no tomó y que además no puede deshacer.
                heredado_area = any(
                    (_dia(e, f) or {}).get('heredado') for e in personas
                )
                for turno in ('AM', 'PM') if not heredado_area else ():
                    tope = maximo_cobertura(horario, area_cobertura, turno, f)
                    if tope is None:
                        continue
                    presentes = 0
                    autorizados = 0
                    for e in personas:
                        dia = _dia(e, f)
                        if turno not in _turnos_cobertura_dia(dia):
                            continue
                        presentes += 1
                        # Una asignación, una excepción de turno o un cambio
                        # aprobado son decisiones explícitas del usuario. El
                        # techo describe cómo reparte el área por su cuenta, no
                        # una prohibición que anule lo que alguien ya decidió.
                        if _es_excepcion_turno(dia):
                            autorizados += 1
                    if presentes - autorizados > tope:
                        errores.append(
                            f'{nombre_area} tiene {presentes} persona(s) {turno} el {f}; '
                            f'el máximo admitido en ese turno es {tope}.'
                        )
                    elif presentes > tope:
                        # El exceso lo causan decisiones explícitas, así que no
                        # bloquea: se hace lo que se pidió. Y tampoco se corrige
                        # sola moviendo a otra persona ese día, porque el turno
                        # es estable dentro de la semana y cambiarlo un miércoles
                        # rompería esa regla para arreglar un máximo que la
                        # propia operación acaba de decidir saltarse. Lo que sí
                        # tiene que pasar es que se vea.
                        avisos.append(
                            f'{nombre_area} tiene {presentes} persona(s) {turno} el {f} y su máximo '
                            f'es {tope}: el exceso viene de asignaciones directas, que mandan sobre '
                            'el reparto. Revisa si el máximo del área sigue siendo el correcto.'
                        )
                # Suelo del área: en Comunicaciones y en Atención al Ciudadano
                # no importa el turno, sino que quede alguien trabajando.
                exigido_area = minimo_area_cobertura(horario, area_cobertura, f)
                if exigido_area > 0:
                    trabajando = _conteo_area(horario, area_cobertura, f)
                    if trabajando < exigido_area:
                        anotar_cobertura(
                            f'{nombre_area} se queda con {trabajando} persona(s) trabajando el {f}; '
                            f'el mínimo obligatorio del área es {exigido_area}, en AM o en PM.'
                            + sufijo_heredado
                        )
    # pareja PC
    por_id={e['empleado_id']:e for e in horario}
    revisadas=set()
    for e in horario:
        pid=e.get('pareja_id')
        if not pid or pid not in por_id:
            continue
        p=por_id[pid]
        clave=tuple(sorted((e['empleado_id'],pid)))
        if clave in revisadas:
            continue
        revisadas.add(clave)
        # Dos personas emparejadas tienen el mismo calendario. Si alguna vez
        # no lo tuvieran, comparar día a día estaría cotejando fechas
        # distintas y la coincidencia de turnos saldría mal.
        for de, dp in zip(e['dias'], p['dias'], strict=True):
            if de['turno'] in {'AM','PM'} and dp['turno']==de['turno']:
                origenes={str(de.get('origen') or ''), str(dp.get('origen') or '')}
                # Un cambio de turno aprobado autoriza la coincidencia igual
                # que una asignación directa: en los dos casos alguien decidió
                # ese día a conciencia.
                autorizada_asignacion = any(
                    o.startswith(('requerimiento:', 'solicitud:turno_')) for o in origenes)
                autorizada_manual = bool(de.get('excepcion_forzada') or dp.get('excepcion_forzada'))
                if autorizada_asignacion or autorizada_manual:
                    avisos.append(
                        f"{e['nombre']} y {p['nombre']} coinciden en {de['turno']} el {de['fecha']}; la coincidencia está permitida porque proviene de una asignación o cambio manual explícito."
                    )
                    continue
                if de.get('heredado') and dp.get('heredado'):
                    avisos.append(
                        f"{e['nombre']} y {p['nombre']} coinciden en {de['turno']} el {de['fecha']} "
                        'y comparten PC. Ese día viene del mes anterior ya publicado, así que este '
                        'período no puede cambiarlo.'
                    )
                    continue
                errores.append(f"{e['nombre']} y {p['nombre']} coinciden en {de['turno']} el {de['fecha']} y comparten PC.")
    # descanso semanal y reglas de día libre
    primera_fecha = date.fromisoformat(horario[0]['dias'][0]['fecha']) if horario and horario[0].get('dias') else None
    ultima_fecha = date.fromisoformat(horario[0]['dias'][-1]['fecha']) if horario and horario[0].get('dias') else None
    for e in horario:
        if e['tipo_turno']=='administrativo':
            continue

        # Para descanso fijo la existencia del día libre está determinada por el
        # contrato incluso si cae fuera de la porción visible de una semana
        # partida entre dos meses.
        if e.get('descanso_fijo') is None:
            for lunes, dias in _semanas(e).items():
                lunes_fecha = date.fromisoformat(lunes)
                domingo_fecha = lunes_fecha + timedelta(days=6)
                dias_vigentes = [d for d in dias if d.get('vigente', True)]
                if not dias_vigentes:
                    continue
                inicio_laboral = date.fromisoformat(str(e.get('vigente_desde') or '2026-08-01')[:10])
                fin_laboral = date.fromisoformat(str(e['vigente_hasta'])[:10]) if e.get('vigente_hasta') else None
                semana_inicio_laboral_parcial = lunes_fecha < inicio_laboral <= domingo_fecha
                semana_fin_laboral_parcial = bool(fin_laboral and lunes_fecha <= fin_laboral < domingo_fecha)
                semana_inicial_parcial = bool(primera_fecha and lunes_fecha < primera_fecha)
                semana_final_parcial = bool(ultima_fecha and domingo_fecha > ultima_fecha)

                dias_que_cubren_descanso = [d for d in dias if _es_descanso_semanal(d)]
                # VAC/INC pueden abarcar varios días y satisfacen el descanso,
                # pero no son varios descansos semanales. Solo se controla la
                # duplicidad de celdas D ordinarias.
                descansos_ordinarios = [
                    d for d in dias_que_cubren_descanso
                    if d.get('turno') == 'D' and d.get('origen') != 'ajuste_manual'
                ]
                actual_descanso_semanal = (bool(dias_que_cubren_descanso)
                                           or _semana_sin_jornada(dias))
                previo_descanso_semanal = bool(_historial_semana(historial_no_laborados or historial_descansos, e, lunes))
                if len(descansos_ordinarios) > 1:
                    fechas_descanso = ', '.join(d['fecha'] for d in descansos_ordinarios)
                    heredados = [d for d in descansos_ordinarios if d.get('heredado')]
                    solicitados = [
                        d for d in descansos_ordinarios
                        if d.get('origen') == 'descanso_solicitado'
                    ]
                    actuales = [d for d in descansos_ordinarios if not d.get('heredado')]
                    # Una semana partida puede traer un D ya publicado del mes
                    # anterior y necesitar su único D dentro del nuevo período.
                    # El generador actual no puede mover el primero. No es un
                    # duplicado creado en este mes, pero sí debe explicarse.
                    if heredados and len(actuales) == 1:
                        origen_actual = (
                            'el descanso solicitado'
                            if solicitados else 'el descanso del nuevo período'
                        )
                        avisos.append(
                            f"{e['nombre']}: la semana del {lunes} conserva el descanso heredado "
                            f"del mes anterior y además {origen_actual} ({fechas_descanso}). "
                            'El día heredado ya fue publicado y no puede moverse desde este período; '
                            'la validación lo conserva como continuidad de frontera.'
                        )
                    else:
                        errores.append(
                            f"{e['nombre']}: tiene {len(descansos_ordinarios)} descansos semanales "
                            f"ordinarios en la semana del {lunes} ({fechas_descanso}). Debe conservar "
                            'uno solo; mueve o elimina el descanso duplicado.'
                        )
                if (
                    not semana_inicial_parcial
                    and not semana_final_parcial
                    and not semana_inicio_laboral_parcial
                    and not semana_fin_laboral_parcial
                    and not actual_descanso_semanal
                    and not previo_descanso_semanal
                ):
                    errores.append(
                        f"{e['nombre']}: no tiene descanso semanal ordinario en la semana del {lunes}. "
                        "Los descansos de festivo, compensatorios y extras son adicionales y no sustituyen este descanso."
                    )

        else:
            for d in e['dias']:
                if not d.get('vigente', True) or d.get('heredado'):
                    continue
                if d['dia_semana_numero']==e['descanso_fijo'] and d['turno'] not in {'D','VAC','INC','PER'}:
                    if d.get('origen') in {'requerimiento:actividad','requerimiento:asignacion_administrativa','ultimo_viernes_administrativo','ajuste_manual','solicitud:capacitacion'}:
                        semana = d.get('lunes_semana')
                        compensado = any(
                            x.get('lunes_semana') == semana and x.get('turno') == 'D'
                            and x.get('origen') in {'descanso_fijo_reubicado_actividad','descanso_fijo_reubicado_manual'}
                            for x in e['dias']
                        )
                        if compensado:
                            continue
                    errores.append(f"{e['nombre']}: incumple su descanso fijo el {d['fecha']}.")
    # Domingos y festivos se validan de forma independiente.
    if horario:
        domingos = fechas_domingos(horario)
        festivos = fechas_festivos(horario)
        for e in horario:
            if e['tipo_turno'] != 'administrativo' and e.get('descanso_fijo') is None and not e.get('exento_especiales'):
                domingos_vigentes = [f for f in domingos if (dia := _dia(e, f)) and dia.get('vigente', True)]
                objetivo_dom_e = len(domingos_vigentes) // 2
                max_dom_e = objetivo_dom_e + (0 if DOMINGOS_MITAD_EXACTA else len(domingos_vigentes) % 2)
                trabajados_dom = sum(1 for f in domingos_vigentes if _dia(e, f)['turno'] in WORK_CODES)
                if not (objetivo_dom_e <= trabajados_dom <= max_dom_e):
                    # El reparto de domingos es una regla estricta de la
                    # operación: mitad trabajados y mitad descansados, y con un
                    # número impar el que sobra se descansa. Con el máximo de
                    # jornadas seguidas en 10 se cumple siempre, así que un mes
                    # que no lo cumpla no se da por válido: se muestra como
                    # conflicto para que se resuelva o se autorice a mano.
                    objetivo_txt = (
                        str(objetivo_dom_e) if objetivo_dom_e == max_dom_e
                        else f'{objetivo_dom_e} a {max_dom_e}'
                    )
                    detalle = (
                        f"{e['nombre']}: trabaja {trabajados_dom} de {len(domingos_vigentes)} domingos dentro de su vigencia; "
                        f"debía trabajar {objetivo_txt} y descansar el resto. "
                        "El motor intentó reubicar el único descanso semanal sin romper el máximo de jornadas seguidas, "
                        "la fatiga ni la cobertura, y no encontró un intercambio válido."
                    )
                    tope_actual = maximo_dias_consecutivos()
                    if len(domingos_vigentes) == len(domingos) and balance_dominical_es_flexible():
                        # Ya se exploró el mes entero buscando un reparto que
                        # cuadrara y no lo hay. Antes que dejar el mes sin
                        # horario, se conserva como excepción explicada.
                        avisos.append(
                            detalle + ' No se encontró ningún reparto que lo cumpla sin romper '
                            'la fatiga, el máximo de jornadas seguidas o la cobertura. Queda como '
                            'excepción: abre una semana, amplía el máximo en Configuración o '
                            'autoriza el cambio a mano si quieres cuadrarlo.'
                        )
                    elif len(domingos_vigentes) == len(domingos) and tope_actual >= 10:
                        # Mes completo y con el máximo de jornadas seguidas en
                        # su valor normal: el reparto siempre tiene solución, así
                        # que el mes no se da por válido hasta resolverlo.
                        errores.append(
                            detalle + ' Revisa una semana abierta, amplía el máximo de jornadas seguidas '
                            'en Configuración o autoriza una excepción a mano.'
                        )
                    elif len(domingos_vigentes) == len(domingos):
                        # El margen para mover el descanso lo da el máximo de
                        # jornadas seguidas. Con el máximo por debajo de diez el
                        # reparto puede no tener solución, y eso es consecuencia
                        # de una decisión del usuario: se avisa y el horario
                        # sigue adelante en vez de dejar el mes sin poder
                        # generarse.
                        avisos.append(
                            detalle + f' El máximo de jornadas seguidas está en {tope_actual}: con menos de '
                            'diez no siempre hay sitio donde mover el descanso. Súbelo en Configuración '
                            'o autoriza una excepción a mano.'
                        )
                    else:
                        # Quien entra o sale a mitad de mes solo alcanza un
                        # trozo de los domingos: el reparto mensual no se le
                        # puede exigir entero, así que queda como aviso.
                        avisos.append(
                            detalle + ' Su vigencia no cubre el mes completo, así que el reparto mensual '
                            'no se le puede exigir entero: queda como aviso para que lo revises.'
                        )

            if e['tipo_turno'] == 'administrativo':
                continue
            for f in festivos:
                dia_festivo = _dia(e, f)
                if not dia_festivo or not dia_festivo.get('vigente', True):
                    continue
                requiere_comp = dia_festivo['turno'] in WORK_CODES or (
                    bool(dia_festivo.get('es_domingo'))
                    and dia_festivo.get('turno') == 'D'
                    and dia_festivo.get('origen') in {'descanso_domingo','descanso_especial'}
                )
                if not requiere_comp:
                    continue
                compensatorios = [
                    d for d in e['dias']
                    if d.get('origen') == 'compensatorio_festivo'
                    and d.get('festivo_origen') == f
                    and d.get('turno') == 'D'
                ]
                if not compensatorios:
                    errores.append(
                        f"{e['nombre']}: trabajó el festivo {f} y no tiene el descanso compensatorio adicional correspondiente."
                    )
    for v in _violaciones_cambio_semanal(horario, turnos_previos):
        e=v['empleado']
        errores.append(
            f"{e['nombre']}: tiene AM y PM dentro de la semana del {v.get('lunes')} sin una excepción de turno autorizada. "
            "El cambio operativo normal debe hacerse al iniciar una semana nueva."
        )
    # Y al final, lo innegociable. El núcleo normativo no se configura desde
    # ninguna pantalla y no admite excepciones: si algo de ahí falla, el mes no
    # se puede publicar por muy bien que cuadre todo lo demás. Va el último a
    # propósito, para que sus mensajes queden a la vista al leer los errores.
    errores.extend(nucleo_normativo.revisar(horario))
    return sorted(set(errores)), sorted(set(avisos))
