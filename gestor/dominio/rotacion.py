from datetime import date, timedelta

from gestor.dominio.calendario import lunes_de


# La rotación consulta las reglas de cobertura para no proponer un reparto que
# el área no admite. Se importan dentro de las funciones y no aquí arriba porque
# `servicios` lee la base y `dominio` no debería depender de ella al importarse:
# así este archivo se sigue pudiendo cargar sin base delante.
def _reglas():
    from gestor.servicios import reglas_cobertura
    return reglas_cobertura


def minimo_cobertura_area(area, turno, fecha=None, rotativos=None):
    return _reglas().minimo(area, turno, fecha)


def maximo_cobertura_area(area, turno, fecha=None, disponibles=None):
    return _reglas().maximo(area, turno, fecha, disponibles)


def regla_cobertura(area, fecha=None):
    return _reglas().regla(area, fecha)


ADMIN_CODE_BY_AREA = {
    'gestion_social': 'ADM-GS',
    'atencion_ciudadano': 'ADM-AC',
    'comunicaciones': 'ADM-GS',
}


def turno_contrario(turno: str) -> str:
    return 'PM' if turno == 'AM' else 'AM'


def turno_rotativo(inicio: str, ancla: str | date, fecha: str | date) -> str:
    if isinstance(ancla, str):
        ancla = date.fromisoformat(ancla)
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    if ancla.weekday() != 0:
        raise ValueError('La fecha ancla debe ser lunes.')
    semanas = (lunes_de(fecha) - ancla).days // 7
    return inicio if semanas % 2 == 0 else turno_contrario(inicio)


def _lunes_grupo(grupo: list[dict], fecha: date) -> tuple[date, int]:
    anclas = [date.fromisoformat(str(e['fecha_ancla_rotacion'])) for e in grupo if e.get('fecha_ancla_rotacion')]
    ancla = min(anclas) if anclas else date(2026, 8, 31)
    lunes = lunes_de(fecha)
    return ancla, (lunes - ancla).days // 7




def _vigente_en_fecha(empleado: dict, fecha: date) -> bool:
    """Indica si la persona forma parte de la plantilla operativa ese día."""
    ingreso = str(empleado.get('vigente_desde') or '2026-08-01')[:10]
    if fecha.isoformat() < ingreso:
        return False
    if bool(empleado.get('activo', 1)):
        return True
    retiro = str(empleado.get('desactivado_en') or '')[:10]
    return bool(retiro and fecha.isoformat() <= retiro)

def _vigente_en_semana(empleado: dict, fecha: date) -> bool:
    """¿Forma parte de la plantilla en algún día de esa semana?

    El carrusel de turnos gira por semanas, no por días: quién está en AM y
    quién en PM se decide una vez, el lunes, y vale los siete días. Si la
    pertenencia al grupo se midiera día a día, alguien que entra un martes
    cambiaría el reparto a mitad de semana y obligaría a otra persona a pasar
    de AM a PM un miércoles, que es justo lo que la regla prohíbe.
    """
    lunes = fecha - timedelta(days=fecha.weekday())
    return any(_vigente_en_fecha(empleado, lunes + timedelta(days=i)) for i in range(7))


def _efectivos_de_la_semana(rotativos: list[dict], fecha: date) -> list[dict]:
    """Quiénes cuentan de verdad para repartir la semana.

    La pertenencia al grupo se decide por semana entera y no día a día: si no,
    alguien que entra un martes cambiaría el reparto a media semana y obligaría
    a otra persona a pasar de AM a PM un miércoles, que es justo lo que la
    aplicación prohíbe. Pero contar a quien se va el lunes durante toda la
    semana tenía un efecto feo: se le reservaba la tarde y nadie la cubría. Se
    encontró con una prueba de recorrido largo —Comunicaciones se quedaba con
    dos personas y las dos aparecían en AM el sábado, porque la tarde estaba
    apartada para alguien que ya se había ido el lunes—.

    La medida es el domingo, el último día de la semana: quien siga ahí ese día
    reparte, y quien ya no esté no ocupa un turno que no va a hacer. Como el
    criterio es el mismo los siete días, nadie cambia de franja a media semana.
    """
    domingo = fecha - timedelta(days=fecha.weekday()) + timedelta(days=6)
    efectivos = [e for e in rotativos if _vigente_en_fecha(e, domingo)]
    return efectivos or rotativos


