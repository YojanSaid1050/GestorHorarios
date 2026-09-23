# -*- coding: utf-8 -*-
"""Comprobador independiente: cada norma, a mano, sobre meses generados.

**No llama a `validar_horario` a propósito.** Vuelve a implementar cada regla
desde su enunciado, para que un fallo del motor y un fallo de su propia
validación no se tapen el uno al otro. Si las dos estuvieran mal de la misma
manera —que es lo que pasa cuando alguien "arregla" la validación para que
acepte lo que el motor produce— las pruebas normales seguirían en verde y esto
no.

Lo que sí conoce son las excepciones legítimas, y cada una está aquí porque al
escribirla saltó y hubo que ir a mirar por qué:

* el **último viernes administrativo**: ese día el área entera hace jornada ADM
  y nadie está en AM ni en PM, y es correcto;
* los días **heredados de la base histórica** (`origen` que empieza por
  `base_`): son la transcripción del Excel real de la oficina, no se pueden
  cambiar desde el mes nuevo y por eso no se le reprochan a él. **Pero sí se
  informan**, marcados como heredados: callarlos fue el error de la versión
  anterior, y por eso un viernes de Atención al Ciudadano sin nadie cubriendo
  estuvo meses sin aparecer en ninguna pantalla;
* la **primera semana** de un período, que se comparte con el mes anterior: el
  descanso semanal pudo caer en un día que este mes no ve;
* la válvula de que un mínimo **nunca puede exigir a toda el área a la vez**,
  porque entonces nadie podría descansar.

Y una distinción que este archivo se comió durante varias versiones: **la
jornada administrativa de Atención al Ciudadano no cubre ningún turno**. ADM-AC
es un horario propio y permanente, no releva a nadie; ADM-GS sí cubre, porque
esa persona seguía en la franja que le tocaba. Contando ADM-AC como «alguien
trabajando», un día en el que toda Atención al Ciudadano descansa salvo la
administrativa pasaba la auditoría, que es justo el día que hay que denunciar.
"""
from __future__ import annotations

import collections
from datetime import date

TRABAJO = {'AM', 'PM', 'ADM-GS', 'ADM-AC', 'CAP'}
CONSERVAN_SU_FRANJA = {'ADM-GS', 'CAP'}
# Turnos que además **cubren** un turno operativo. ADM-AC está en TRABAJO
# —quien lo tiene trabaja, y por eso no necesita descanso ese día— pero no está
# aquí: no releva a nadie en AM ni en PM.
CUBREN_TURNO = {'AM', 'PM', 'ADM-GS', 'CAP'}
NO_TRABAJO = {'D', 'VAC', 'INC', 'PER'}
FUERA = 'NV'
AREAS = ('gestion_social', 'comunicaciones', 'atencion_ciudadano')
NOMBRES = {'gestion_social': 'Gestión Social', 'comunicaciones': 'Comunicaciones',
           'atencion_ciudadano': 'Atención al Ciudadano'}


def _dias(fila):
    return {d['fecha']: d for d in fila.get('dias', [])}


def _es_heredado(*dias):
    """¿Estos días vienen de un mes ya publicado?

    Un día heredado no se puede cambiar desde el mes que se está generando: es
    la última semana del mes anterior, que la oficina ya tiene en la mano. Se
    informa igual —callarlo fue el error de la versión anterior— pero marcado,
    para no reprocharle al mes nuevo algo que no decidió.
    """
    return all(str(d.get('origen') or '').startswith('base_') or d.get('heredado')
               for d in dias if d)


def _franja(dia):
    """Qué franja operativa cubre esa casilla, según el enunciado de la norma.

    AM y PM se cubren a sí mismas. **La jornada administrativa general conserva
    la franja que la persona tenía ese día**: cambia lo que hace, no el hueco
    que deja en el cuadro. ADM-AC, en cambio, es un horario propio y permanente
    de Atención al Ciudadano y no cubre nada.

    Esta función se escribió primero contando solo AM y PM, y denunció como
    incumplimiento un día que sí estaba cubierto por alguien en jornada
    administrativa. Se corrigió mirando el enunciado, no mirando lo que hace el
    motor: los campos que se leen aquí son datos del horario —qué turno traía
    esa persona—, no la decisión del motor sobre si eso vale.
    """
    turno = dia.get('turno')
    if turno in ('AM', 'PM'):
        return turno
    if turno not in CONSERVAN_SU_FRANJA:
        return None
    if dia.get('cobertura_operativa') in ('AM', 'PM'):
        return dia['cobertura_operativa']
    for campo in ('turno_operativo_origen', 'turno_original', 'turno_base'):
        if dia.get(campo) in ('AM', 'PM'):
            return dia[campo]
    return None


