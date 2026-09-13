# -*- coding: utf-8 -*-
"""1 · Construir el mes en bruto.

Se parte de la plantilla y del mes anterior: cada persona recibe su
turno base, se heredan los días que vienen del mes publicado y se
colocan los descansos fijos. Todavía no hay ninguna novedad aplicada.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

from gestor.dominio.calendario import dias_del_periodo
from gestor.dominio.cobertura import desde_texto

# Cómo se le cuenta a una persona un aviso de validación vive en su propio
# módulo: son ciento catorce líneas de texto que no dependen del horario.
from gestor.dominio.rotacion import turno_base_empleado
from gestor.dominio.vigencia import config_en_fecha, fechas_de_transicion
from gestor.motor.comun import (  # noqa: F401
    _codigo_administrativo_area,
    _codigo_guia_area,
    _es_ultimo_viernes_administrativo,
)
from gestor.motor.vocabulario import (  # noqa: F401
    OUT_OF_VIGENCY_CODE,
)


def ultimo_viernes_mes(mes: int, anio: int) -> str:
    """Devuelve la fecha ISO del último viernes del mes."""
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    f = date(anio, mes, ultimo_dia)
    while f.weekday() != 4:  # viernes
        f -= timedelta(days=1)
    return f.isoformat()

def construir_base(empleados: list[dict], mes: int, anio: int) -> list[dict]:
    # El periodo abarca semanas completas: puede empezar en el mes anterior y
    # terminar en el siguiente. Cada día lleva `mes_propio` para poder separar
    # después lo que cuenta como mes natural de lo que solo completa la semana.
    cal = dias_del_periodo(mes, anio)
    # El último viernes administrativo es una regla mensual, así que cada día
    # se compara con el último viernes de SU mes. Sin esto, los días que
    # completan la primera y la última semana perderían la marca —o la
    # ganarían por error— y la cobertura de ese día se leería mal.
    ultimos_viernes = {
        (d['anio'], d['mes']): ultimo_viernes_mes(d['mes'], d['anio'])
        for d in cal
    }
    # Una persona puede cambiar de configuración dentro del periodo —de turno
    # fijo a rotativo desde un lunes concreto, por ejemplo—. Cuando eso pasa,
    # el turno base de cada día se calcula con la plantilla tal como estaba
    # configurada **ese** día, no con la foto final del mes.
    hay_transiciones = any(x.get('cambios_config') for x in empleados)
    _plantillas: dict[str, tuple[list[dict], dict[int, dict]]] = {}

    def plantilla_del_dia(fecha_iso: str) -> tuple[list[dict], dict[int, dict]]:
        if not hay_transiciones:
            return empleados, {int(x['id']): x for x in empleados}
        if fecha_iso not in _plantillas:
            lista = [config_en_fecha(x, fecha_iso) for x in empleados]
            _plantillas[fecha_iso] = (lista, {int(x['id']): x for x in lista})
        return _plantillas[fecha_iso]

    out = []
    for e in empleados:
        transiciones = sorted(fechas_de_transicion(e))
        codigo_administrativo = _codigo_administrativo_area(e.get('area'))
        vigente_desde = str(e.get('vigente_desde') or '2026-08-01')[:10]
        vigente_hasta = str(e.get('desactivado_en') or '')[:10] if not bool(e.get('activo', 1)) else ''
        dias=[]
        for d in cal:
            f=date.fromisoformat(d['fecha'])
            plantilla, por_id = plantilla_del_dia(d['fecha'])
            e_dia = por_id.get(int(e['id']), e)
            codigo_administrativo_dia = _codigo_administrativo_area(e_dia.get('area'))
            vigente = d['fecha'] >= vigente_desde and (not vigente_hasta or d['fecha'] <= vigente_hasta)
            if not vigente:
                turno = OUT_OF_VIGENCY_CODE
                origen='fuera_vigencia'
                bloqueado=True
                obs='Fuera de la vigencia laboral del colaborador'
            else:
                turno = turno_base_empleado(e_dia, plantilla, f)
                origen='turno_base'
                bloqueado=False
                obs=''
                if e_dia['tipo_turno']=='administrativo':
                    if d['es_domingo'] or d['es_festivo']:
                        turno='D'
                        origen='descanso_administrativo'
                        bloqueado=True
                        obs='Descanso obligatorio administrativo (domingo/festivo)'
                    else:
                        turno=codigo_administrativo_dia
            dias.append({
                **d,
                'vigente': vigente,
                # Configuración con la que se decidió este día concreto. Las
                # validaciones diarias la usan para no juzgar un lunes con las
                # reglas que solo empezaron a regir el martes.
                'cfg_tipo_turno': e_dia.get('tipo_turno'),
                'cfg_turno_fijo': e_dia.get('turno_fijo'),
                'cfg_descanso_fijo': e_dia.get('descanso_fijo'),
                'cfg_pareja_id': e_dia.get('pareja_id'),
                # Primer día en que rige una configuración nueva. El turno
                # puede cambiar aquí por decisión explícita del usuario.
                'cambio_vigencia': d['fecha'] in transiciones,
                'es_ultimo_viernes_administrativo': d['fecha'] == ultimos_viernes.get((d['anio'], d['mes'])),
                'turno':turno,
                'turno_original':turno,
                'origen':origen,
                'bloqueado':bloqueado,
                'solicitud_id':None,
                'observacion':obs,
                'capacitacion_horas':0.0,
                'reemplaza_a':None,
                'reemplazado_por':None,
                'festivo_origen':None,
                'requerimiento_id':None,
            })
        out.append({
            'empleado_id':e['id'], 'nombre':e['nombre'], 'cargo':e.get('cargo','GUÍA SOCIAL'),
            'area':e['area'], 'tipo_turno':e['tipo_turno'],
            'turno_base':(codigo_administrativo if e['tipo_turno']=='administrativo' else ('AM/PM' if e['tipo_turno']=='rotativo' else e.get('turno_fijo'))),
            'descanso_fijo':e.get('descanso_fijo'), 'pareja_id':e.get('pareja_id'),
            'inicio_rotacion':e.get('inicio_rotacion'), 'fecha_ancla_rotacion':e.get('fecha_ancla_rotacion'),
            'orden_rotacion':e.get('orden_rotacion',0), 'exento_especiales':bool(e.get('exento_especiales',0)),
            # Qué días de la semana cuenta esta persona para el mínimo de su
            # área. `None` es lo normal: cuenta todos. Ver
            # `backend/cobertura_personal.py`.
            'cobertura_dias':(e.get('cobertura_dias')
                              if 'cobertura_dias' in e
                              else desde_texto(e.get('cobertura_dias_json'))),
            'vigente_desde':vigente_desde, 'vigente_hasta':vigente_hasta or None,
            # Días en que empieza a regir un cambio de configuración de turno.
            # Marcan la frontera entre dos semanas de rotación distintas y por
            # eso no cuentan como cambio de turno no autorizado.
            'transiciones_config': transiciones,
            'dias':dias,
        })
    return out

# Días que otro mes ya publicó
# ---------------------------------------------------------------------------
# Con el modelo de semanas completas, dos periodos consecutivos comparten la
# semana del cambio de mes. Esa semana ya se publicó con el mes anterior, así
# que aquí no se vuelve a decidir: se copia tal cual y se bloquea. De este modo
# nadie ve cambiar un turno que ya tenía confirmado, y las reglas que cruzan la
# frontera (máximo de días seguidos, descanso semanal, fatiga PM→AM) siguen
# viendo la semana entera y no un trozo suelto.
CODIGO_DIA_HEREDADO = 'periodo_anterior'

def aplicar_dias_heredados(horario: list[dict], heredados: Optional[dict[int, dict[str, dict]]]) -> int:
    """Copia y congela los días que el periodo oficial anterior ya cubría."""
    if not heredados:
        return 0
    copiados = 0
    for e in horario:
        mapa = heredados.get(int(e.get('empleado_id') or 0)) or {}
        if not mapa:
            continue
        for d in e.get('dias', []):
            previo = mapa.get(d.get('fecha'))
            if not previo:
                continue
            turno = str(previo.get('turno') or '').strip()
            if not turno:
                continue
            # Se conserva el origen con el que se decidió el día en el mes
            # anterior. Así las reglas que dependen de él —el viernes
            # administrativo general, un descanso fijo, un compensatorio de
            # festivo— siguen leyéndose igual y no aparecen conflictos
            # inventados sobre días que ya están publicados.
            origen_previo = str(previo.get('origen') or '') or CODIGO_DIA_HEREDADO
            observacion_previa = str(previo.get('observacion') or '')
            d.update(
                turno=turno,
                turno_original=turno,
                origen=origen_previo,
                bloqueado=True,
                heredado=True,
                # El día ya ocurrió y quedó publicado, así que la persona
                # estaba en plantilla. Si la configuración vigente de este mes
                # dice otra cosa —por ejemplo un alta con fecha posterior—, la
                # que manda es la realidad del mes anterior: de lo contrario el
                # día aparecería trabajado y a la vez fuera de vigencia, y no
                # contaría para la cobertura de esa fecha.
                vigente=turno != OUT_OF_VIGENCY_CODE,
                origen_heredado=origen_previo,
                observacion=(
                    f'{observacion_previa} · Publicado con el mes anterior'
                    if observacion_previa else 'Día publicado con la programación del mes anterior'
                ),
                capacitacion_horas=float(previo.get('capacitacion_horas') or 0),
                cobertura_operativa=previo.get('cobertura_operativa'),
                turno_operativo_origen=previo.get('turno_operativo_origen'),
                origen_descanso=previo.get('origen_descanso'),
                motivo_descanso=previo.get('motivo_descanso'),
                festivo_origen=previo.get('festivo_origen'),
            )
            copiados += 1
        # Si la configuración vigente dice que la persona entró después del
        # primer día heredado, la corrige: el día ya se publicó trabajado, así
        # que estaba en plantilla. Sin esto la ficha diría una cosa y el
        # horario otra, y esa semana no se le exigiría su descanso.
        trabajados = sorted(
            d['fecha'] for d in e.get('dias', [])
            if d.get('heredado') and d.get('turno') not in {OUT_OF_VIGENCY_CODE, ''}
        )
        if trabajados and str(e.get('vigente_desde') or '') > trabajados[0]:
            e['vigente_desde'] = trabajados[0]
    return copiados

def _turno_operativo(d: dict) -> Optional[str]:
    turno = d.get('turno')
    if turno in {'AM', 'PM'}:
        return turno
    for clave in ('cobertura_operativa', 'turno_operativo_origen'):
        valor = d.get(clave)
        if valor in {'AM', 'PM'}:
            return valor
    return None

def alinear_semanas_heredadas(horario: list[dict]) -> None:
    """El turno del lunes heredado manda en toda su semana.

    Una semana se trabaja entera en el mismo turno: no se pasa de AM a PM un
    miércoles. Si el lunes viene heredado del mes anterior, es ese lunes —y no
    la rotación teórica— quien fija el turno de los días que este periodo sí
    genera dentro de esa misma semana. Sin esto, el primer día publicado y el
    segundo podrían contradecirse.
    """
    for e in horario:
        if e.get('tipo_turno') != 'rotativo':
            continue
        por_semana: dict[str, list[dict]] = {}
        for d in e.get('dias', []):
            por_semana.setdefault(str(d.get('lunes_semana') or ''), []).append(d)
        for dias_semana in por_semana.values():
            heredados = [d for d in dias_semana if d.get('heredado')]
            if not heredados or len(heredados) == len(dias_semana):
                continue
            referencia = next(
                (_turno_operativo(d) for d in sorted(heredados, key=lambda x: str(x.get('fecha')))
                 if _turno_operativo(d)),
                None,
            )
            if referencia not in {'AM', 'PM'}:
                continue
            for d in dias_semana:
                if d.get('heredado') or d.get('bloqueado'):
                    continue
                if d.get('origen') != 'turno_base' or d.get('turno') not in {'AM', 'PM'}:
                    continue
                if d.get('turno') == referencia:
                    continue
                d.update(
                    turno=referencia,
                    turno_original=referencia,
                    origen='continuidad_semana_heredada',
                    observacion=(
                        'La semana continúa en el turno con el que quedó publicada '
                        'en el mes anterior'
                    ),
                )

def dias_heredados_desde_horario(anterior: list[dict], fechas: set[str]) -> dict[int, dict[str, dict]]:
    """Extrae de un horario ya oficial los días que otro periodo reutiliza."""
    out: dict[int, dict[str, dict]] = {}
    for e in anterior or []:
        try:
            eid = int(e.get('empleado_id'))
        except (TypeError, ValueError):
            continue
        mapa = {
            str(d.get('fecha')): {
                'turno': d.get('turno'),
                'origen': d.get('origen'),
                'observacion': d.get('observacion'),
                'capacitacion_horas': d.get('capacitacion_horas'),
                'cobertura_operativa': d.get('cobertura_operativa'),
                'turno_operativo_origen': d.get('turno_operativo_origen'),
                'origen_descanso': d.get('origen_descanso'),
                'motivo_descanso': d.get('motivo_descanso'),
                'festivo_origen': d.get('festivo_origen'),
            }
            for d in e.get('dias', [])
            if str(d.get('fecha')) in fechas and d.get('turno')
        }
        if mapa:
            out[eid] = mapa
    return out

def aplicar_descansos_fijos(horario: list[dict]):
    for e in horario:
        if e['tipo_turno']=='administrativo' or e.get('descanso_fijo') is None:
            continue
        for d in e['dias']:
            if not d.get('vigente', True) or d.get('heredado'):
                continue
            if d['dia_semana_numero']==e['descanso_fijo']:
                d.update(turno='D', origen='descanso_fijo', bloqueado=True, observacion='Descanso fijo obligatorio')

def aplicar_ultimo_viernes_administrativo(horario: list[dict]) -> list[str]:
    """Convierte el último viernes del mes en jornada administrativa global.

    Las instrucciones explícitas del usuario (ausencias, solicitudes, asignaciones
    directas y edición manual) conservan prioridad. La regla sí reemplaza el turno
    base y cualquier descanso fijo configurado, dejando que la validación señale
    claramente el choque si en el futuro alguien tiene descanso fijo los viernes.
    El día queda bloqueado para impedir que los descansos automáticos lo utilicen.
    """
    avisos: list[str] = []
    for e in horario:
        codigo = _codigo_guia_area(e.get('area'))
        if not codigo:
            continue
        for d in e.get('dias', []):
            if not d.get('vigente', True) or d.get('heredado'):
                continue
            if not _es_ultimo_viernes_administrativo(d):
                continue
            # Si el último viernes coincide con un festivo (p. ej. 25/12/2026),
            # se conserva la regla de festivo. Es una restricción de mayor
            # prioridad y evita convertir un descanso festivo obligatorio en
            # jornada administrativa de forma silenciosa.
            if d.get('es_festivo') or d.get('es_domingo'):
                continue

            origen = str(d.get('origen') or '')
            explicito = (
                origen.startswith('solicitud:')
                or origen.startswith('requerimiento:')
                or origen == 'ajuste_manual'
                or d.get('solicitud_id') is not None
                or d.get('requerimiento_id') is not None
                or d.get('turno') in {'VAC', 'INC', 'PER', 'CAP'}
            )
            # Una regla habitual no es una instrucción para este viernes: es lo
            # que se hace mientras nadie diga otra cosa, y el último viernes
            # administrativo lo dice para todo el personal. Sin esto, un
            # «todos los viernes en PM» dejaba a esa persona fuera de la
            # jornada administrativa todos los meses.
            if d.get('origen_habitual'):
                explicito = False
            if explicito:
                continue

            anterior = d.get('turno')
            d.update(
                turno=codigo,
                origen='ultimo_viernes_administrativo',
                bloqueado=True,
                observacion='Último viernes del mes: jornada administrativa para todo el personal',
                cobertura_operativa=None,
                turno_operativo_origen=anterior if anterior in {'AM', 'PM'} else d.get('turno_operativo_origen'),
            )
            if anterior == 'D' and origen == 'descanso_fijo':
                avisos.append(
                    f"{e['nombre']}: su descanso fijo coincide con el último viernes administrativo {d['fecha']}; "
                    "la regla global dejó la jornada administrativa y la validación exigirá resolver el descanso fijo."
                )
    return avisos