def _reparto_rotativos(area: str, fecha: date, rotativos: int,
                       fijos_am: int, fijos_pm: int) -> int:
    """Cuántos rotativos deben quedar en AM según la regla vigente del área.

    Parte del objetivo configurado (por ejemplo `2 AM / 1 PM`), descuenta lo que
    ya cubren los fijos y ajusta el resultado para no romper ningún mínimo
    obligatorio. Sin objetivo configurado deja un único rotativo en AM, que es el
    reparto histórico de Comunicaciones.
    """
    actual = regla_cobertura(area, fecha)
    am_minimo = minimo_cobertura_area(area, 'AM', fecha, rotativos)
    pm_minimo = minimo_cobertura_area(area, 'PM', fecha, rotativos)
    # El techo se consulta con la gente que realmente hay que repartir ese
    # día: si el área creció por encima de lo que la política admitía, el techo
    # cede en lugar de amontonar a todo el mundo en una franja.
    disponibles = rotativos + fijos_am + fijos_pm
    am_maximo = maximo_cobertura_area(area, 'AM', fecha, disponibles)
    pm_maximo = maximo_cobertura_area(area, 'PM', fecha, disponibles)

    if actual.am_objetivo is None:
        objetivo_am = fijos_am + (0 if fijos_am else 1)
    else:
        objetivo_am = int(actual.am_objetivo)

    en_am = max(0, min(rotativos, objetivo_am - fijos_am))
    # El techo por turno acota el reparto antes que nada: si PM solo admite una
    # persona, el resto del área tiene que ir a AM aunque el objetivo diga otra
    # cosa. Y al revés con el techo de AM.
    if pm_maximo is not None:
        en_am = max(en_am, rotativos - max(0, int(pm_maximo) - fijos_pm))
    if am_maximo is not None:
        en_am = min(en_am, max(0, int(am_maximo) - fijos_am))
    # El mínimo obligatorio manda sobre el reparto normal.
    if fijos_pm + (rotativos - en_am) < pm_minimo:
        en_am = max(0, rotativos - max(0, pm_minimo - fijos_pm))
    if fijos_am + en_am < am_minimo:
        en_am = min(rotativos, max(en_am, am_minimo - fijos_am))
    # Un area que se cubre entera con gente rotativa no puede quedarse con una
    # franja vacia. No es solo que la ayuda de la aplicacion lo diga -«con tres
    # personas 1 AM + 2 PM, nunca 3 AM + 0 PM»-: es que ademas congela el
    # carrusel, porque si todo el mundo va a la misma franja ya no queda a quien
    # rotar. Pasaba en cuanto Comunicaciones bajaba de tres personas a dos: el
    # reparto configurado «2 AM + 1 PM» se llevaba a las dos a la manana y alli
    # se quedaban indefinidamente, sin PM y sin rotar nunca mas. El reparto se
    # escribio pensando en el area completa; si el area encoge, se encoge con
    # ella. Donde hay turnos fijos esto no se aplica: alli el reparto convive
    # con gente que no se mueve y dejar una franja vacia puede ser lo correcto.
    if fijos_am == 0 and fijos_pm == 0 and rotativos >= 2:
        en_am = max(1, min(rotativos - 1, en_am))
    return max(0, min(rotativos, en_am))


def _ventana_am(rotativos: list[dict], indice_semana: int, cuantos: int) -> set[int]:
    """Ids de los rotativos que trabajan AM esa semana.

    La ventana **termina** en la posición que marcaba el reparto histórico de un
    solo AM (`indice_semana % n`). Así, al pasar de 1 AM a 2 AM, quien ya llevaba
    una semana en AM continúa y solo se le suma la persona anterior del carrusel:
    la rotación no se reinicia y nadie repite turno fuera de orden.
    """
    n = len(rotativos)
    if n == 0 or cuantos <= 0:
        return set()
    if cuantos >= n:
        return {int(e['id']) for e in rotativos}
    fin = indice_semana % n
    return {
        int(rotativos[(fin - offset) % n]['id'])
        for offset in range(cuantos)
    }


