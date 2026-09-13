# -*- coding: utf-8 -*-
"""3 · Repartir lo que hay que repartir.

El descanso semanal de cada persona, los domingos y los festivos. Es la
parte que decide el motor por su cuenta, dentro de lo que las decisiones
de la etapa anterior dejaron libre.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from gestor.dominio.calendario import lunes_de
from gestor.motor.comun import (  # noqa: F401
    _asignar_d,
    _conteo_turno,
    _cuenta_descansos_semanales,
    _dia,
    _dias_ordenados,
    _es_descanso_semanal,
    _habilitar_descanso_con_reajuste_cobertura,
    _historial_semana,
    _lunes_iso_de_dia,
    _puede_descansar,
    _reparto_fijado,
    _semana_sin_jornada,
    _turnos_cobertura_dia,
    es_dia_del_mes,
    fechas_domingos,
    fechas_festivos,
    maximo_dias_consecutivos,
    minimo_area_cobertura,
    minimo_cobertura,
)
from gestor.motor.presupuesto import (
    queda_presupuesto,
)
from gestor.motor.vocabulario import (  # noqa: F401
    DOMINGOS_MITAD_EXACTA,
    FATIGUE_ADMIN_CODES,
    NONWORK_CODES,
    OUT_OF_VIGENCY_CODE,
    WORK_CODES,
)

# Cómo se le cuenta a una persona un aviso de validación vive en su propio
# módulo: son ciento catorce líneas de texto que no dependen del horario.
from gestor.servicios.reglas_cobertura import (
    descripcion_minimos_regla as descripcion_minimos_cobertura,
)
from gestor.servicios.reglas_cobertura import (
    regla as regla_cobertura,
)


def texto_minimos_area(area: str, fecha: Optional[str] = None) -> str:
    return descripcion_minimos_cobertura(regla_cobertura(area, fecha))

def _corta_transicion_pm_am(e: dict, d: dict) -> bool:
    """¿Descansar este día evita una transición PM → AM?

    Es el caso del lunes en el que alguien pasa de una semana PM a una semana
    AM: sale a las 21:00 del domingo y entraría a las 5:00 del lunes. Colocar
    ahí el descanso semanal —que de todas formas hay que colocar en algún
    sitio— resuelve la fatiga sin gastar un puente administrativo ni un día
    libre extra.
    """
    if d.get('turno') != 'AM':
        return False
    dias = _dias_ordenados(e)
    anterior = None
    for _orden, actual, _prev in dias:
        if actual is d:
            break
        anterior = actual
    if anterior is None:
        return False
    if str(anterior.get('fecha') or '') >= str(d.get('fecha') or ''):
        return False
    turno_anterior = anterior.get('turno')
    if turno_anterior == 'PM':
        return True
    return (
        turno_anterior in FATIGUE_ADMIN_CODES
        and anterior.get('turno_operativo_origen') == 'PM'
    )

def _coverage_ok_with_plan(horario:list[dict], fechas:list[str], plan:dict[tuple[int,str],bool]) -> bool:
    """plan[(empleado_id, fecha)] = True si trabaja, False si descansa.

    Comprueba la cobertura obligatoria de cada área con su regla vigente. Cada
    área tiene un suelo de personas trabajando —el que manda en Comunicaciones
    y en Atención al Ciudadano, donde no importa el turno— y puede tener además
    un mínimo propio de AM y de PM, como Gestión Social.
    """
    areas = {str(e.get('area') or '') for e in horario}
    for f in fechas:
        for area in sorted(areas):
            personas = [e for e in horario if e.get('area') == area]
            if not personas:
                continue
            am_minimo = minimo_cobertura(horario, area, 'AM', f)
            pm_minimo = minimo_cobertura(horario, area, 'PM', f)
            total_minimo = minimo_area_cobertura(horario, area, f)
            if am_minimo <= 0 and pm_minimo <= 0 and total_minimo <= 0:
                continue
            counts = {'AM': 0, 'PM': 0}
            trabajando = 0
            for e in personas:
                d = _dia(e, f)
                if not d:
                    continue
                turno = d['turno']
                if plan.get((e['empleado_id'], f)) is False:
                    turno = 'D'
                cubre_dia = _turnos_cobertura_dia({**d, 'turno': turno})
                if cubre_dia & {'AM', 'PM'}:
                    trabajando += 1
                for cubre in cubre_dia:
                    if cubre in counts:
                        counts[cubre] += 1
            if trabajando < total_minimo:
                return False
            if counts['AM'] < am_minimo or counts['PM'] < pm_minimo:
                return False
    return True

def _ultima_posicion_no_laborada(
    e: dict,
    inicio_periodo: date,
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
) -> Optional[int]:
    """Qué día de la semana descansó la persona justo antes de este periodo.

    Devuelve 1 para lunes y 7 para domingo. ``None`` si no hay dato: entonces
    el periodo arranca sin restricción heredada.
    """
    previos = (dias_previos or {}).get(int(e.get('empleado_id') or 0))
    items = previos if isinstance(previos, list) else ([previos] if previos else [])
    fechas_libres = [
        date.fromisoformat(str(x['fecha'])[:10])
        for x in items
        if x.get('fecha') and str(x.get('turno') or '') in NONWORK_CODES
        and date.fromisoformat(str(x['fecha'])[:10]) < inicio_periodo
    ]
    fechas_libres += [
        date.fromisoformat(d['fecha'])
        for d in e.get('dias', [])
        if d.get('turno') in NONWORK_CODES and date.fromisoformat(d['fecha']) < inicio_periodo
    ]
    if not fechas_libres:
        return None
    ultimo = max(fechas_libres)
    # Solo interesa si cae en la semana inmediatamente anterior: más atrás, la
    # racha ya se habría cortado por otra vía y el dato no restringe nada.
    if (inicio_periodo - ultimo).days > 7:
        return None
    return ultimo.weekday() + 1

def _plan_respeta_limite_descansos(
    e: dict,
    fechas: list[str],
    plan: dict[tuple[int, str], bool],
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
) -> bool:
    """¿Puede esta persona descansar justo esos domingos sin pasar del máximo?

    No basta con que el reparto sea bonito sobre el papel. Con un solo descanso
    semanal, entre el descanso de una semana y el de la siguiente hay
    ``(7 - p1) + (p2 - 1)`` jornadas, así que el descanso solo puede **avanzar**
    un día por semana cuando el máximo son siete jornadas seguidas. Una persona
    que cerró el mes anterior descansando un martes no puede descansar el
    domingo de la tercera semana de este: por muchas vueltas que se le dé, en
    el camino aparecen ocho jornadas encadenadas.

    Antes esto no se comprobaba: el reparto de domingos proponía un plan
    imposible, la reparación de máximo 7 lo deshacía entera y la persona
    terminaba trabajando todos los domingos del mes. Aquí se descarta el plan
    imposible **antes** de aplicarlo, y el resolutor elige otro que sí lo sea.

    Se avanza semana a semana guardando la posición más tardía que el descanso
    puede ocupar. Solo hace falta el máximo: descansar antes de lo permitido
    nunca rompe la racha, solo la acorta.
    """
    if not fechas:
        return True
    dias = sorted(e.get('dias', []), key=lambda d: d['fecha'])
    if not dias:
        return True
    avance = max(1, maximo_dias_consecutivos() - 6)
    inicio_periodo = date.fromisoformat(dias[0]['fecha'])
    previa = _ultima_posicion_no_laborada(e, inicio_periodo, dias_previos)
    tope = 7 if previa is None else min(7, previa + avance)

    semanas: dict[str, list[dict]] = {}
    for d in dias:
        semanas.setdefault(str(d.get('lunes_semana') or _lunes_iso_de_dia(d)), []).append(d)

    eid = int(e.get('empleado_id') or 0)
    for lunes in sorted(semanas):
        dias_semana = semanas[lunes]
        if len(dias_semana) < 7:
            # Semana partida por el inicio o el final del periodo: no impone
            # una posición completa y se deja pasar sin restringir.
            tope = 7
            continue
        # Días de esa semana en los que la persona ya sabe que no trabaja: los
        # que el plan marca como descanso y los que ya venían libres.
        posibles = []
        for d in dias_semana:
            libre = d.get('turno') in NONWORK_CODES
            clave = (eid, d['fecha'])
            if clave in plan:
                libre = not plan[clave]
            if libre:
                posibles.append(date.fromisoformat(d['fecha']).weekday() + 1)
        if posibles:
            # La semana ya tiene su descanso decidido: tiene que caber dentro
            # del tope, y la posición que cuenta es la última libre.
            if min(posibles) > tope:
                return False
            tope = min(7, max(p for p in posibles if p <= tope) + avance)
        else:
            # Semana sin descanso decidido: podrá colocarse en cualquier día
            # que no supere el tope. Si el tope ya no llega ni al lunes, no hay
            # forma de cortar la racha.
            if tope < 1:
                return False
            tope = min(7, tope + avance)
    return True

def _planificar_balance_fechas(
    horario: list[dict],
    fechas: list[str],
    objetivo_trabajo: int,
    origen: str,
    descripcion: str,
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
    variante: int = 0,
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
) -> list[str]:
    """Planifica domingos/festivos respetando cobertura de forma determinística.

    Cada persona debe trabajar exactamente ``objetivo_trabajo`` días especiales
    (salvo novedades aprobadas que hagan imposible el objetivo individual). La
    versión anterior intentaba encontrar una solución mediante miles de sorteos
    pseudoaleatorios; al exigir cobertura mínima simultánea AM/PM en Gestión Social era posible que
    existiera una solución y aun así no fuera encontrada.

    Aquí el problema se resuelve como un CSP/knapsack de elección múltiple:
    cada empleado aporta una de sus combinaciones posibles y un backtracking
    memoizado controla cuántos descansos puede soportar cada fecha/turno antes
    de bajar de la cobertura mínima. El resultado no depende de la suerte y las
    variantes solo cambian el orden de preferencia entre soluciones válidas.
    """
    import itertools
    from functools import lru_cache

    advertencias: list[str] = []
    variables = [
        e for e in horario
        if e['tipo_turno'] != 'administrativo'
        and e.get('descanso_fijo') is None
        and not e.get('exento_especiales')
    ]
    if not variables or not fechas:
        return advertencias

    # ---------------------------------------------------------------
    # 1. Alternativas individuales: cada set contiene las fechas que
    #    la persona TRABAJA. Las demás fechas flexibles serán D.
    # ---------------------------------------------------------------
    opciones: dict[int, list[set[str]]] = {}
    for e in variables:
        forced_work: list[str] = []
        flex: list[str] = []
        for f in fechas:
            d = _dia(e, f)
            if not d:
                continue
            if d['turno'] in NONWORK_CODES:
                # Ya está libre por una novedad/descanso bloqueado.
                continue
            if d['bloqueado'] and d['turno'] in WORK_CODES:
                forced_work.append(f)
            elif d['turno'] in {'AM', 'PM'}:
                flex.append(f)
            elif d['turno'] in WORK_CODES:
                forced_work.append(f)

        # Con una cantidad impar de días especiales, tanto floor(n/2) como
        # ceil(n/2) representan un reparto mitad/mitad razonable. Esto es
        # imprescindible cuando la cobertura 1+1 exige que algunas personas
        # trabajen un día especial adicional. Con cantidad par, ambos límites
        # coinciden y el reparto sigue siendo exactamente la mitad.
        max_objetivo = objetivo_trabajo + (0 if DOMINGOS_MITAD_EXACTA else len(fechas) % 2)
        totales_permitidos = list(range(objetivo_trabajo, max_objetivo + 1))
        choices: list[set[str]] = []
        for total_work in totales_permitidos:
            need = total_work - len(forced_work)
            if 0 <= need <= len(flex):
                choices.extend(
                    set(c) | set(forced_work)
                    for c in itertools.combinations(flex, need)
                )

        if not choices:
            advertencias.append(
                f"{e['nombre']}: sus novedades aprobadas impiden cumplir el rango "
                f"equilibrado de {descripcion} ({objetivo_trabajo} a {max_objetivo} días trabajados)."
            )
            # Mejor esfuerzo individual: elige la cantidad alcanzable más
            # cercana al rango permitido para que las demás reglas sigan siendo
            # comprobables por la validación final.
            min_reachable = len(forced_work)
            max_reachable = len(forced_work) + len(flex)
            total_work = min(
                range(min_reachable, max_reachable + 1),
                key=lambda x: (
                    0 if objetivo_trabajo <= x <= max_objetivo
                    else min(abs(x - objetivo_trabajo), abs(x - max_objetivo)),
                    x,
                ),
            )
            need = max(0, min(len(flex), total_work - len(forced_work)))
            choices = [
                set(c) | set(forced_work)
                for c in itertools.combinations(flex, need)
            ] or [set(forced_work)]

        # Cada alternativa se puntúa por dos cosas que la validación final sí
        # mira, y que antes solo se descubrían cuando ya era tarde:
        #
        #   · **colisiones** — semanas que ya tienen un día no laborado y a las
        #     que este plan añadiría además el descanso del domingo. La persona
        #     descansaría dos veces esa semana y ninguna la siguiente.
        #   · **racha** — si el plan es alcanzable con un solo descanso
        #     semanal. Con máximo siete jornadas seguidas el descanso solo
        #     avanza un día por semana, así que hay domingos a los que
        #     sencillamente no se llega desde donde quedó el mes anterior.
        #
        # Ninguna de las dos descarta alternativas: si todas fallan, se elige
        # la menos mala y la validación final lo dirá. Las colisiones pesan más
        # porque duplicar un descanso rompe la semana entera, mientras que una
        # racha se puede reparar después moviendo un día.
        semanas_ocupadas = {
            str(d.get('lunes_semana') or _lunes_iso_de_dia(d))
            for d in e.get('dias', [])
            if d.get('turno') in NONWORK_CODES
        }
        semana_de = {
            f: str((_dia(e, f) or {}).get('lunes_semana') or '')
            for f in fechas
        }

        def _penalizacion(choice: set[str]) -> tuple[int, int]:
            colisiones = sum(
                1 for f in fechas
                if f not in choice and semana_de.get(f) in semanas_ocupadas
            )
            alcanzable = _plan_respeta_limite_descansos(
                e, fechas,
                {(e['empleado_id'], f): (f in choice) for f in fechas},
                historial_descansos, dias_previos,
            )
            return (colisiones, 0 if alcanzable else 1)

        # Entre planes igual de válidos se prefiere el que descansa justo en el
        # día que abre una transición PM→AM. Es el domingo en el que alguien
        # cierra una semana PM y el lunes siguiente empieza en AM: sale a las
        # 21:00 y entraría a las 5:00. Descansar ahí resuelve la fatiga con el
        # descanso que de todas formas había que dar, en lugar de gastar
        # después un puente administrativo.
        # Orden estable. ``variante`` rota las preferencias para producir otras
        # programaciones válidas sin alterar ninguna regla.
        choices = sorted(
            choices,
            key=lambda c: tuple(1 if f in c else 0 for f in fechas),
        )
        if choices:
            offset = (
                int(variante) * 131
                + int(e['empleado_id']) * 17
                + len(fechas) * 7
            ) % len(choices)
            choices = choices[offset:] + choices[:offset]
            if int(variante) % 2:
                choices = list(reversed(choices))

            # Orden estable: entre alternativas igual de limpias sigue
            # mandando la rotación anterior, que es la que da variedad a las
            # cinco programaciones alternativas del mes.
            choices.sort(key=_penalizacion)


        opciones[int(e['empleado_id'])] = choices

    # ---------------------------------------------------------------
    # 2. Resuelve las restricciones por área. Gestión Social y
    #    Comunicaciones no comparten cobertura entre sí, así que resolverlas
    #    por separado evita un producto cartesiano innecesario de estados.
    # ---------------------------------------------------------------
    selected_choice: dict[int, set[str]] = {}

    def resolver_area(area: str, area_vars: list[dict]) -> bool:
        if not area_vars:
            return True

        constraint_keys: list[tuple[str, str]] = []
        capacities: list[int] = []
        personas_area = [e for e in horario if e['area'] == area]
        # El área tiene un suelo de personas trabajando —el único que manda en
        # Comunicaciones y en Atención al Ciudadano, donde el turno da igual— y
        # puede tener además un mínimo propio de AM y de PM, como Gestión
        # Social. Se expresan las dos restricciones y se respetan ambas.
        for f in fechas:
            exigido_area = minimo_area_cobertura(horario, area, f)
            if exigido_area > 0:
                base = sum(
                    1 for e in personas_area
                    if (_dia(e, f) and _turnos_cobertura_dia(_dia(e, f)) & {'AM', 'PM'})
                )
                constraint_keys.append((f, 'TOTAL'))
                capacities.append(base - exigido_area)
            for turno in ('AM', 'PM'):
                exigido = minimo_cobertura(horario, area, turno, f)
                if exigido <= 0:
                    # Sin mínimo obligatorio ese turno no restringe el reparto.
                    continue
                base = sum(
                    1 for e in personas_area
                    if (_dia(e, f) and turno in _turnos_cobertura_dia(_dia(e, f)))
                )
                constraint_keys.append((f, turno))
                capacities.append(base - exigido)

        if any(c < 0 for c in capacities):
            return False

        key_index = {k: i for i, k in enumerate(constraint_keys)}

        def cost_vector(e: dict, choice: set[str]) -> tuple[int, ...]:
            cost = [0] * len(constraint_keys)
            for f in fechas:
                if f in choice:
                    continue
                d = _dia(e, f)
                if not d or d['turno'] not in {'AM', 'PM'}:
                    continue
                # Quien descansa resta a la vez del total del área y del
                # turno concreto que dejaba cubierto; ambas restricciones
                # pueden estar activas (Gestión Social tiene las dos).
                for clave in ((f, 'TOTAL'), (f, d['turno'])):
                    idx = key_index.get(clave)
                    if idx is not None:
                        cost[idx] += 1
            return tuple(cost)

        ordered = sorted(
            area_vars,
            key=lambda e: (
                len(opciones[int(e['empleado_id'])]),
                int(e['empleado_id']),
            ),
        )
        choice_costs: dict[int, list[tuple[set[str], tuple[int, ...]]]] = {}
        for e in ordered:
            eid = int(e['empleado_id'])
            choice_costs[eid] = [
                (choice, cost_vector(e, choice))
                for choice in opciones[eid]
            ]

        @lru_cache(maxsize=None)
        def solve(index: int, used: tuple[int, ...]) -> Optional[tuple[int, ...]]:
            if index >= len(ordered):
                return tuple()
            if not queda_presupuesto():
                return None
            e = ordered[index]
            eid = int(e['empleado_id'])
            for choice_idx, (_choice, cost) in enumerate(choice_costs[eid]):
                nuevo = tuple(used[i] + cost[i] for i in range(len(used)))
                if any(nuevo[i] > capacities[i] for i in range(len(nuevo))):
                    continue
                tail = solve(index + 1, nuevo)
                if tail is not None:
                    return (choice_idx,) + tail
            return None

        result = solve(0, tuple(0 for _ in constraint_keys))
        if result is None:
            return False
        for e, choice_idx in zip(ordered, result, strict=True):
            eid = int(e['empleado_id'])
            selected_choice[eid] = choice_costs[eid][choice_idx][0]
        return True

    # Cada área se resuelve por separado, con su propia regla de cobertura. Un
    # área sin mínimo obligatorio no restringe el reparto y puede escoger su
    # primera alternativa individual válida.
    referencia = fechas[0] if fechas else None
    nombres_area = {
        'gestion_social': 'Gestión Social',
        'comunicaciones': 'Comunicaciones',
        'atencion_ciudadano': 'Atención al Ciudadano',
    }
    restringidas = []
    libres = []
    for area_actual in ('gestion_social', 'comunicaciones', 'atencion_ciudadano'):
        del_area = [e for e in variables if e['area'] == area_actual]
        if not del_area:
            continue
        exige = any(
            minimo_cobertura(horario, area_actual, turno, f) > 0
            for turno in ('AM', 'PM') for f in fechas[:1]
        ) or any(
            minimo_area_cobertura(horario, area_actual, f) > 0 for f in fechas[:1]
        )
        (restringidas if exige else libres).append((area_actual, del_area))
    libres.extend(
        (e['area'], [e]) for e in variables
        if e['area'] not in nombres_area
    )

    for area_actual, del_area in restringidas:
        if not resolver_area(area_actual, del_area):
            advertencias.append(
                f"No existe una distribución de {descripcion} que mantenga la cobertura "
                f"mínima de {nombres_area.get(area_actual, area_actual)} "
                f"({texto_minimos_area(area_actual, referencia)})."
            )
            return advertencias

    for _area_libre, del_area in libres:
        for e in del_area:
            eid = int(e['empleado_id'])
            if opciones.get(eid):
                selected_choice[eid] = opciones[eid][0]

    # ---------------------------------------------------------------
    # 3. Materializa el plan y ejecuta una comprobación independiente.
    # ---------------------------------------------------------------
    best: dict[tuple[int, str], bool] = {}
    for e in variables:
        eid = int(e['empleado_id'])
        choice = selected_choice.get(eid)
        if choice is None:
            advertencias.append(
                f"{e['nombre']}: no se encontró una alternativa individual para {descripcion}."
            )
            return advertencias
        for f in fechas:
            best[(eid, f)] = f in choice

    if not _coverage_ok_with_plan(horario, fechas, best):
        advertencias.append(
            f"La distribución calculada de {descripcion} no superó la comprobación "
            "independiente de cobertura; no se aplicaron descansos especiales."
        )
        return advertencias
    # La comprobación de racha se aplica al construir las alternativas de cada
    # persona, no aquí. Si alguien viene del mes anterior con un descanso tan
    # temprano que ningún reparto le cabe, lo correcto es darle el mejor
    # reparto posible y avisar; descartar el plan completo dejaría a TODA el
    # área sin reparto de domingos por culpa de una sola persona.
    for e in variables:
        if not _plan_respeta_limite_descansos(
            e, fechas, best, historial_descansos, dias_previos
        ):
            advertencias.append(
                f"{e['nombre']}: cerró el periodo anterior descansando muy al principio de la "
                f"semana, así que en este no alcanza el reparto completo de {descripcion.lower()} "
                'sin superar el máximo de jornadas seguidas. Se aplica el reparto más cercano posible.'
            )

    for e in variables:
        eid = int(e['empleado_id'])
        for f in fechas:
            d = _dia(e, f)
            if not d or d['turno'] not in {'AM', 'PM'} or d['bloqueado']:
                continue
            if not best[(eid, f)]:
                _asignar_d(d, origen, descripcion)

    return advertencias

def _asignar_compensatorios_festivos(
    horario: list[dict],
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
) -> list[str]:
    """Da un día adicional por cada festivo trabajado.

    El compensatorio se ubica dentro de la misma semana calendario y nunca
    sustituye el descanso semanal. Si la persona descansó el festivo, el propio
    festivo ya satisface este derecho adicional y no se crea compensatorio.
    """
    advertencias: list[str] = []
    festivos = fechas_festivos(horario)
    if not festivos:
        return advertencias

    for e in horario:
        if e.get('tipo_turno') == 'administrativo':
            continue
        for fecha_festivo in festivos:
            fest = _dia(e, fecha_festivo)
            if not fest:
                continue
            # El festivo es un día **adicional**, no un cambio de sitio del
            # descanso que la persona ya tenía. Así que hay que reubicarlo
            # siempre que ese día no haya servido realmente como el día extra:
            #
            #   · lo trabajó → se le debe el día;
            #   · cayó en su domingo de descanso, que ya le tocaba por el
            #     reparto mensual → el domingo no puede contar dos veces;
            #   · cayó justo en su descanso fijo o en su descanso semanal → esa
            #     semana se quedaría con un solo día libre, que es el que
            #     tenía de todas formas.
            #
            # Solo cuando el propio festivo se le concedió como descanso de
            # festivo el derecho ya está servido y no se compensa nada.
            origen_festivo = str(fest.get('origen') or '')
            turno_festivo = fest.get('turno')
            # Un festivo heredado sí genera derecho: el día ya está decidido y
            # no se puede tocar, pero el compensatorio se ubica en cualquier
            # otro día del mes que sí sea de este periodo.
            if turno_festivo == OUT_OF_VIGENCY_CODE:
                continue
            if turno_festivo in {'VAC', 'INC', 'PER'}:
                # No estaba trabajando: el festivo no le quita nada.
                continue
            debe_compensar = (
                turno_festivo in WORK_CODES
                or (turno_festivo == 'D' and origen_festivo not in {
                    'descanso_festivo', 'descanso_especial_festivo',
                })
            )
            if not debe_compensar:
                continue

            lunes = date.fromisoformat(fecha_festivo) - timedelta(days=date.fromisoformat(fecha_festivo).weekday())
            domingo = lunes + timedelta(days=6)
            # Un compensatorio preexistente para este mismo festivo evita duplicados.
            ya = next((
                d for d in e['dias']
                if d.get('origen') == 'compensatorio_festivo'
                and d.get('festivo_origen') == fecha_festivo
            ), None)
            if ya:
                continue

            candidatos = []
            for d in e['dias']:
                # El compensatorio es un derecho independiente del descanso
                # semanal. Se prefiere la misma semana del festivo, pero si la
                # cobertura 1+1 no lo permite puede ubicarse en otro día del
                # mismo mes. Esto evita invalidar una programación viable por
                # una restricción artificial de calendario.
                if d.get('es_domingo') or d.get('es_festivo'):
                    continue
                if d.get('turno') not in {'AM', 'PM'} or d.get('bloqueado'):
                    continue
                if not _puede_descansar(horario, e, d):
                    continue
                candidatos.append(d)

            festivo_date = date.fromisoformat(fecha_festivo)
            candidatos.sort(key=lambda d: (
                0 if lunes <= date.fromisoformat(d['fecha']) <= domingo else 1,
                0 if date.fromisoformat(d['fecha']) >= festivo_date else 1,
                abs((date.fromisoformat(d['fecha']) - festivo_date).days),
                -_conteo_turno(horario, e['area'], d['fecha'], d['turno']),
                d['fecha'],
            ))
            if not candidatos:
                advertencias.append(
                    f"{e['nombre']}: trabajó el festivo {fecha_festivo}, pero no fue posible ubicar un descanso compensatorio en el mes sin romper cobertura ni otras reglas."
                )
                continue

            d = candidatos[0]
            d.update(
                turno='D',
                origen='compensatorio_festivo',
                bloqueado=True,
                festivo_origen=fecha_festivo,
                observacion=f'Descanso compensatorio por festivo trabajado el {fecha_festivo}',
            )
    return advertencias

def asignar_balance_especiales(
    horario:list[dict],
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
    variante: int = 0,
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
) -> list[str]:
    """Domingos y festivos se administran por separado.

    - Domingos conservan el reparto equilibrado mensual.
    - Los festivos son un descanso adicional independiente. Quien descansa el
      festivo ya recibe ese día; quien lo trabaja recibe otro D compensatorio.
    """
    advertencias: list[str] = []
    domingos = fechas_domingos(horario)
    festivos = fechas_festivos(horario)

    if domingos:
        advertencias.extend(_planificar_balance_fechas(
            horario,
            domingos,
            len(domingos) // 2,
            'descanso_domingo',
            'Balance de domingos',
            historial_descansos,
            variante,
            dias_previos,
        ))

    if festivos:
        advertencias.extend(_planificar_balance_fechas(
            horario,
            festivos,
            len(festivos) // 2,
            'descanso_festivo',
            'Descanso de festivos',
            historial_descansos,
            variante + 11,
            dias_previos,
        ))
        # Marca explícita del festivo descansado para que no sustituya el descanso semanal.
        for e in horario:
            for f in festivos:
                d = _dia(e, f)
                if d and d.get('turno') == 'D' and d.get('origen') == 'descanso_festivo':
                    d['festivo_origen'] = f
                    d['observacion'] = d.get('observacion') or 'Descanso correspondiente al festivo'
        advertencias.extend(_asignar_compensatorios_festivos(horario, historial_descansos))

    return advertencias

_ETIQUETA_AREA = {
    'gestion_social': 'Gestión Social',
    'atencion_ciudadano': 'Atención al Ciudadano',
    'comunicaciones': 'Comunicaciones',
}

def _domingos_de_continuidad(horario: list[dict]) -> list[str]:
    """Domingos del periodo que ya pertenecen al mes siguiente."""
    if not horario:
        return []
    propios = [d['fecha'] for d in horario[0]['dias'] if es_dia_del_mes(d)]
    if not propios:
        return []
    ultimo_propio = max(propios)
    return [
        d['fecha'] for d in horario[0]['dias']
        if d['es_domingo'] and not es_dia_del_mes(d) and d['fecha'] > ultimo_propio
    ]

def repartir_domingos_continuidad(horario: list[dict], variante: int = 0) -> list[str]:
    """Deja medio equipo descansando en el domingo que abre el mes siguiente.

    La última semana del periodo termina en un domingo que ya cuenta para el
    mes siguiente. Si aquí trabajase todo el mundo, ese mes empezaría con un
    domingo entero gastado y su reparto «trabaja 2, descansa 2» sería
    imposible de cumplir sin tocar un día ya publicado. Por eso el domingo de
    continuidad se reparte por mitades dentro de cada área, empezando por
    quienes más domingos han trabajado este mes. No es un descanso extra: es
    el descanso semanal de esa semana, colocado en domingo.
    """
    advertencias: list[str] = []
    domingos = _domingos_de_continuidad(horario)
    if not domingos:
        return advertencias
    domingos_mes = fechas_domingos(horario)
    for fecha in domingos:
        for area in sorted({str(e.get('area') or '') for e in horario}):
            gente = [
                e for e in horario
                if e.get('area') == area
                and e.get('tipo_turno') != 'administrativo'
                and e.get('descanso_fijo') is None
                and not e.get('exento_especiales')
            ]
            elegibles = []
            for e in gente:
                d = _dia(e, fecha)
                if not (d and d.get('vigente', True) and d.get('turno') in {'AM', 'PM'}
                        and not d.get('bloqueado')):
                    continue
                # Este domingo es el descanso semanal de esa semana, no uno
                # extra. Quien ya tiene su descanso colocado en otro día —por
                # ejemplo porque pidió moverlo al miércoles— trabaja el domingo:
                # si además descansara aquí, esa semana quedaría en cinco días
                # trabajados. Se queda fuera del reparto y el sitio se lo lleva
                # otra persona del área.
                if _cuenta_descansos_semanales(e, str(d.get('lunes_semana') or _lunes_iso_de_dia(d))):
                    continue
                elegibles.append(e)
            if len(elegibles) < 2:
                continue
            objetivo = (len(elegibles) + 1) // 2

            def trabajados(e: dict) -> int:
                return sum(
                    1 for f in domingos_mes
                    if (x := _dia(e, f)) and x.get('turno') in WORK_CODES
                )

            orden = sorted(
                elegibles,
                key=lambda e: (-trabajados(e), (int(e.get('empleado_id') or 0) + int(variante)) % 97, int(e.get('empleado_id') or 0)),
            )
            puestos = 0
            for e in orden:
                if puestos >= objetivo:
                    break
                d = _dia(e, fecha)
                if not d or not _puede_descansar(horario, e, d):
                    continue
                _asignar_d(
                    d, 'descanso_domingo',
                    'Descanso del domingo que abre el mes siguiente, para que ese mes '
                    'pueda repartir sus domingos por mitades',
                )
                puestos += 1
            if puestos < objetivo:
                advertencias.append(
                    f'Área {_ETIQUETA_AREA.get(area, area)}: solo {puestos} de {objetivo} personas '
                    f'pudieron descansar el domingo {fecha} sin dejar el turno descubierto. '
                    'El mes siguiente empezará con ese domingo desequilibrado.'
                )
    return advertencias

def asignar_descanso_semanal(
    horario: list[dict],
    historial_descansos: Optional[dict[int, dict[str, set[int]]]] = None,
    historial_no_laborados: Optional[dict[int, dict[str, set[int]]]] = None,
    variante: int = 0,
    dias_previos: Optional[dict[int, dict | list[dict]]] = None,
) -> list[str]:
    """Asigna el descanso semanal, incluso en semanas partidas entre meses.

    Reglas:
    - Si la porción del mes anterior de la misma semana ya tuvo D/VAC/INC/PER,
      esa semana ya tiene un día no laborado y no se agrega otro descanso normal.
    - Si la semana termina fuera del mes y todavía no hay día no laborado, se
      asigna dentro de los días visibles del mes actual. Así el siguiente mes
      podrá leerlo del historial y no duplicarlo.
    """
    advertencias: list[str] = []

    semanas = sorted({
        d['lunes_semana']
        for e in horario
        for d in e['dias']
        if d.get('lunes_semana')
    })
    ultima_fecha = date.fromisoformat(horario[0]['dias'][-1]['fecha']) if horario and horario[0].get('dias') else None

    for idx, lunes in enumerate(semanas):
        lunes_fecha = date.fromisoformat(lunes)
        domingo_fecha = lunes_fecha + timedelta(days=6)
        # La última semana parcial se completa al generar el mes siguiente. No
        # forzamos a que todos descansen en los pocos días que quedan del mes,
        # porque eso puede hacer imposible la cobertura. El siguiente mes leerá
        # esta porción desde el historial y completará el descanso pendiente.
        semana_final_parcial = bool(ultima_fecha and domingo_fecha > ultima_fecha)
        # También intentamos asignar descansos en la porción final del mes. Si
        # por cobertura alguno no cabe, queda pendiente para la porción inicial
        # del mes siguiente; la validación del mes actual no lo marca como error.
        def prioridad_descanso(e: dict) -> tuple[date, int]:
            """Atiende primero a quien alcanzará antes su octava jornada."""
            if e.get('tipo_turno') == 'administrativo' or e.get('descanso_fijo') is not None:
                return date.max, int(e.get('empleado_id') or 0)
            dias_e = [d for d in e.get('dias', []) if d.get('lunes_semana') == lunes]
            if not dias_e:
                return date.max, int(e.get('empleado_id') or 0)
            inicio = min(date.fromisoformat(d['fecha']) for d in dias_e)
            anteriores = [
                date.fromisoformat(d['fecha'])
                for d in e.get('dias', [])
                if date.fromisoformat(d['fecha']) < inicio and d.get('turno') in NONWORK_CODES
            ]
            limite = max(anteriores) + timedelta(days=7) if anteriores else date.max
            return limite, int(e.get('empleado_id') or 0)

        for e in sorted(horario, key=prioridad_descanso):
            if e['tipo_turno'] == 'administrativo' or e.get('descanso_fijo') is not None:
                continue

            dias = [d for d in e['dias'] if d.get('lunes_semana') == lunes]
            if not dias:
                continue
            dias_vigentes = [d for d in dias if d.get('vigente', True)]
            if not dias_vigentes:
                continue

            inicio_laboral = date.fromisoformat(str(e.get('vigente_desde') or '2026-08-01')[:10])
            fin_laboral = date.fromisoformat(str(e['vigente_hasta'])[:10]) if e.get('vigente_hasta') else None
            semana_inicio_laboral_parcial = lunes_fecha < inicio_laboral <= domingo_fecha
            semana_fin_laboral_parcial = bool(fin_laboral and lunes_fecha <= fin_laboral < domingo_fecha)
            # Ingreso o retiro a mitad de semana: no se crea un descanso ordinario
            # artificial para una semana en la que la relación laboral solo cubre
            # una fracción de los siete días.
            if semana_inicio_laboral_parcial or semana_fin_laboral_parcial:
                continue

            # Cualquier D/VAC/INC del mes actual o de la parte de esta misma
            # semana que quedó en el mes anterior satisface el descanso semanal.
            # El permiso no: ver `_es_descanso_semanal`.
            if any(_es_descanso_semanal(d) for d in dias):
                continue
            if _semana_sin_jornada(dias):
                continue
            if _historial_semana(historial_no_laborados or historial_descansos, e, lunes):
                continue

            # Un festivo descansado es el beneficio adicional del festivo y no
            # puede convertirse silenciosamente en el único descanso ordinario.
            candidatos = [
                d for d in dias
                if not d.get('es_festivo') and _puede_descansar(horario, e, d)
            ]

            if not candidatos and _reparto_fijado(e.get('area'), lunes):
                # Segunda oportunidad: repartir la cobertura dentro de la misma
                # área. Con un reparto como 2 AM + 1 PM, quien cubre PM no puede
                # descansar sin que otra persona del área pase ese día de AM a
                # PM. Es un intercambio interno, nunca personal de otra área ni
                # un descanso adicional.
                for candidato in sorted(
                    (
                        d for d in dias
                        if not d.get('es_festivo') and d.get('turno') in {'AM', 'PM'}
                        and not d.get('bloqueado')
                    ),
                    key=lambda d: (int(d['es_domingo']), d['fecha']),
                ):
                    habilitado, reajuste = _habilitar_descanso_con_reajuste_cobertura(
                        horario, e, candidato, 'el descanso semanal'
                    )
                    if habilitado:
                        candidatos = [candidato]
                        if reajuste:
                            advertencias.append(
                                f"{e['nombre']}: para su descanso del {candidato['fecha']}, "
                                f"{reajuste['persona']} pasó de {reajuste['antes']} a {reajuste['despues']} "
                                'ese día y el área conservó su cobertura obligatoria.'
                            )
                        break

            if not candidatos:
                if semana_final_parcial:
                    # Puede completarse en los días de esta misma semana que
                    # pertenecen al mes siguiente. No es una infracción del
                    # mes actual y se resolverá al generar el siguiente periodo.
                    continue
                advertencias.append(
                    f"{e['nombre']}: no fue posible asignar descanso en la semana del {lunes} "
                    "sin dejar un turno obligatorio descubierto."
                )
                continue

            # Un descanso por semana no basta si se ubica muy temprano en una
            # semana y muy tarde en la siguiente: entre ambos podrían aparecer
            # siete o más jornadas consecutivas. Cuando la cobertura lo permite,
            # limita la elección a fechas situadas como máximo siete días después
            # del último día no laborado ya programado para la persona.
            inicio_semana_visible = min(date.fromisoformat(d['fecha']) for d in dias)
            # La primera semana del periodo no tiene días anteriores dentro del
            # horario que se está construyendo, pero la persona sí venía de
            # algún sitio. Sin mirar el mes anterior, el descanso de esa semana
            # se colocaba demasiado tarde, la reparación de máximo 7 tenía que
            # adelantarlo después y, al hacerlo, deshacía el reparto de
            # domingos que ya estaba planificado.
            previos_mes_anterior = (dias_previos or {}).get(int(e.get('empleado_id') or 0))
            items_previos = (
                previos_mes_anterior if isinstance(previos_mes_anterior, list)
                else ([previos_mes_anterior] if previos_mes_anterior else [])
            )
            no_laborados_previos = sorted(
                [
                    date.fromisoformat(x['fecha'])
                    for x in e.get('dias', [])
                    if date.fromisoformat(x['fecha']) < inicio_semana_visible
                    and x.get('turno') in NONWORK_CODES
                ] + [
                    date.fromisoformat(str(x['fecha'])[:10])
                    for x in items_previos
                    if x.get('fecha') and str(x.get('turno') or '') in NONWORK_CODES
                    and date.fromisoformat(str(x['fecha'])[:10]) < inicio_semana_visible
                ]
            )
            if no_laborados_previos:
                fecha_limite = no_laborados_previos[-1] + timedelta(days=maximo_dias_consecutivos())
                antes_del_limite = [
                    d for d in candidatos
                    if date.fromisoformat(d['fecha']) <= fecha_limite
                ]
                if antes_del_limite:
                    candidatos = antes_del_limite

            # Mirar también hacia adelante. Si la persona ya tiene un día no
            # laborado planificado más adelante —normalmente el domingo que le
            # asignó el balance de días especiales—, colocar el descanso de esta
            # semana demasiado pronto deja más de siete jornadas seguidas entre
            # ambos y obliga a deshacer después ese balance.
            fin_semana_visible = max(date.fromisoformat(d['fecha']) for d in dias)
            siguientes_no_laborados = sorted(
                date.fromisoformat(x['fecha'])
                for x in e.get('dias', [])
                if date.fromisoformat(x['fecha']) > fin_semana_visible
                and x.get('turno') in NONWORK_CODES
            )
            if siguientes_no_laborados:
                # El descanso solo puede avanzar `maximo_dias_consecutivos() - 6`
                # posiciones por semana. Así que un domingo ya reservado dentro
                # de dos semanas no obliga a descansar el sábado de esta, sino
                # a no descansar antes del viernes: hay dos saltos por delante.
                # Mirar solo un salto —que es lo que hacía la versión anterior—
                # dejaba el descanso en lunes, y desde ahí el domingo reservado
                # se volvía inalcanzable y la reparación acababa borrándolo.
                objetivo = siguientes_no_laborados[0]
                saltos = max(1, (lunes_de(objetivo) - lunes_fecha).days // 7)
                avance_semanal = max(1, maximo_dias_consecutivos() - 6)
                posicion_minima = (objetivo.weekday() + 1) - saltos * avance_semanal
                compatibles = [
                    d for d in candidatos
                    if (date.fromisoformat(d['fecha']).weekday() + 1) >= posicion_minima
                ]
                if compatibles:
                    candidatos = compatibles

            # Preferencia por el día que además corta una transición PM→AM.
            # Cuando alguien cambia de semana PM a semana AM, el domingo
            # termina a las 21:00 y el lunes empieza a las 5:00. Si el descanso
            # semanal se coloca justo en ese lunes, la transición desaparece
            # sola y no hace falta ningún puente administrativo. Antes esto no
            # se podía aprovechar: el lunes del cambio caía en el mes siguiente
            # y no estaba en el horario que se estaba generando.
            # En la última semana del periodo el descanso se coloca lo más
            # tarde que permitan las reglas. Es la semana con la que arranca el
            # mes siguiente: si el descanso cae en lunes o martes, la persona
            # entra al mes nuevo con cinco o seis jornadas ya encadenadas y su
            # descanso queda clavado a principio de semana durante semanas,
            # lo que hace imposible su reparto de domingos. Colocándolo tarde,
            # el mes siguiente empieza con margen.
            #
            # En esa última semana la fecha manda por encima del reparto de
            # cobertura del día. La razón es aritmética: con un solo descanso
            # semanal, entre el descanso de una semana y el de la siguiente hay
            # (7 - p1) + (p2 - 1) jornadas, así que el descanso solo puede
            # avanzar un día por semana. Quien cierra el mes descansando un
            # martes entra al mes siguiente obligado a descansar miércoles, y
            # desde ahí no alcanza ningún domingo: su reparto dominical queda
            # roto de antemano. Cerrar en sábado o domingo deja al mes
            # siguiente con margen para repartir los domingos.
            ultima_semana = idx == len(semanas) - 1
            candidatos.sort(
                key=lambda d: (
                    int(bool(d.get('descanso_permitido'))),
                    -int(_corta_transicion_pm_am(e, d)),
                    int(d['es_domingo'] or d['es_festivo']),
                    *((-d['dia_semana_numero'], -_conteo_turno(horario, e['area'], d['fecha'], d['turno']))
                      if ultima_semana else
                      (-_conteo_turno(horario, e['area'], d['fecha'], d['turno']),
                       (d['dia_semana_numero'] - (e['empleado_id'] + idx + int(variante) * 2) % 7) % 7)),
                    d['fecha'],
                )
            )
            elegido = candidatos[0]
            if elegido.get('descanso_permitido'):
                # La asignación cubría toda la semana. El descanso semanal es
                # obligatorio, así que se coloca dentro de ella y se avisa: el
                # turno asignado sigue vigente los demás días.
                advertencias.append(
                    f"{e['nombre']}: la asignación directa cubría toda la semana del {lunes}, "
                    f"así que su descanso semanal se ubicó el {elegido['fecha']}. "
                    'El turno asignado se mantiene el resto de la semana.'
                )
                _asignar_d(
                    elegido, 'descanso_automatico',
                    'Descanso semanal dentro de una semana asignada por completo',
                )
            else:
                _asignar_d(elegido, 'descanso_automatico', 'Descanso semanal automático')

    return advertencias
