# -*- coding: utf-8 -*-
"""2 · Aplicar lo que alguien decidió.

Las solicitudes aprobadas, las asignaciones, los cambios hechos a mano y
los reemplazos. Son las decisiones de personas, y por eso van antes que
cualquier reparto automático: el motor se acomoda a ellas, no al revés.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from gestor.motor.comun import (  # noqa: F401
    _asignar_d,
    _codigo_administrativo_area,
    _conteo_turno,
    _dia,
    _es_descanso_semanal,
    _fila,
    _lunes_iso_de_dia,
    _puede_descansar,
    _semanas,
    cobertura_valida_si_cambia,
)

# Cómo se le cuenta a una persona un aviso de validación vive en su propio
# módulo: son ciento catorce líneas de texto que no dependen del horario.
from gestor.motor.vocabulario import (  # noqa: F401
    ALL_CODES,
    OUT_OF_VIGENCY_CODE,
    WORK_CODES,
)


def _rango_fechas(inicio: str, fin: str):
    a = date.fromisoformat(inicio)
    b = date.fromisoformat(fin)
    while a <= b:
        yield a
        a += timedelta(days=1)

def _fechas_turno_dia(s: dict) -> list[str]:
    """Fechas reales afectadas por una solicitud de cambio de turno."""
    fechas = list(_rango_fechas(s['fecha_inicio'], s['fecha_fin']))
    if s.get('modo_periodo') == 'semanal':
        weekday = s.get('dia_semana_recurrente')
        if weekday is None:
            return []
        fechas = [f for f in fechas if f.weekday() == int(weekday)]
    return [f.isoformat() for f in fechas]

#: Lo que dura una capacitación cuando nadie dijo de cuándo a cuándo. Es una
#: jornada normal: si alguien pasa el día en un curso, ese día no está en su
#: puesto, y para el horario eso es lo que importa.
HORAS_DE_UNA_JORNADA = 7.0


def _horas_cap(s: dict) -> float:
    """Cuántas horas dura la capacitación. Sin horas, una jornada.

    Esto reventaba, y se llevaba el mes entero por delante. `strptime(None)`
    lanza, la excepción subía hasta `generacion.generar`, que la apunta en el
    registro y sigue con la variante siguiente... donde vuelve a pasar lo mismo.
    Las cinco variantes fallaban igual, no quedaba ni una propuesta, y la
    persona leía «puede que se contradigan entre ellas» sobre **una sola**
    solicitud. A partir de ahí octubre no se podía generar hasta cancelarla.

    Y pasaba siempre: la pantalla manda `hora_inicio` y `hora_fin`, pero el
    modelo de la ruta no las declaraba y la tabla no tenía dónde guardarlas, así
    que a este punto no llegaban nunca. Una capacitación pedida desde la
    aplicación no podía tener horas.
    """
    ini, fin = s.get('hora_inicio'), s.get('hora_fin')
    if not ini or not fin:
        return HORAS_DE_UNA_JORNADA
    try:
        desde = datetime.strptime(str(ini), '%H:%M')
        hasta = datetime.strptime(str(fin), '%H:%M')
    except (TypeError, ValueError):
        return HORAS_DE_UNA_JORNADA
    horas = (hasta - desde).total_seconds() / 3600
    return horas if horas > 0 else HORAS_DE_UNA_JORNADA

def reubicar_descanso_retirado_manualmente(
    horario: list[dict],
    ajustes: Optional[list[dict]] = None,
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
) -> tuple[list[str], list[str]]:
    """Reubica dentro de la misma semana un D que el usuario convirtió en trabajo.

    La modificación manual continúa siendo la decisión principal. Si la celda
    editada antes era D y ahora es AM/PM/ADM, se busca otro día AM/PM libre de
    la MISMA semana y dentro del rango editable. Si no existe una alternativa
    compatible, no se inventa una: se devuelve una discrepancia entendible.
    """
    errores: list[str] = []
    avisos: list[str] = []
    for ajuste in ajustes or []:
        if ajuste.get('preservar') or str(ajuste.get('turno_anterior') or '') != 'D' or str(ajuste.get('turno')) == 'D':
            continue
        e = _fila(horario, int(ajuste.get('empleado_id')))
        if not e:
            continue
        fecha = str(ajuste.get('fecha'))
        original = _dia(e, fecha)
        if not original:
            continue
        lunes = str(original.get('lunes_semana') or _lunes_iso_de_dia(original))
        # Si ya existe otro descanso semanal válido, no añadimos un segundo.
        existentes = [d for d in e.get('dias', []) if _lunes_iso_de_dia(d) == lunes and d.get('fecha') != fecha and _es_descanso_semanal(d)]
        if existentes:
            continue
        candidatos = [
            d for d in e.get('dias', [])
            if _lunes_iso_de_dia(d) == lunes
            and d.get('fecha') != fecha
            and d.get('turno') in {'AM','PM'}
            and not d.get('bloqueado')
            and not d.get('es_ultimo_viernes_adm')
            and _puede_descansar(horario, e, d)
        ]
        if not candidatos:
            errores.append(
                f"{e['nombre']}: el descanso del {fecha} fue cambiado manualmente a {ajuste.get('turno')}, "
                f"pero no hay otro día disponible en la semana del {lunes} para reubicar el descanso sin romper cobertura u otra condición."
            )
            continue
        candidatos.sort(key=lambda d:(
            1 if int(d.get('dia_semana_numero',-1)) == 6 else 0,
            -_conteo_turno(horario, e['area'], d['fecha'], d['turno']),
            d['fecha'],
        ))
        nuevo = candidatos[0]
        origen = 'descanso_fijo_reubicado_manual' if e.get('descanso_fijo') is not None else 'descanso_reubicado_manual'
        anterior_turno = nuevo.get('turno')
        _asignar_d(nuevo, origen, f"Descanso reubicado automáticamente porque el {fecha} fue modificado manualmente")
        nuevo['reubicado_desde'] = fecha
        avisos.append(
            f"{e['nombre']}: el descanso se movió automáticamente del {fecha} al {nuevo['fecha']} "
            f"({anterior_turno} → D) para conservar el descanso semanal."
        )
    return errores, avisos

def aplicar_solicitudes_previas(
    horario: list[dict],
    solicitudes: list[dict],
    respetar_bloqueos_existentes: bool = False,
    advertencias: Optional[list[str]] = None,
) -> tuple[list[str], list[dict]]:
    errores=[]
    reemplazos=[]
    aprobadas=[s for s in solicitudes if bool(s['aprobada'])]
    # 1) descanso, ausencias, capacitación y ADM-GS
    for s in aprobadas:
        e=_fila(horario,s['empleado_id'])
        if not e:
            continue
        tipo=s['tipo']
        if tipo in {'cambio_am','cambio_pm','cambio_pareja','cambio_persona','turno_dia','turno_semanas'}:
            continue
        for f in _rango_fechas(s['fecha_inicio'],s['fecha_fin']):
            d=_dia(e,f.isoformat())
            if not d:
                continue
            # Un día heredado ya se decidió y se publicó con el mes anterior:
            # ninguna novedad ni asignación de este periodo lo reescribe.
            #
            # **Pero se dice.** Antes esto era un `continue` a secas y ahí se
            # acababa: la novedad salía aprobada en su tabla, el día salía
            # trabajado en el horario, y no había una sola línea en ninguna
            # parte que explicara por qué. Quien la pidió daba por hecho que
            # estaba puesta. Como los períodos van por semanas completas, la
            # primera semana de un mes es siempre la última del anterior, así
            # que esto le toca a cualquier novedad de los primeros días.
            if d.get('heredado'):
                if advertencias is not None:
                    advertencias.append(
                        f"{e['nombre']}: la solicitud {tipo} del {f.isoformat()} "
                        'no se aplicó aquí. Ese día pertenece a la semana que '
                        'este mes comparte con el anterior, que ya se entregó y '
                        'se copia tal cual. Para cambiarlo hay que rehacer el '
                        'mes anterior desde Modificar horario.')
                continue
            if not d.get('vigente', True) or d.get('turno') == OUT_OF_VIGENCY_CODE:
                # Una novedad histórica posterior al retiro no reactiva a la persona.
                continue
            if respetar_bloqueos_existentes and d.get('bloqueado') and d.get('origen_habitual'):
                # Lo puso una regla habitual, que es lo que se hace mientras
                # nadie diga otra cosa. Una solicitud aprobada para ese día sí
                # lo dice, así que manda ella.
                if advertencias is not None:
                    advertencias.append(
                        f"{e['nombre']}: la solicitud {tipo} del {f.isoformat()} sustituye ese día a su "
                        'regla habitual de turno.')
                d['bloqueado'] = False
                d['origen_habitual'] = False
            if (tipo == 'descanso' and d.get('turno') == 'D'
                    and respetar_bloqueos_existentes and d.get('bloqueado')):
                # Pedía descansar ese día y ese día ya es descanso: la solicitud
                # está cumplida. Antes esto se leía como un choque y bastaba para
                # dejar el mes sin poder programarse.
                if advertencias is not None:
                    advertencias.append(
                        f"{e['nombre']}: el descanso pedido para el {f.isoformat()} ya lo tenía "
                        'por otro motivo, así que no cambia nada.')
                continue
            if respetar_bloqueos_existentes and d.get('bloqueado'):
                errores.append(
                    f"{e['nombre']}: la solicitud {tipo} del {f.isoformat()} entra en conflicto con una instrucción de mayor prioridad ({d.get('turno')})."
                )
                continue
            if tipo=='descanso':
                if e['tipo_turno']=='administrativo' or e.get('descanso_fijo') is not None:
                    errores.append(f"{e['nombre']}: no se puede mover su descanso el {f.isoformat()}.")
                    continue
                d.update(turno='D',origen='descanso_solicitado',bloqueado=True,solicitud_id=s['id'],observacion=s.get('observacion') or 'Descanso semanal movido por solicitud')
            elif tipo=='descanso_extra':
                if e['tipo_turno']=='administrativo':
                    errores.append(f"{e['nombre']}: el descanso extra no aplica al turno administrativo el {f.isoformat()}.")
                    continue
                if d['turno'] not in {'AM','PM'} or d['bloqueado']:
                    errores.append(f"{e['nombre']}: no se puede agregar descanso extra el {f.isoformat()} porque ya existe una novedad o descanso bloqueado.")
                    continue
                if not _puede_descansar(horario,e,d):
                    errores.append(f"{e['nombre']}: el descanso extra del {f.isoformat()} dejaría un turno obligatorio sin cobertura.")
                    continue
                d.update(turno='D',origen='descanso_extra_solicitado',bloqueado=True,solicitud_id=s['id'],observacion=s.get('observacion') or 'Descanso extra aprobado')
            elif tipo in {'vacaciones','incapacidad','permiso'}:
                codigo={'vacaciones':'VAC','incapacidad':'INC','permiso':'PER'}[tipo]
                turno_cubrir=d['turno']
                d.update(turno=codigo,origen=f'solicitud:{tipo}',bloqueado=True,solicitud_id=s['id'],observacion=s.get('observacion') or tipo.title())
                if s.get('modo_cobertura')=='reemplazar' and s.get('reemplazo_empleado_id'):
                    reemplazos.append({'solicitud':s,'fecha':f.isoformat(),'turno':turno_cubrir,'ausente':e})
            elif tipo=='capacitacion':
                turno_cubrir=d['turno']
                d.update(turno='CAP',origen='solicitud:capacitacion',bloqueado=True,solicitud_id=s['id'],observacion=s.get('observacion') or 'Capacitación',capacitacion_horas=_horas_cap(s))
                if s.get('modo_cobertura')=='reemplazar' and s.get('reemplazo_empleado_id'):
                    reemplazos.append({'solicitud':s,'fecha':f.isoformat(),'turno':turno_cubrir,'ausente':e})
            elif tipo=='asignacion_adm_gs':
                if e['area']!='gestion_social':
                    errores.append(f"{e['nombre']}: ADM-GS solo aplica a Gestión Social.")
                    continue
                if d.get('bloqueado') or d.get('turno') not in {'AM', 'PM'}:
                    errores.append(
                        f"{e['nombre']}: no puede asignarse ADM-GS el {f.isoformat()} porque ese día ya tiene una novedad o descanso obligatorio."
                    )
                    continue

                turno_origen = d['turno']
                solicita_reemplazo = (
                    s.get('modo_cobertura') == 'reemplazar'
                    and bool(s.get('reemplazo_empleado_id'))
                )
                # ADM-GS conserva el turno que la persona tenía ese día: si
                # iba a estar en AM cubre AM, y si iba a estar en PM cubre PM.
                # Solo se libera cuando se pide expresamente un reemplazo desde
                # «Asignaciones y ajustes»; entonces la otra persona garantiza
                # PM y la jornada administrativa pasa a contar como AM.
                cobertura_operativa = turno_origen if turno_origen in {'AM', 'PM'} else 'AM'

                if turno_origen == 'PM' and solicita_reemplazo:
                    cobertura_operativa = 'AM'
                    reemplazos.append({
                        'solicitud': s,
                        'fecha': f.isoformat(),
                        'turno': 'PM',
                        'ausente': e,
                    })

                d.update(
                    turno='ADM-GS',
                    origen='solicitud:adm_gs',
                    bloqueado=True,
                    solicitud_id=s['id'],
                    turno_operativo_origen=turno_origen,
                    cobertura_operativa=cobertura_operativa,
                    observacion=(
                        s.get('observacion')
                        or f'Asignación administrativa GS; cobertura operativa {cobertura_operativa}'
                    ),
                )
    # 2) Cambio de turno AM/PM sin intercambio. Puede ser un rango de 1-3 días
    #    o un día semanal recurrente dentro del mes seleccionado.
    for s in aprobadas:
        if s['tipo'] not in {'turno_dia','turno_semanas'}:
            continue
        e = _fila(horario, s['empleado_id'])
        if not e:
            continue

        fechas_objetivo = _fechas_turno_dia(s) if s['tipo']=='turno_dia' else [f.isoformat() for f in _rango_fechas(s['fecha_inicio'], s['fecha_fin'])]
        if not fechas_objetivo:
            errores.append(f"{e['nombre']}: la solicitud de cambio de turno no afecta ninguna fecha del periodo.")
            continue

        for fecha in fechas_objetivo:
            d = _dia(e, fecha)
            # Si la recurrencia abarca parte de otro mes, sencillamente esa fecha
            # no pertenece al horario que estamos generando.
            if not d:
                continue
            # Un día heredado ya se decidió y se publicó con el mes anterior:
            # ninguna novedad ni asignación de este periodo lo reescribe.
            if d.get('heredado'):
                continue
            if not d.get('vigente', True) or d.get('turno') == OUT_OF_VIGENCY_CODE:
                continue
            if e['tipo_turno'] == 'administrativo':
                errores.append(f"{e['nombre']}: el horario administrativo no puede cambiarse a AM/PM el {fecha}.")
                continue
            if d.get('bloqueado') and d.get('origen_habitual') and d.get('turno') in {'AM', 'PM'}:
                # Ese día lo puso una regla habitual, que es lo que se hace
                # mientras nadie diga otra cosa. Un cambio de turno aprobado sí
                # lo dice, así que manda él.
                if advertencias is not None:
                    advertencias.append(
                        f"{e['nombre']}: el cambio de turno aprobado del {fecha} sustituye ese día a su "
                        'regla habitual.')
                d['bloqueado'] = False
                d['origen_habitual'] = False
            if d['bloqueado'] or d['turno'] not in {'AM','PM'}:
                errores.append(
                    f"{e['nombre']}: no puede cambiar su turno el {fecha} porque ese día ya tiene una novedad, descanso o asignación bloqueada."
                )
                continue
            objetivo = s.get('turno_solicitado')
            if objetivo not in {'AM','PM'}:
                errores.append(f"{e['nombre']}: la solicitud del {fecha} no indica un turno AM/PM válido.")
                continue

            actual = d['turno']
            if actual != objetivo and not cobertura_valida_si_cambia(horario, e, d, objetivo, respetar_maximo=False):
                errores.append(
                    f"{e['nombre']}: cambiar de {actual} a {objetivo} el {fecha} dejaría descubierto un turno obligatorio de su área."
                )
                continue

            # La pareja de PC comparte equipo: no pueden estar los dos en el
            # mismo turno, y ninguna solicitud aprobada se salta eso. Se
            # devuelve el conflicto para que se corrija la solicitud.
            pareja = _fila(horario, e.get('pareja_id')) if e.get('pareja_id') else None
            if pareja:
                dp = _dia(pareja, fecha)
                if dp and dp['turno'] == objetivo:
                    errores.append(
                        f"{e['nombre']}: no puede quedar {objetivo} el {fecha} porque coincidiría "
                        f"con su pareja de PC {pareja['nombre']}."
                    )
                    continue

            modo = ('semanas completas' if s['tipo']=='turno_semanas' else ('recurrente semanal' if s.get('modo_periodo') == 'semanal' else 'rango aprobado'))
            d.update(
                turno=objetivo,
                origen=('solicitud:turno_semanas' if s['tipo']=='turno_semanas' else 'solicitud:turno_dia'),
                bloqueado=True,
                # Un cambio de turno dice en qué turno trabaja esa persona ese
                # día, no que tenga que trabajar los siete días de la semana.
                # Si la solicitud cubre una semana entera, el descanso semanal
                # —que es obligatorio— puede colocarse dentro de ella; se elige
                # en último lugar, así que solo ocurre si no queda otro día.
                descanso_permitido=True,
                solicitud_id=s['id'],
                observacion=s.get('observacion') or f'Cambio de turno {modo}: {actual} → {objetivo}',
            )

    # 3) intercambios de turno aprobados
    #    a) con la pareja de PC (cambio_am / cambio_pm)
    #    b) con cualquier persona compatible de la misma área (cambio_persona)
    procesados=set()
    for s in aprobadas:
        if s['tipo'] not in {'cambio_am','cambio_pm','cambio_pareja','cambio_persona'}:
            continue

        e=_fila(horario,s['empleado_id'])
        fecha=s['fecha_inicio']
        if not e or (e['empleado_id'],fecha) in procesados:
            continue

        if s['tipo']=='cambio_persona':
            otra_id=s.get('intercambio_empleado_id')
            p=_fila(horario,otra_id) if otra_id else None
            if not p:
                errores.append(f"{e['nombre']}: no se encontró la persona seleccionada para el intercambio del {fecha}.")
                continue
            if p['area']!=e['area']:
                errores.append(f"{e['nombre']} y {p['nombre']}: el intercambio del {fecha} no es válido porque pertenecen a áreas diferentes.")
                continue
        else:
            p=_fila(horario,e.get('pareja_id')) if e.get('pareja_id') else None
            if not p:
                errores.append(f"{e['nombre']}: no tiene pareja disponible para el cambio del {fecha}.")
                continue

        de=_dia(e,fecha)
        dp=_dia(p,fecha)
        if not de or not dp:
            errores.append(f"No se encontró el día {fecha} para completar el intercambio entre {e['nombre']} y {p['nombre']}.")
            continue
        if (
            not de.get('vigente', True) or not dp.get('vigente', True)
            or de.get('turno') == OUT_OF_VIGENCY_CODE or dp.get('turno') == OUT_OF_VIGENCY_CODE
        ):
            # Un intercambio posterior al retiro/antes del ingreso queda fuera
            # de la programación y no debe reactivar a ninguna persona.
            continue

        if de['turno'] not in {'AM','PM'} or dp['turno'] not in {'AM','PM'}:
            errores.append(f"{e['nombre']} y {p['nombre']}: no pueden intercambiar el {fecha} porque alguno no tiene turno AM/PM disponible.")
            continue

        if de['bloqueado'] or dp['bloqueado']:
            errores.append(f"{e['nombre']} y {p['nombre']}: el intercambio del {fecha} coincide con otra novedad o asignación bloqueada.")
            continue

        if de['turno']==dp['turno']:
            errores.append(f"{e['nombre']} y {p['nombre']}: ambos ya tienen {de['turno']} el {fecha}; no hay turnos diferentes para intercambiar.")
            continue

        if s['tipo'] in {'cambio_am','cambio_pm'}:
            # Compatibilidad con solicitudes antiguas. Las nuevas usan cambio_pareja
            # y simplemente intercambian AM ↔ PM según el turno real de ese día.
            objetivo='AM' if s['tipo']=='cambio_am' else 'PM'
            if dp['turno']!=objetivo:
                errores.append(f"{e['nombre']}: su pareja {p['nombre']} no tiene {objetivo} el {fecha}.")
                continue

        turno_e=de['turno']
        turno_p=dp['turno']

        # Como intercambian AM por PM, el número de personas por turno dentro del área no cambia.
        # Solo se revisa conflicto de PC posterior para cada persona.
        de['turno'],dp['turno']=turno_p,turno_e

        conflicto=False
        for persona,dia_persona in ((e,de),(p,dp)):
            pareja_id=persona.get('pareja_id')
            pareja_pc=_fila(horario,pareja_id) if pareja_id else None
            if pareja_pc and pareja_pc['empleado_id'] not in {e['empleado_id'],p['empleado_id']}:
                dia_pareja=_dia(pareja_pc,fecha)
                if dia_pareja and dia_pareja['turno']==dia_persona['turno'] and dia_persona['turno'] in {'AM','PM'}:
                    errores.append(
                        f"{persona['nombre']}: el intercambio del {fecha} lo dejaría en {dia_persona['turno']} al mismo tiempo que su pareja de PC {pareja_pc['nombre']}."
                    )
                    conflicto=True
                    break

        if conflicto:
            de['turno'],dp['turno']=turno_e,turno_p
            continue

        origen='intercambio_persona' if s['tipo']=='cambio_persona' else 'intercambio_pareja'
        for x,otro in ((de,p['nombre']),(dp,e['nombre'])):
            x.update(
                origen=origen,
                bloqueado=True,
                solicitud_id=s['id'],
                observacion=f'Intercambio aprobado con {otro}',
            )

        procesados.add((e['empleado_id'],fecha))
        procesados.add((p['empleado_id'],fecha))
    return errores,reemplazos

def aplicar_requerimientos_directos(
    horario: list[dict],
    requerimientos: Optional[list[dict]] = None,
    advertencias: Optional[list[str]] = None,
) -> tuple[list[str], list[dict]]:
    """Aplica instrucciones directas del jefe, sin flujo de aprobación.

    Se mantienen separadas de Solicitudes porque son decisiones operativas ya
    autorizadas: descanso extra, asignación administrativa, actividad asignada y
    excepción de turno. Una asignación directa es una decisión explícita que
    puede superar la regla de pareja y la consistencia semanal AM/PM, pero no la
    cobertura, las ausencias, el máximo de seis días ni otras reglas operativas.
    """
    errores: list[str] = []
    reemplazos: list[dict] = []
    en_curso: dict = {'habitual': False}

    def _problema(texto: str) -> None:
        """Qué hacer cuando una asignación no se puede aplicar.

        Una asignación con fecha es una instrucción para ese día: si choca con
        otra cosa, el usuario tiene que resolverlo y por eso es un error. Una
        regla habitual —«todos los lunes en PM»— es solo lo que se hace
        mientras nadie diga otra cosa: cuando ese día ya está decidido por unas
        vacaciones, una asignación con fecha o un ajuste manual, la regla
        sencillamente no se aplica ese día y se avisa. Antes esto era un error
        y bastaba una habitualidad para dejar el mes entero sin poder
        generarse.
        """
        if en_curso['habitual']:
            if advertencias is not None:
                advertencias.append(texto + ' Como es una regla habitual, ese día se deja como estaba.')
        else:
            errores.append(texto)

    def _es_habitual(x: dict) -> bool:
        """Regla que se repite sola, sin una fecha concreta detrás."""
        return bool(x.get('recurrente_indefinido') or x.get('dias_semana'))

    # Las reglas habituales se aplican primero y las asignaciones con fecha
    # después. Una fecha concreta es una instrucción para ese día; la
    # habitualidad es lo que se hace mientras nadie diga otra cosa. Antes el
    # orden dependía de cuál se hubiera creado primero, y una jornada
    # administrativa del área chocaba contra un «todos los lunes en PM» y
    # dejaba el mes entero sin poder generarse.
    ordenados = sorted(requerimientos or [], key=lambda x: (not _es_habitual(x), int(x.get('id') or 0)))
    por_id = {int(x.get('id') or 0): x for x in ordenados if x.get('id') is not None}

    for r in ordenados:
        habitual = _es_habitual(r)
        en_curso['habitual'] = habitual
        e = _fila(horario, int(r['empleado_id']))
        if not e:
            continue
        fechas = [str(x) for x in (r.get('fechas') or [])]
        for fecha in fechas:
            d = _dia(e, fecha)
            if not d:
                continue
            # Un día heredado ya se decidió y se publicó con el mes anterior:
            # ninguna novedad ni asignación de este periodo lo reescribe.
            if d.get('heredado'):
                continue
            if not d.get('vigente', True) or d.get('turno') == OUT_OF_VIGENCY_CODE:
                continue
            tipo = r.get('tipo')
            # Una asignación con fecha manda sobre lo que dejó puesto una regla
            # habitual: se sustituye y se explica en el comentario del día.
            escrito_por = por_id.get(int(d.get('requerimiento_id') or 0))
            cede_habitual = (
                not habitual
                and d.get('bloqueado')
                and escrito_por is not None
                and _es_habitual(escrito_por)
                and str(d.get('origen') or '').startswith('requerimiento:')
            )
            if cede_habitual:
                d['bloqueado'] = False
                d['sustituye_habitual'] = True
            if tipo == 'descanso_extra':
                if e['tipo_turno'] == 'administrativo':
                    _problema(f"{e['nombre']}: el día de descanso asignado no aplica al horario administrativo el {fecha}.")
                    continue
                if d.get('turno') == 'D':
                    # Ya descansa ese día —por su descanso fijo o porque otra
                    # novedad lo dejó libre—, así que la asignación no tiene
                    # nada que hacer. Antes esto era un error y bastaba para
                    # dejar el mes sin poder generarse.
                    if advertencias is not None:
                        advertencias.append(
                            f"{e['nombre']}: el descanso asignado del {fecha} ya lo tenía por otro motivo, "
                            'así que no cambia nada.')
                    continue
                if d.get('bloqueado') or d.get('turno') not in {'AM','PM'}:
                    _problema(f"{e['nombre']}: no puede fijarse el descanso del {fecha} porque ya existe una novedad o descanso obligatorio.")
                    continue
                if not _puede_descansar(horario, e, d):
                    _problema(f"{e['nombre']}: el descanso asignado del {fecha} dejaría un turno obligatorio sin cobertura.")
                    continue
                d.update(
                    turno='D', origen='descanso_asignado_directo', bloqueado=True,
                    requerimiento_id=r.get('id'),
                    observacion=r.get('descripcion') or 'Día de descanso semanal fijado por asignación',
                )
                continue

            if tipo == 'excepcion_turno':
                if e.get('tipo_turno') == 'administrativo':
                    _problema(f"{e['nombre']}: la excepción AM/PM no aplica a personal administrativo el {fecha}.")
                    continue
                turno = r.get('turno_excepcion')
                if turno not in {'AM','PM'}:
                    _problema(f"{e['nombre']}: la excepción del {fecha} no indica AM o PM.")
                    continue
                # No se permite convertir silenciosamente un descanso fijo en
                # turno. Se comprueba antes que el bloqueo genérico para que el
                # mensaje diga exactamente qué ocurre y cómo resolverlo.
                if d.get('origen') == 'descanso_fijo':
                    _problema(
                        f"{e['nombre']}: el {fecha} es su descanso fijo semanal. "
                        "Quita esa fecha de la asignación, o cambia primero su descanso fijo desde Personal, "
                        "o realiza el cambio desde Modificar horario con una justificación."
                    )
                    continue
                if d.get('bloqueado'):
                    _problema(
                        f"{e['nombre']}: la excepción de turno del {fecha} coincide con otra novedad o asignación bloqueada ({d.get('turno')})."
                    )
                    continue
                if d.get('turno') not in {'AM','PM'}:
                    _problema(
                        f"{e['nombre']}: la excepción de turno del {fecha} requiere una jornada operativa AM/PM disponible."
                    )
                    continue
                # Una asignación directa del administrador tiene prioridad sobre
                # la regla de pareja. La coincidencia queda identificada por el
                # origen requerimiento:* y la validación final la muestra como
                # decisión permitida, no como conflicto.
                if not cobertura_valida_si_cambia(horario, e, d, turno, respetar_maximo=False):
                    _problema(
                        f"{e['nombre']}: la excepción a {turno} del {fecha} dejaría descubierto el turno que tenía asignado."
                    )
                    continue
                anterior = d.get('turno')
                d.update(
                    turno=turno,
                    origen='requerimiento:excepcion_turno',
                    bloqueado=True,
                    # Una excepción dice en qué turno trabaja esa persona ese
                    # día, no que tenga que trabajar los siete días de la
                    # semana. Si la asignación cubre una semana entera, el
                    # descanso semanal —que es obligatorio— puede colocarse
                    # dentro de ella; se elige siempre en último lugar, así que
                    # solo ocurre cuando no queda ningún otro día libre.
                    descanso_permitido=True,
                    requerimiento_id=r.get('id'),
                    solicitud_id=None,
                    turno_operativo_origen=anterior,
                    observacion=r.get('descripcion') or f'Excepción operativa directa · {turno}',
                )
                continue

            if tipo not in {'asignacion_administrativa','actividad'}:
                continue
            codigo = r.get('horario_administrativo')
            if tipo == 'actividad' and codigo in {'OPERATIVO','AM','PM'}:
                if e.get('tipo_turno') == 'administrativo':
                    _problema(f"{e['nombre']}: una actividad operativa AM/PM no aplica a su horario administrativo el {fecha}.")
                    continue
                if d.get('bloqueado') and d.get('origen') not in {'descanso_fijo','descanso_administrativo'}:
                    _problema(f"{e['nombre']}: la actividad del {fecha} coincide con otra novedad o asignación bloqueada ({d.get('turno')}).")
                    continue
                actual = d.get('turno')
                if actual not in {'AM','PM'}:
                    original = d.get('turno_original')
                    actual = original if original in {'AM','PM'} else None
                objetivo = actual if codigo == 'OPERATIVO' else codigo
                if objetivo not in {'AM','PM'}:
                    _problema(f"{e['nombre']}: no fue posible determinar el turno operativo para la actividad del {fecha}.")
                    continue
                if actual in {'AM','PM'} and actual != objetivo:
                    # Igual que cualquier asignación directa, una actividad
                    # explícita puede hacer coincidir temporalmente a la pareja.
                    if not cobertura_valida_si_cambia(horario, e, d, objetivo, respetar_maximo=False):
                        _problema(f"{e['nombre']}: mover la actividad a {objetivo} el {fecha} dejaría descubierto su turno de origen.")
                        continue
                d.update(
                    turno=objetivo,
                    origen='requerimiento:actividad',
                    bloqueado=True,
                    requerimiento_id=r.get('id'),
                    solicitud_id=None,
                    turno_operativo_origen=actual,
                    cobertura_operativa=objetivo,
                    observacion=r.get('descripcion') or f'Actividad asignada · {objetivo}',
                )
                continue

            if codigo not in {'ADM-GS','ADM-AC'}:
                _problema(f"{e['nombre']}: el requerimiento del {fecha} no indica un horario compatible.")
                continue
            if codigo == 'ADM-AC' and e.get('area') != 'atencion_ciudadano':
                _problema(f"{e['nombre']}: ADM-AC solo puede asignarse a Atención al Ciudadano el {fecha}.")
                continue

            # Una actividad asignada sí puede desplazar el descanso fijo/administrativo
            # automático, porque el jefe ya indicó que la persona debe trabajar ese día.
            # La compensación del descanso fijo se reubica más adelante dentro de la semana.
            permitido_sobre_descanso = tipo in {'actividad','asignacion_administrativa'} and d.get('origen') in {'descanso_fijo','descanso_administrativo'}
            if d.get('bloqueado') and not permitido_sobre_descanso:
                _problema(f"{e['nombre']}: el requerimiento directo del {fecha} coincide con otra novedad o asignación bloqueada ({d.get('turno')}).")
                continue

            # Un administrativo permanente conserva el código propio de su área.
            # Esto también permite asignarle una actividad en domingo/festivo;
            # el descanso obligatorio desplazado se reubica más adelante.
            if e.get('tipo_turno') == 'administrativo':
                codigo_esperado = _codigo_administrativo_area(e.get('area'))
                if codigo not in {codigo_esperado, 'ADM-GS'}:
                    _problema(
                        f"{e['nombre']}: el horario administrativo compatible con su área es {codigo_esperado} el {fecha}."
                    )
                    continue
                d.update(
                    turno=codigo,
                    origen=f"requerimiento:{tipo}",
                    bloqueado=True,
                    requerimiento_id=r.get('id'),
                    solicitud_id=None,
                    turno_operativo_origen=None,
                    # Un administrativo permanente no tenía turno operativo ese
                    # día, así que su jornada administrativa no cubre ninguno.
                    cobertura_operativa=None,
                    observacion=r.get('descripcion') or (
                        f'Actividad asignada · {codigo}' if tipo == 'actividad'
                        else f'Asignación administrativa directa · {codigo}'
                    ),
                )
                continue

            turno_origen = d.get('turno')
            if turno_origen not in {'AM','PM'}:
                original = d.get('turno_original')
                turno_origen = original if original in {'AM','PM'} else None

            if codigo == 'ADM-GS':
                if turno_origen not in {'AM','PM'}:
                    _problema(f"{e['nombre']}: no fue posible determinar el turno operativo de origen para ADM-GS el {fecha}.")
                    continue
                # El turno propio de la persona es el que ADM-GS conserva.
                cobertura_operativa = turno_origen
                if turno_origen == 'PM' and bool(r.get('cubrir_pm')) and r.get('reemplazo_empleado_id'):
                    # Se pidió expresamente que otra persona garantice PM.
                    cobertura_operativa = 'AM'
                    reemplazos.append({
                        'solicitud': {
                            'id': None,
                            'reemplazo_empleado_id': r.get('reemplazo_empleado_id'),
                            'observacion': r.get('descripcion') or 'Cobertura PM por requerimiento directo',
                        },
                        'fecha': fecha, 'turno': 'PM', 'ausente': e,
                    })
                d.update(
                    turno='ADM-GS', origen=f"requerimiento:{tipo}", bloqueado=True,
                    requerimiento_id=r.get('id'), solicitud_id=None,
                    turno_operativo_origen=turno_origen,
                    cobertura_operativa=cobertura_operativa,
                    observacion=r.get('descripcion') or (
                        'Actividad asignada · ADM-GS' if tipo == 'actividad' else 'Asignación administrativa directa · ADM-GS'
                    ),
                )
            else:
                # ADM-AC puede corresponder a una actividad del personal de Atención,
                # incluido el administrativo permanente en un domingo/festivo.
                d.update(
                    turno='ADM-AC', origen=f"requerimiento:{tipo}", bloqueado=True,
                    requerimiento_id=r.get('id'), solicitud_id=None,
                    turno_operativo_origen=turno_origen,
                    cobertura_operativa=None,
                    observacion=r.get('descripcion') or (
                        'Actividad asignada · ADM-AC' if tipo == 'actividad' else 'Asignación administrativa directa · ADM-AC'
                    ),
                )
    return errores, reemplazos

def reubicar_descanso_fijo_por_actividad(horario: list[dict]) -> list[str]:
    """Reubica descansos que una actividad obligatoria desplaza.

    Aplica tanto al descanso fijo de personal operativo como al descanso
    administrativo automático de domingo/festivo. La actividad siempre se
    respeta y el descanso se busca en otro día de la misma semana.
    """
    errores: list[str] = []
    for e in horario:
        fijo = e.get('descanso_fijo')
        semanas = _semanas(e)
        for lunes, dias in semanas.items():
            if e.get('tipo_turno') == 'administrativo':
                codigo_administrativo = _codigo_administrativo_area(e.get('area'))
                afectados = [
                    d for d in dias
                    if d.get('turno') in WORK_CODES
                    and d.get('origen') in {'requerimiento:actividad','requerimiento:asignacion_administrativa'}
                    and (d.get('turno_original') == 'D' or d.get('es_domingo') or d.get('es_festivo'))
                ]
                origen_comp = 'descanso_administrativo_reubicado_actividad'
                candidatos = [
                    d for d in dias
                    if not d.get('bloqueado') and d.get('turno') == codigo_administrativo
                ]
            else:
                if fijo is None:
                    continue
                afectados = [
                    d for d in dias
                    if int(d.get('dia_semana_numero')) == int(fijo)
                    and d.get('turno') in WORK_CODES
                    # Una capacitación aprobada es una jornada obligatoria como
                    # cualquier otra: si cae en el día de descanso fijo, la
                    # persona asiste y su descanso se busca en otro día de esa
                    # misma semana. Antes esto dejaba el mes sin poder generarse.
                    and d.get('origen') in {'requerimiento:actividad','requerimiento:asignacion_administrativa','ultimo_viernes_administrativo','solicitud:capacitacion'}
                ]
                origen_comp = 'descanso_fijo_reubicado_actividad'
                candidatos = [d for d in dias if _puede_descansar(horario, e, d)]
            if not afectados:
                continue
            if any(d.get('turno') == 'D' and d.get('origen') == origen_comp for d in dias):
                continue
            if not candidatos:
                errores.append(
                    f"{e['nombre']}: la actividad del {afectados[0]['fecha']} coincide con un día de descanso y no fue posible reubicar ese descanso dentro de la semana del {lunes} sin romper las reglas del horario."
                )
                continue
            # El descanso desplazado se busca lo más cerca posible del día que
            # esa persona tenía reservado y, a igual distancia, en el día más
            # tarde. Colocarlo al principio de la semana alargaba la racha que
            # viene después y obligaba a meter un segundo descanso: la persona
            # acababa con dos días libres esa semana sin que nadie lo pidiera.
            dia_original = int(afectados[0].get('dia_semana_numero') or 0)
            candidatos.sort(key=lambda d: (
                int(d.get('es_domingo') or d.get('es_festivo')),
                abs(int(d.get('dia_semana_numero') or 0) - dia_original),
                -int(d.get('dia_semana_numero') or 0),
                -_conteo_turno(horario, e['area'], d['fecha'], d['turno']),
                d['fecha'],
            ))
            candidatos[0].update(
                turno='D', origen=origen_comp, bloqueado=True,
                observacion=(f"Descanso reubicado por el último viernes administrativo del {afectados[0]['fecha']}" if afectados[0].get('origen')=='ultimo_viernes_administrativo' else f"Descanso reubicado porque había actividad asignada el {afectados[0]['fecha']}"),
            )
    return errores

#: Lo que un cambio a mano no puede tocar, ni siquiera con la casilla de forzar
#: marcada. No son turnos: son decisiones aprobadas en otra pantalla, y el
#: horario las refleja, no las decide. `NV` no está porque no es una ausencia
#: —es que esa persona ese día no estaba en la plantilla— y se descarta antes.
NO_SE_PISAN_NI_FORZANDO = frozenset({'VAC', 'INC', 'PER', 'CAP'})


def aplicar_ajustes_manuales(
    horario: list[dict],
    ajustes: Optional[list[dict]] = None,
) -> list[str]:
    """Aplica bloqueos/ediciones manuales antes de los descansos automáticos.

    Los elementos internos con ``preservar=True`` pueden contener cualquier código
    ya existente y se usan para congelar semanas no seleccionadas durante una
    reprogramación parcial. Los ajustes creados por el usuario solo admiten
    AM/PM/D/ADM-GS y se validan después junto con el resto del horario.
    """
    errores: list[str] = []
    for ajuste in ajustes or []:
        e = _fila(horario, int(ajuste.get('empleado_id')))
        if not e:
            errores.append(f"Ajuste manual: no existe el empleado {ajuste.get('empleado_id')}.")
            continue
        fecha = str(ajuste.get('fecha'))
        d = _dia(e, fecha)
        if not d:
            continue
        if not d.get('vigente', True) or d.get('turno') == OUT_OF_VIGENCY_CODE:
            continue
        # Los días heredados pertenecen al mes ya publicado. Si hace falta
        # cambiarlos, se cambian allí y este periodo vuelve a leerlos.
        if d.get('heredado'):
            continue
        turno = str(ajuste.get('turno') or '')
        preservar = bool(ajuste.get('preservar'))
        forzar_total = bool(ajuste.get('forzar_total'))
        if preservar:
            if turno not in ALL_CODES:
                errores.append(f"{e['nombre']}: no se puede preservar el código {turno} del {fecha}.")
                continue
            d.update(
                turno=turno,
                origen=(ajuste.get('origen') if 'origen' in ajuste else (d.get('origen') or 'preservado_parcial')),
                bloqueado=True,
                # Conservar incluso una observación vacía: una semana cerrada debe
                # quedar visualmente idéntica, no recibir textos técnicos nuevos.
                observacion=(ajuste.get('observacion') if 'observacion' in ajuste else d.get('observacion', '')),
                solicitud_id=ajuste.get('solicitud_id', d.get('solicitud_id')),
                requerimiento_id=ajuste.get('requerimiento_id', d.get('requerimiento_id')),
                festivo_origen=ajuste.get('festivo_origen', d.get('festivo_origen')),
                capacitacion_horas=float(ajuste.get('capacitacion_horas', d.get('capacitacion_horas') or 0.0)),
                cobertura_operativa=ajuste.get('cobertura_operativa', d.get('cobertura_operativa')),
                turno_operativo_origen=ajuste.get('turno_operativo_origen', d.get('turno_operativo_origen')),
                preservado_parcial=True,
            )
            continue

        if turno not in {'AM', 'PM', 'D', 'ADM-GS', 'ADM-AC'}:
            errores.append(f"{e['nombre']}: el ajuste manual del {fecha} debe ser AM, PM, D, ADM-GS o ADM-AC.")
            continue
        # Una ausencia aprobada no se quita poniendo otra cosa encima.
        #
        # Estos cuatro códigos no los pone el reparto: los pone una novedad que
        # alguien aprobó, con su fecha y su motivo. Forzar por encima dejaba a
        # la persona trabajando un día en el que seguía teniendo la incapacidad
        # aprobada —el horario decía AM y la novedad decía INC— y además borraba
        # el `solicitud_id`, que era lo único que ataba la casilla a la decisión.
        #
        # Forzar sirve para saltarse una **regla del reparto**: la cobertura, el
        # descanso, la pareja. No para deshacer una decisión que se tomó en otra
        # pantalla. Si la incapacidad ya no vale, se rectifica la novedad, que es
        # donde queda constancia de quién lo autorizó.
        if d.get('turno') in NO_SE_PISAN_NI_FORZANDO:
            errores.append(
                f"{e['nombre']}: el {fecha} tiene {d.get('turno')} por una novedad "
                f"aprobada y no se puede cambiar a {turno} desde el horario, ni "
                "forzando. Rectifica la novedad en Solicitudes y el horario la "
                "seguirá.")
            continue
        if not forzar_total:
            if turno == 'ADM-AC':
                if e.get('area') != 'atencion_ciudadano':
                    errores.append(f"{e['nombre']}: ADM-AC manual solo puede asignarse a personal de Atención al Ciudadano el {fecha}.")
                    continue
            elif e.get('tipo_turno') == 'administrativo' and turno in {'AM', 'PM'}:
                errores.append(f"{e['nombre']}: el horario administrativo no puede convertirse manualmente a {turno} el {fecha}.")
                continue
            permitir_admin_sobre_descanso = (
                e.get('tipo_turno') == 'administrativo'
                and turno == _codigo_administrativo_area(e.get('area'))
                and d.get('origen') == 'descanso_administrativo'
            )
            permitir_reubicar_descanso = str(ajuste.get('turno_anterior') or '') == 'D' and turno != 'D'
            if d.get('bloqueado') and d.get('turno') != turno and not permitir_admin_sobre_descanso and not permitir_reubicar_descanso:
                errores.append(
                    f"{e['nombre']}: el {fecha} ya tiene una novedad o descanso obligatorio ({d.get('turno')}) y no puede cambiarse manualmente a {turno}."
                )
                continue
        anterior = d.get('turno')
        payload = {
            'turno': turno,
            'origen': 'ajuste_manual',
            'bloqueado': True,
            'observacion': ajuste.get('observacion') or ((f"Cambio manual forzado: {anterior} → {turno}. Motivo: {ajuste.get('justificacion') or 'justificación registrada'}") if forzar_total else f'Ajuste manual: {anterior} → {turno}'),
            'solicitud_id': None,
            'cobertura_operativa': None,
            'turno_operativo_origen': anterior,
            'excepcion_forzada': forzar_total,
            'justificacion_forzada': ajuste.get('justificacion') if forzar_total else None,
        }
        if turno == 'ADM-GS':
            payload['cobertura_operativa'] = 'AM' if e.get('area') == 'gestion_social' else (anterior if anterior in {'AM','PM'} else None)
        d.update(**payload)
    return errores

def aplicar_reemplazos(horario:list[dict], pendientes:list[dict]) -> list[str]:
    errores=[]
    for item in pendientes:
        s=item['solicitud']
        ausente=item['ausente']
        fecha=item['fecha']
        turno=item['turno']
        if turno not in {'AM','PM'}:
            errores.append(f"{ausente['nombre']}: el turno {turno} del {fecha} no puede cubrirse con reemplazo operativo.")
            continue
        r=_fila(horario,s.get('reemplazo_empleado_id'))
        if not r or r['area']!=ausente['area'] or r['tipo_turno']=='administrativo':
            errores.append(f"{ausente['nombre']}: reemplazo inválido el {fecha}.")
            continue
        dr=_dia(r,fecha)
        if not dr or dr['turno'] not in {'AM','PM'} or dr['bloqueado']:
            errores.append(f"{r['nombre']}: no está disponible para cubrir el {fecha}.")
            continue
        if not cobertura_valida_si_cambia(horario,r,dr,turno, respetar_maximo=False):
            errores.append(f"{r['nombre']}: moverlo a {turno} el {fecha} dejaría descubierto su turno original.")
            continue
        # conflicto de PC del reemplazo
        p=_fila(horario,r.get('pareja_id')) if r.get('pareja_id') else None
        if p:
            dp=_dia(p,fecha)
            if dp and dp['turno']==turno:
                errores.append(f"{r['nombre']}: no puede cubrir {turno} el {fecha} porque coincide con su pareja {p['nombre']}.")
                continue
        original=dr['turno']
        dr.update(turno=turno,origen='reemplazo_aprobado',bloqueado=True,solicitud_id=s['id'],observacion=f"Reemplaza a {ausente['nombre']} (antes {original})",reemplaza_a=ausente['empleado_id'])
        da=_dia(ausente,fecha)
        if da:
            da['reemplazado_por']=r['empleado_id']
    return errores