def _cubre(fila, dia):
    """¿Cuenta esta persona ese día para el mínimo de su área?"""
    dias = fila.get('cobertura_dias')
    if dias is None:
        return True
    return int(dia.get('dia_semana_numero', -1)) in set(dias)


def _semanas(horario):
    por_semana = collections.defaultdict(set)
    for fila in horario:
        for d in fila['dias']:
            por_semana[str(d.get('lunes_semana') or '')].add(d['fecha'])
    return {k: sorted(v) for k, v in por_semana.items() if k}


def auditar(horario, reglas_area, festivos_conocidos=None):
    """Devuelve una lista de incumplimientos. Vacía = el mes cumple."""
    fallos = []
    def anotar(norma, detalle, heredado=False):
        # Los heredados se marcan y no se ocultan. La versión anterior los
        # saltaba, y por eso un viernes sin cobertura en Atención al Ciudadano
        # estuvo meses sin salir en ninguna pantalla.
        fallos.append((f'{norma} (heredado)' if heredado else norma, detalle))

    fechas = sorted({d['fecha'] for f in horario for d in f['dias']})
    por_area = collections.defaultdict(list)
    for f in horario:
        por_area[f['area']].append(f)

    # ---------- 1. Ninguna casilla vacía y un solo turno por día ----------
    for f in horario:
        vistas = collections.Counter(d['fecha'] for d in f['dias'])
        repetidas = [k for k, v in vistas.items() if v > 1]
        if repetidas:
            anotar('un turno por día', f"{f['nombre']}: {repetidas[0]} aparece dos veces")
        for d in f['dias']:
            if not str(d.get('turno') or '').strip():
                anotar('sin casillas vacías', f"{f['nombre']}: {d['fecha']} sin turno")
            if '+' in str(d.get('turno') or ''):
                anotar('sin doble jornada', f"{f['nombre']}: {d['fecha']} = {d['turno']}")

    # ---------- 2. Cobertura mínima y techos, día a día ----------
    for area in AREAS:
        filas = por_area.get(area) or []
        if not filas:
            continue
        regla = reglas_area.get(area) or {}
        am_min = int(regla.get('am_minimo') or 0)
        pm_min = int(regla.get('pm_minimo') or 0)
        min_area = int(regla.get('minimo_area') or 0)
        am_max = regla.get('am_maximo')
        pm_max = regla.get('pm_maximo')
        for fecha in fechas:
            presentes = {'AM': 0, 'PM': 0}
            trabajando = 0
            vigentes = 0
            dias_del_area = [_dias(f).get(fecha) for f in filas]
            dias_del_area = [d for d in dias_del_area if d]
            # El último viernes administrativo el área entera hace jornada ADM:
            # ese día nadie está en AM ni en PM, y es a propósito.
            if any(d.get('es_ultimo_viernes_administrativo') for d in dias_del_area):
                continue
            # Los días heredados de la base histórica son una transcripción del
            # Excel real de la oficina: se conservan tal cual y no se juzgan.
            heredado = _es_heredado(*dias_del_area)
            for f in filas:
                d = _dias(f).get(fecha)
                if not d or d.get('turno') == FUERA or d.get('vigente') is False:
                    continue
                vigentes += 1
                franja = _franja(d) if _cubre(f, d) else None
                if franja:
                    trabajando += 1
                    presentes[franja] += 1
            if vigentes == 0:
                continue
            # El suelo nunca puede exigir a toda el área: alguien tiene que
            # poder descansar. Es la misma válvula que aplica el motor.
            tope_exigible = max(0, vigentes - 1)
            if am_min and presentes['AM'] < min(am_min, tope_exigible):
                anotar('cobertura AM',
                       f"{NOMBRES[area]} {fecha}: {presentes['AM']} en AM, exige {am_min}",
                       heredado)
            if pm_min and presentes['PM'] < min(pm_min, tope_exigible):
                anotar('cobertura PM',
                       f"{NOMBRES[area]} {fecha}: {presentes['PM']} en PM, exige {pm_min}",
                       heredado)
            if min_area and trabajando < min(min_area, tope_exigible):
                anotar('cobertura del área',
                       f"{NOMBRES[area]} {fecha}: {trabajando} trabajando, "
                       f"exige {min_area}", heredado)
            if am_max is not None and presentes['AM'] > int(am_max):
                anotar('techo AM',
                       f"{NOMBRES[area]} {fecha}: {presentes['AM']} en AM, techo {am_max}",
                       heredado)
            if pm_max is not None and presentes['PM'] > int(pm_max):
                anotar('techo PM',
                       f"{NOMBRES[area]} {fecha}: {presentes['PM']} en PM, techo {pm_max}",
                       heredado)

    # ---------- 3. Descanso semanal ----------
    semanas = _semanas(horario)
    primera = min(semanas) if semanas else None
    for f in horario:
        dias = _dias(f)
        for lunes, fechas_semana in semanas.items():
            if lunes == primera:
                continue                      # se comparte con el mes anterior
            propias = [dias[x] for x in fechas_semana if x in dias]
            if len(propias) < 7:
                continue
            if any(str(d.get('origen') or '').startswith('base_') for d in propias):
                continue
            if all(d.get('turno') == FUERA or d.get('vigente') is False for d in propias):
                continue
            if not any(d['turno'] in NO_TRABAJO for d in propias):
                anotar('descanso semanal',
                       f"{f['nombre']}: la semana del {lunes} sin ningún día libre")

    # ---------- 4. Jornadas seguidas ----------
    for f in horario:
        racha = mayor = 0
        desde = None
        for d in sorted(f['dias'], key=lambda x: x['fecha']):
            if d['turno'] in TRABAJO:
                if racha == 0:
                    desde = d['fecha']
                racha += 1
                mayor = max(mayor, racha)
            else:
                racha = 0
        if mayor > 14:
            anotar('tope absoluto de jornadas',
                   f"{f['nombre']}: {mayor} jornadas seguidas desde {desde}")

    # ---------- 5. Transición PM → AM sin corte ----------
    for f in horario:
        ordenados = sorted(f['dias'], key=lambda x: x['fecha'])
        for previo, siguiente in zip(ordenados, ordenados[1:], strict=False):
            if previo['turno'] == 'PM' and siguiente['turno'] == 'AM':
                d1 = date.fromisoformat(previo['fecha'])
                d2 = date.fromisoformat(siguiente['fecha'])
                if (d2 - d1).days == 1:
                    anotar('transición PM → AM',
                           f"{f['nombre']}: PM el {previo['fecha']} y AM el {siguiente['fecha']}",
                           all(str(d.get('origen') or '').startswith('base_')
                               for d in (previo, siguiente)))

    # ---------- 6. Parejas de PC nunca en el mismo turno ----------
    por_id = {int(f['empleado_id']): f for f in horario}
    revisadas = set()
    for f in horario:
        pid = f.get('pareja_id')
        if not pid or int(pid) not in por_id:
            continue
        clave = tuple(sorted((int(f['empleado_id']), int(pid))))
        if clave in revisadas:
            continue
        revisadas.add(clave)
        otra = por_id[int(pid)]
        d1, d2 = _dias(f), _dias(otra)
        for fecha in fechas:
            a, b = d1.get(fecha), d2.get(fecha)
            if not a or not b:
                continue
            if a['turno'] in ('AM', 'PM') and a['turno'] == b['turno']:
                if a.get('requerimiento_id') or b.get('requerimiento_id'):
                    continue          # una asignación directa puede autorizarlo
                if a.get('excepcion_forzada') or b.get('excepcion_forzada'):
                    continue
                anotar('pareja de PC en el mismo turno',
                       f"{f['nombre']} y {otra['nombre']}: {a['turno']} el {fecha}",
                       _es_heredado(a, b))

    # ---------- 7. Compensatorio por festivo trabajado ----------
    festivos = sorted({d['fecha'] for f in horario for d in f['dias'] if d.get('es_festivo')})
    for f in horario:
        dias = _dias(f)
        for fecha in festivos:
            d = dias.get(fecha)
            if not d or d['turno'] not in TRABAJO:
                continue
            if not d.get('mes_propio', True):
                continue
            tiene = any(x.get('turno') == 'D'
                        and str(x.get('origen') or '') == 'compensatorio_festivo'
                        and x.get('festivo_origen') == fecha
                        for x in f['dias'])
            if not tiene:
                anotar('compensatorio de festivo',
                       f"{f['nombre']}: trabajó el festivo {fecha} y no tiene compensatorio")

    return fallos