def turno_comunicaciones(empleado: dict, empleados: list[dict], fecha: date) -> str:
    """Carrusel semanal de COM guiado por la regla de cobertura del área.

    - Un fijo conserva AM/PM y cuenta antes de repartir rotativos.
    - El reparto normal (por ejemplo 1 AM + 2 PM, o 2 AM + 1 PM desde el 31 de
      agosto de 2026) se configura desde la aplicación y puede cambiar por fecha.
    - Los mínimos obligatorios del área mandan sobre ese reparto.
    - La responsabilidad rota semanalmente: nadie carga siempre el mismo turno.
    """
    if empleado.get('tipo_turno') == 'fijo':
        return str(empleado.get('turno_fijo'))
    if empleado.get('tipo_turno') == 'administrativo':
        return 'ADM-GS'

    activos = [e for e in empleados if e.get('area') == 'comunicaciones' and _vigente_en_semana(e, fecha)]
    rotativos = sorted(
        [e for e in activos if e.get('tipo_turno') == 'rotativo'],
        key=lambda e: (int(e.get('orden_rotacion') or 0), int(e['id'])),
    )
    if empleado not in rotativos:
        raise ValueError('La persona de Comunicaciones no pertenece al grupo rotativo activo.')
    fijos_am = sum(1 for e in activos if e.get('tipo_turno') == 'fijo' and e.get('turno_fijo') == 'AM')
    fijos_pm = sum(1 for e in activos if e.get('tipo_turno') == 'fijo' and e.get('turno_fijo') == 'PM')

    efectivos = _efectivos_de_la_semana(rotativos, fecha)
    en_am = _reparto_rotativos('comunicaciones', fecha, len(efectivos), fijos_am, fijos_pm)

    if len(efectivos) == 1:
        # Con un solo rotativo no hay carrusel: decide el reparto calculado.
        return 'AM' if en_am >= 1 else 'PM'

    _ancla, indice_semana = _lunes_grupo(efectivos, fecha)
    ids_am = _ventana_am(efectivos, indice_semana, en_am)
    return 'AM' if int(empleado['id']) in ids_am else 'PM'


def turno_atencion_ciudadano(empleado: dict, empleados: list[dict], fecha: date) -> str:
    """Distribuye AC semanalmente contando primero los turnos fijos.

    La cobertura protegida AM+PM se activa desde dos rotativos activos. Para
    grupos impares alterna cuál turno recibe la persona adicional y usa una
    ventana circular para que nadie cargue permanentemente el mismo turno.
    """
    if empleado.get('tipo_turno') == 'fijo':
        return str(empleado.get('turno_fijo'))
    if empleado.get('tipo_turno') == 'administrativo':
        return 'ADM-AC'

    activos = [e for e in empleados if e.get('area') == 'atencion_ciudadano' and _vigente_en_semana(e, fecha)]
    rotativos = sorted(
        [e for e in activos if e.get('tipo_turno') == 'rotativo'],
        key=lambda e: (int(e.get('orden_rotacion') or 0), int(e['id'])),
    )
    if empleado not in rotativos:
        raise ValueError('La persona de Atención al Ciudadano no pertenece al grupo rotativo activo.')

    if len(rotativos) == 1:
        # Una sola persona rotativa no reparte con nadie: alterna AM y PM
        # semana a semana desde su lunes de referencia. Parece que deje el area
        # sin PM las semanas que le tocan AM, pero es como funciona de verdad:
        # el horario real de Atencion al Ciudadano de septiembre de 2026 tiene
        # justamente esas semanas con todo el area en AM. Se intento "corregir"
        # atando su turno al reparto del area y el resultado dejaba de parecerse
        # a la realidad, asi que se conserva la alternancia.
        inicio = empleado.get('inicio_rotacion') or 'AM'
        ancla = empleado.get('fecha_ancla_rotacion') or '2026-08-31'
        return turno_rotativo(str(inicio), str(ancla), fecha)

    fijos_am = sum(1 for e in activos if e.get('tipo_turno') == 'fijo' and e.get('turno_fijo') == 'AM')
    fijos_pm = sum(1 for e in activos if e.get('tipo_turno') == 'fijo' and e.get('turno_fijo') == 'PM')
    efectivos = _efectivos_de_la_semana(rotativos, fecha)
    total_operativo = len(efectivos) + fijos_am + fijos_pm
    _ancla, indice_semana = _lunes_grupo(efectivos, fecha)

    objetivo_am = regla_cobertura('atencion_ciudadano', fecha).am_objetivo
    if objetivo_am is not None:
        # Reparto fijado desde la aplicación para esta fecha.
        rotativos_am = _reparto_rotativos(
            'atencion_ciudadano', fecha, len(efectivos), fijos_am, fijos_pm
        )
    else:
        # Reparto adaptativo histórico: mitad y mitad cuando es par y, en
        # dotación impar, alterna semanalmente qué turno recibe a la persona
        # adicional, preservando la continuidad entre meses.
        ideal_am = total_operativo // 2
        if total_operativo % 2 and indice_semana % 2:
            ideal_am += 1
        ideal_am = max(1, min(total_operativo - 1, ideal_am))
        rotativos_am = max(0, min(len(efectivos), ideal_am - fijos_am))
        # Los techos configurados acotan también el reparto adaptativo.
        tope_pm = maximo_cobertura_area('atencion_ciudadano', 'PM', fecha, total_operativo)
        if tope_pm is not None:
            rotativos_am = max(rotativos_am, len(efectivos) - max(0, int(tope_pm) - fijos_pm))
        tope_am = maximo_cobertura_area('atencion_ciudadano', 'AM', fecha, total_operativo)
        if tope_am is not None:
            rotativos_am = min(rotativos_am, max(0, int(tope_am) - fijos_am))
        # No sacrificar la cobertura PM protegida cuando los fijos no la cubren.
        if fijos_pm + (len(efectivos) - rotativos_am) < 1:
            rotativos_am = max(0, len(efectivos) - 1)
        # Y asegurar AM si no existe fijo AM.
        if fijos_am + rotativos_am < 1:
            rotativos_am = 1

    inicio_ventana = indice_semana % len(efectivos)
    ids_am = {
        int(efectivos[(inicio_ventana + offset) % len(efectivos)]['id'])
        for offset in range(rotativos_am)
    }
    return 'AM' if int(empleado['id']) in ids_am else 'PM'

def turno_base_empleado(empleado: dict, empleados: list[dict], fecha: date) -> str:
    if empleado['tipo_turno'] == 'administrativo':
        codigo = ADMIN_CODE_BY_AREA.get(empleado.get('area'))
        if not codigo:
            raise ValueError('El personal administrativo debe pertenecer a un área válida.')
        return codigo
    if empleado['tipo_turno'] == 'fijo':
        return str(empleado['turno_fijo'])
    if empleado['area'] == 'comunicaciones':
        return turno_comunicaciones(empleado, empleados, fecha)
    if empleado['area'] == 'atencion_ciudadano':
        return turno_atencion_ciudadano(empleado, empleados, fecha)
    return turno_rotativo(
        empleado['inicio_rotacion'],
        empleado['fecha_ancla_rotacion'],
        fecha,
    )

def validar_parejas(empleados: list[dict]) -> list[str]:
    errores = []
    por_id = {e['id']: e for e in empleados}
    revisadas = set()
    for e in empleados:
        if e['tipo_turno'] == 'rotativo':
            if not e.get('inicio_rotacion') or not e.get('fecha_ancla_rotacion'):
                errores.append(f"{e['nombre']}: configuración rotativa incompleta.")
        pid = e.get('pareja_id')
        if pid is None:
            continue
        if e['area'] == 'comunicaciones' or e['tipo_turno'] == 'administrativo':
            errores.append(f"{e['nombre']}: no puede tener pareja de PC.")
            continue
        p = por_id.get(pid)
        if not p:
            errores.append(f"{e['nombre']}: la pareja no existe o está inactiva.")
            continue
        clave = tuple(sorted((e['id'], p['id'])))
        if clave in revisadas:
            continue
        revisadas.add(clave)
        if p.get('pareja_id') != e['id']:
            errores.append(f"{e['nombre']} y {p['nombre']}: la pareja no es recíproca.")
        if e['area'] != p['area']:
            errores.append(f"{e['nombre']} y {p['nombre']}: deben ser de la misma área.")
        if e['tipo_turno'] != p['tipo_turno']:
            errores.append(f"{e['nombre']} y {p['nombre']}: deben ser ambos fijos o ambos rotativos.")
            continue
        if e['tipo_turno'] == 'fijo' and e.get('turno_fijo') == p.get('turno_fijo'):
            errores.append(f"{e['nombre']} y {p['nombre']}: los turnos fijos deben ser opuestos.")
        if e['tipo_turno'] == 'rotativo':
            if e.get('fecha_ancla_rotacion') != p.get('fecha_ancla_rotacion'):
                errores.append(f"{e['nombre']} y {p['nombre']}: deben compartir lunes de referencia.")
            if e.get('inicio_rotacion') == p.get('inicio_rotacion'):
                errores.append(f"{e['nombre']} y {p['nombre']}: deben iniciar en turnos opuestos.")
    return sorted(set(errores))
