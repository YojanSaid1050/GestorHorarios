"""Generación del Excel de la programación.

Son tres libros, cada uno para algo distinto:

* **Para trabajar** (``trabajo``) — el que se edita. Lleva dos hojas: «Semanas
  completas», con el horario tal y como se programa —de lunes a domingo, con
  los días que completan la primera y la última semana—, y «Solo el mes», que
  es la misma tabla recortada al mes natural. Los turnos de la segunda no son
  una copia: son una referencia a la primera. Se cambia un turno en «Semanas
  completas» y la hoja del mes lo recoge sola, con su color y sus horas. Todos
  los controles de la derecha son fórmulas vivas.

* **Una semana** (``semana``) — de lunes a domingo, para imprimir y repartir.

* **Completo** (``completo``) — el horario del período con los comentarios de
  cada día, más Parámetros, Resumen mensual e Instructivo. Es para consultar.

En los dos últimos las horas siguen calculándose, porque es lo que suele
preguntarse; los controles de domingos y de fatiga no aparecen, porque son de
quien programa el mes y no de quien lo lee.

Los colores salen de la configuración de la aplicación: los mismos que pintan
la tabla en pantalla. Y no se quedan pegados a la celda: una regla de formato
condicional hace que el color dependa de lo que la celda dice, así que al
cambiar un turno dentro del Excel el color cambia con él.
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from gestor.registro import obtener as obtener_registro
from gestor.rutas import EXPORTACIONES as OUTPUT_DIR
from gestor.servicios.apariencia import obtener_colores_excel

#: El respaldo si no se puede leer la regla configurada. Es el mismo número que
#: usa `servicios.reglas_operacion`, leído de allí para que no haya dos.
from gestor.servicios.reglas_operacion import POR_DEFECTO as MAX_DIAS_POR_DEFECTO

AREA = {
    'gestion_social': 'Gestión Social',
    'atencion_ciudadano': 'Atención al Ciudadano',
    'comunicaciones': 'Comunicaciones',
}

DIAS = {
    0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves',
    4: 'Viernes', 5: 'Sábado', 6: 'Domingo',
}

MESES = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]
MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

MARCA_AGUA = 'Creado por xYojanSaidx'

# Las dos hojas del libro de trabajo. La del mes es un espejo de la de semanas:
# los cambios se hacen en una y aparecen en la otra.
HOJA_SEMANAS = 'Semanas completas'
HOJA_MES = 'Solo el mes'

# Franjas horarias reales de la operación.
FRANJAS = [
    ['Código', 'Tipo', 'Aplicación', 'Horario', 'Descanso', 'Horas efectivas'],
    ['AM', 'Operativo AM', 'Lunes a sábado', '5:00 a. m. a 1:00 p. m.', '1 hora', 7],
    ['AM', 'Operativo AM', 'Domingo o festivo', '5:30 a. m. a 1:30 p. m.', '1 hora', 7],
    ['PM', 'Operativo PM', 'Lunes a sábado', '1:00 p. m. a 9:00 p. m.', '1 hora', 7],
    ['PM', 'Operativo PM', 'Domingo o festivo', '12:00 m. a 8:00 p. m.', '1 hora', 7],
    ['ADM-GS', 'Administrativo Guía Social', 'Lunes a domingo', '7:30 a. m. a 3:30 p. m.', '1 hora', 7],
    ['ADM-AC', 'Administrativo AC', 'Lunes a viernes', '7:30 a. m. a 4:00 p. m.', '1 hora', 7.5],
    ['ADM-AC', 'Administrativo AC', 'Sábado', '7:30 a. m. a 12:00 m.', 'Sin pausa', 4.5],
    ['CAP', 'Capacitación', 'Solicitud aprobada', 'Horario solicitado', 'Según capacitación', 'Horas reales'],
    ['D', 'Descanso', 'Día asignado', 'No aplica', 'No aplica', 0],
    ['VAC', 'Vacaciones', 'Novedad aprobada', 'No aplica', 'No aplica', 0],
    ['INC', 'Incapacidad', 'Novedad aprobada', 'No aplica', 'No aplica', 0],
    ['PER', 'Permiso', 'Novedad aprobada', 'No aplica', 'No aplica', 0],
]

# Un solo sitio para los códigos: ver `backend/codigos_turno.py`. Aquí van en
# lista porque el orden manda en las columnas del resumen.
CODIGOS_NO_LABORADOS = ['D', 'VAC', 'INC', 'PER', 'NV']
CODIGOS_TRABAJO = ['AM', 'PM', 'ADM-GS', 'ADM-AC', 'CAP']


def _borde():
    side = Side(style='thin', color='B7B7B7')
    return Border(left=side, right=side, top=side, bottom=side)


def _header(cell, color='5B2A86'):
    cell.fill = PatternFill('solid', fgColor=color)
    cell.font = Font(bold=True, color='FFFFFF')
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    cell.border = _borde()


def _cell(cell, center=True):
    cell.border = _borde()
    cell.alignment = Alignment(
        horizontal='center' if center else 'left',
        vertical='center',
        wrap_text=True,
    )


def _fecha_corta(iso: str) -> str:
    _a, m, d = str(iso).split('-')
    return f'{int(d)} {MESES_CORTOS[int(m) - 1]}'


def _dow(d: dict) -> int:
    """Día de la semana del registro, calculándolo si no viene dado."""
    valor = d.get('dia_semana_numero')
    if valor is not None:
        return int(valor)
    from datetime import date as _date
    return _date.fromisoformat(str(d['fecha'])).weekday()


def _agrupar_semanas(dias: list[dict]) -> list[list[dict]]:
    """Parte los días del período en sus semanas de lunes a domingo."""
    semanas: list[list[dict]] = []
    from datetime import date as _date
    from datetime import timedelta as _td
    for d in dias:
        lunes = d.get('lunes_semana')
        if not lunes:
            f = _date.fromisoformat(str(d['fecha']))
            lunes = (f - _td(days=f.weekday())).isoformat()
            d['lunes_semana'] = lunes
        if semanas and semanas[-1][0].get('lunes_semana') == lunes:
            semanas[-1].append(d)
        else:
            semanas.append([d])
    return semanas


def _rangos(columnas: list[int], fila: int) -> str:
    """Convierte columnas sueltas en la lista de rangos contiguos de una fila."""
    if not columnas:
        return ''
    partes = []
    inicio = anterior = columnas[0]
    for col in columnas[1:]:
        if col == anterior + 1:
            anterior = col
            continue
        partes.append((inicio, anterior))
        inicio = anterior = col
    partes.append((inicio, anterior))
    return ','.join(
        f'{get_column_letter(a)}{fila}' if a == b
        else f'{get_column_letter(a)}{fila}:{get_column_letter(b)}{fila}'
        for a, b in partes
    )


def _contar(rangos: str, codigos: list[str]) -> str:
    if not rangos:
        return '0'
    piezas = [f'COUNTIF({r},"{c}")' for r in rangos.split(',') for c in codigos]
    return '+'.join(piezas) if piezas else '0'


def _formula_horas(fila: int, todos: list[int], ac_semana: list[int], ac_sabado: list[int]) -> str:
    """Horas efectivas del rango, con las franjas reales de cada código."""
    r_todos = _rangos(todos, fila)
    partes = [f'7*({_contar(r_todos, ["AM", "PM", "ADM-GS", "CAP"])})']
    r_semana = _rangos(ac_semana, fila)
    if r_semana:
        partes.append(f'7.5*({_contar(r_semana, ["ADM-AC"])})')
    r_sabado = _rangos(ac_sabado, fila)
    if r_sabado:
        partes.append(f'4.5*({_contar(r_sabado, ["ADM-AC"])})')
    return '=' + '+'.join(partes)



def _hoja_horario(wb, titulo: str, resultado: dict, dias: list[dict],
                  colores: dict, opciones: dict) -> dict:
    """Construye una hoja de horario y devuelve lo que necesitan las demás.

    Una sola función para las tres formas que puede tomar la hoja:

    * la de trabajo, con todas las columnas de control en fórmula;
    * su espejo del mes, cuyos turnos son una referencia a la hoja de
      semanas: se cambia un turno allí y aquí cambia solo;
    * la informativa, que se queda con el horario y las dos cifras de horas.
    """
    con_comentarios = bool(opciones.get('con_comentarios'))
    controles = bool(opciones.get('controles', True))
    enlace = opciones.get('enlace')
    enlace_cols = opciones.get('enlace_cols') or {}
    color_header = colores['header']
    color_sabado = colores['saturday_header']
    color_domingo = colores['sunday_header']
    color_festivo = colores['holiday_header']
    color_viernes_adm = colores['admin_friday_header']
    color_celda_viernes_adm = colores['admin_friday_cell']
    color_otro_mes = colores.get('otro_mes_header', '41648C')
    color_otro_mes_celda = colores.get('otro_mes_cell', 'EDF3F9')

    ws = wb.create_sheet(titulo)
    horario = resultado['horario']
    semanas = _agrupar_semanas(dias)
    mes = int(resultado.get('mes') or 0)
    anio = int(resultado.get('anio') or 0)
    nombre_mes = MESES[mes - 1] if 1 <= mes <= 12 else ''

    nombres_por_id = {int(e['empleado_id']): e['nombre'] for e in horario}

    # ------------------------------------------------------------------
    # Geometría de la hoja
    # ------------------------------------------------------------------
    base_headers = ['Cargo', 'Nombre del colaborador', 'Área', 'Turno base', 'Descanso obligatorio', 'Pareja']
    start_col = len(base_headers) + 1
    end_day_col = start_col + len(dias) - 1
    stats_start = end_day_col + 1

    fechas_hoja = [d['fecha'] for d in dias]
    col_por_fecha = {d['fecha']: start_col + i for i, d in enumerate(dias)}
    cols_mes = [col_por_fecha[d['fecha']] for d in dias if d.get('mes_propio', True)]
    # El período son todas las columnas, incluidos los días que solo completan
    # la primera y la última semana. Esa es la cifra que queda pareja.
    cols_periodo = [col_por_fecha[d['fecha']] for d in dias]
    cols_periodo_ac_semana = [col_por_fecha[d['fecha']] for d in dias if _dow(d) <= 4]
    cols_periodo_ac_sabado = [col_por_fecha[d['fecha']] for d in dias if _dow(d) == 5]
    cols_mes_ac_semana = [
        col_por_fecha[d['fecha']] for d in dias
        if d.get('mes_propio', True) and _dow(d) <= 4
    ]
    cols_mes_ac_sabado = [
        col_por_fecha[d['fecha']] for d in dias
        if d.get('mes_propio', True) and _dow(d) == 5
    ]
    cols_domingos_mes = [
        col_por_fecha[d['fecha']] for d in dias
        if d.get('mes_propio', True) and d['es_domingo']
    ]
    hay_dias_de_otro_mes = any(not d.get('mes_propio', True) for d in dias)
    # Una hoja va «recortada» cuando no contiene el período entero: se pidió
    # solo el mes natural o una sola semana.
    hoja_recortada = bool(opciones.get('recorte'))
    recorte_texto = str(opciones.get('recorte') or '')

    # Dos cifras de horas, porque dicen cosas distintas y las dos importan:
    # las del período son las que quedan parejas para todo el personal —es lo
    # que el horario equilibra— y las del mes natural varían según dónde caiga
    # el descanso de cada quien, que es normal y no es un desequilibrio.
    reglas = resultado.get('reglas', {})
    # El tope de jornadas seguidas es configurable en la aplicación. Si el
    # horario lo trae anotado se usa ese —es el que regía cuando se generó—; si
    # no, se pregunta por el que rige ahora. Escribirlo a mano en la fórmula
    # haría que el Excel marcara «REVISAR» en rachas perfectamente legales.
    tope_racha = reglas.get('maximo_dias_consecutivos')
    if not tope_racha:
        # Esto apuntaba a `backend.operation_rules`, que es el paquete de la
        # versión anterior y aquí no existe: el import fallaba siempre, el
        # `except` se lo tragaba y el Excel salía impreso diciendo «máximo 7
        # jornadas seguidas» mientras la regla configurada era 10. Un fallo que
        # no daba error, no salía en ningún registro y viajaba en el papel que
        # se reparte.
        try:
            from gestor.servicios.reglas_operacion import maximo_dias
            tope_racha = maximo_dias(dias[0]['fecha']) if dias else None
        except Exception:                                          # noqa: BLE001
            obtener_registro().exception(
                'no se pudo leer el máximo de jornadas seguidas para el Excel')
            tope_racha = None
    tope_racha = int(tope_racha or MAX_DIAS_POR_DEFECTO)

    headers_stats = ['Horas del período (dato)' if hoja_recortada else 'Horas del período',
                     f'Horas {nombre_mes}' if nombre_mes else 'Horas del mes',
                     'Días trabajados',
                     'Domingos trabajados',
                     'Domingos descansados',
                     'Objetivo domingos',
                     'Control domingos']
    if not controles:
        # Los libros informativos se quedan con el horario y las horas: los
        # controles son de quien programa, no de quien lo lee.
        headers_stats = headers_stats[:2]
    headers_semana = ([f'Horas sem. {_fecha_corta(s[0]["fecha"])}–{_fecha_corta(s[-1]["fecha"])}' for s in semanas]
                      if controles else [])
    headers_final = (['Máx. días seguidos', f'Control fatiga (máx. {tope_racha})', 'Observaciones']
                     if controles else ['Observaciones'])
    todas_stats = headers_stats + headers_semana + headers_final
    end_col = stats_start + len(todas_stats) - 1

    domingos = reglas.get('domingos_mes', len(cols_domingos_mes))
    objetivo = reglas.get('domingos_trabajo_objetivo', domingos // 2)
    objetivo_max = reglas.get('domingos_trabajo_maximo_equilibrado', objetivo + (domingos % 2))

    # ------------------------------------------------------------------
    # Cabecera
    # ------------------------------------------------------------------
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end_col)
    if resultado.get('_export_week_start'):
        alcance = 'PROGRAMACIÓN SEMANAL DE TURNOS'
    elif hoja_recortada:
        alcance = 'PROGRAMACIÓN MENSUAL DE TURNOS'
    else:
        alcance = 'PROGRAMACIÓN DE TURNOS POR SEMANAS COMPLETAS'
    titulo_texto = f'{alcance} · {nombre_mes.upper()} {anio}' if nombre_mes else alcance
    if resultado.get('_es_borrador_export'):
        titulo_texto = f'BORRADOR — NO PUBLICADO · {titulo_texto}'
    title = ws.cell(1, 1, titulo_texto)
    title.font = Font(size=16, bold=True, color='FFFFFF')
    title.fill = PatternFill('solid', fgColor=color_header)
    title.alignment = Alignment(horizontal='center', vertical='center')

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=end_col)
    if hay_dias_de_otro_mes:
        subtitulo = (
            f'Vista semanal completa del {_fecha_corta(dias[0]["fecha"])} al {_fecha_corta(dias[-1]["fecha"])}. '
            f'Los días fuera de {nombre_mes} completan la primera y la última semana: sirven para comprobar '
            f'descansos, rachas y continuidad, y no suman a «Horas {nombre_mes}».'
        )
    else:
        subtitulo = (
            f'Del {_fecha_corta(dias[0]["fecha"])} al {_fecha_corta(dias[-1]["fecha"])}. '
            'AM y PM son los turnos operativos; D es descanso; ADM-GS y ADM-AC, jornadas administrativas.'
        )
    ws.cell(2, 1, subtitulo)
    ws.cell(2, 1).alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.cell(2, 1).font = Font(italic=True)

    # Fila 3: bandas de semana
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=len(base_headers))
    _header(ws.cell(3, 1, f'Período oficial: {nombre_mes} de {anio}' if nombre_mes else 'Período oficial'), color_header)
    for indice, semana in enumerate(semanas, 1):
        primera = col_por_fecha[semana[0]['fecha']]
        ultima = col_por_fecha[semana[-1]['fecha']]
        etiqueta = f'Semana {indice} · {_fecha_corta(semana[0]["fecha"])}–{_fecha_corta(semana[-1]["fecha"])}'
        if primera != ultima:
            ws.merge_cells(start_row=3, start_column=primera, end_row=3, end_column=ultima)
        _header(ws.cell(3, primera, etiqueta), color_header)
    ws.merge_cells(start_row=3, start_column=stats_start, end_row=3, end_column=end_col)
    _header(ws.cell(3, stats_start, 'Controles y horas · fórmulas que se recalculan solas'), color_header)

    # Fila 4: encabezados. Fila 5: día de la semana.
    for col, text in enumerate(base_headers, 1):
        _header(ws.cell(4, col, text), color_header)
        _header(ws.cell(5, col, ''), color_header)

    for col, day in enumerate(dias, start_col):
        otro_mes = not day.get('mes_propio', True)
        color = (
            color_otro_mes if otro_mes else
            color_festivo if day['es_festivo'] else
            color_viernes_adm if day.get('es_ultimo_viernes_administrativo') else
            color_domingo if day['es_domingo'] else
            color_sabado if day.get('es_sabado') else
            color_header
        )
        etiqueta = f"{day['dia']} {MESES_CORTOS[int(day.get('mes') or mes) - 1]}" if otro_mes else day['dia']
        day_cell = ws.cell(4, col, etiqueta)
        _header(day_cell, color)
        _header(ws.cell(5, col, day['dia_semana'][:3]), color)
        notas = []
        if otro_mes:
            notas.append('Día de otro mes: completa la semana y no suma a las horas del mes.')
        if day.get('nombre_festivo'):
            notas.append(f"Festivo: {day['nombre_festivo']}")
        elif day.get('es_ultimo_viernes_administrativo'):
            notas.append('Último viernes administrativo del mes')
        if notas and con_comentarios:
            # «Sin comentarios» es sin ninguno, también en la fila de fechas: el
            # día de otro mes ya se distingue por su color y su marco.
            day_cell.comment = Comment('\n'.join(notas), 'Sistema')

    for col, text in enumerate(todas_stats, stats_start):
        _header(ws.cell(4, col, text), color_header)
        _header(ws.cell(5, col, ''), color_header)

    # ------------------------------------------------------------------
    # Filas de personal
    # ------------------------------------------------------------------
    stats_by = {s['empleado_id']: s for s in resultado.get('estadisticas', [])}
    primera_fila = 6
    ultima_fila = primera_fila + len(horario) - 1

    notas = [
        f'Regla de domingos: {nombre_mes} de {anio} tiene {domingos} domingos; el personal operativo trabaja '
        f'{objetivo} y descansa {domingos - objetivo}. El horario administrativo conserva domingos y festivos no laborados.',
        'Las horas son informativas y reflejan el tiempo programado. Una semana ordinaria suele sumar 42 h; '
        'un festivo, un compensatorio o una ausencia aprobada pueden reducir el total sin que eso sea un conflicto.',
        'Si editas una celda de turno dentro de este Excel, las horas, los domingos y el máximo de días seguidos '
        'se recalculan solos. El cambio no vuelve a la aplicación: para que quede guardado hazlo desde la app.',
        f'Control de fatiga: el tope configurado es de {tope_racha} jornadas seguidas. La columna marca REVISAR '
        f'a partir de la {tope_racha + 1}.',
    ]
    if hoja_recortada:
        notas.append(
            f'«Horas del período (dato)» es la cifra del período completo, de semanas enteras: la que el '
            f'horario equilibra y en la que todo el personal queda parejo. Aquí va como dato y no como '
            f'fórmula porque esta hoja solo trae {recorte_texto}, y los días que faltan no están para poder '
            f'sumarlos. Si la necesitas calculada, exporta el libro del período.'
        )
    if hay_dias_de_otro_mes:
        fuera = [d for d in dias if not d.get('mes_propio', True)]
        etiquetas = ', '.join(_fecha_corta(d['fecha']) for d in fuera)
        notas.append(
            f'Las columnas {etiquetas} completan la primera y la última semana. Sirven para verificar horas '
            f'semanales, descansos, fatiga y continuidad; no se incluyen en «Horas {nombre_mes}».'
        )

    fila_nota = ultima_fila + 2
    fila_franjas = fila_nota + len(notas) + 1
    fila_marca = fila_franjas + len(FRANJAS) + 2
    # Filas auxiliares: cuentan días seguidos de trabajo. Van al final y se
    # ocultan porque son el andamiaje de la fórmula «Máx. días seguidos», no
    # información para leer.
    fila_aux_inicio = fila_marca + 3

    for indice, employee in enumerate(horario):
        row = primera_fila + indice
        fila_aux = fila_aux_inicio + indice
        stat = stats_by.get(employee['empleado_id'], {})

        if employee['tipo_turno'] == 'administrativo':
            descanso = 'Domingos y festivos'
        elif employee.get('descanso_fijo') is not None:
            rango = str(objetivo) if objetivo == objetivo_max else f'{objetivo}-{objetivo_max}'
            descanso = f"{DIAS[employee['descanso_fijo']]} fijo + domingos {rango}/{domingos}"
        else:
            rango = str(objetivo) if objetivo == objetivo_max else f'{objetivo}-{objetivo_max}'
            descanso = f'Variable · domingos {rango}/{domingos}'

        pareja = nombres_por_id.get(int(employee.get('pareja_id') or 0), '—')

        values = [
            employee.get('cargo', 'GUÍA SOCIAL'),
            employee['nombre'],
            AREA.get(employee['area'], employee['area']),
            employee['turno_base'],
            descanso,
            pareja,
        ]
        for col, value in enumerate(values, 1):
            _cell(ws.cell(row, col, value), center=col != 2)

        # Los días de esta hoja, no los de todo el período: la hoja del mes
        # tiene menos columnas y antes se le escribían de más, corridas.
        dias_empleado = {d['fecha']: d for d in employee['dias']}
        for col, fecha_dia in enumerate(fechas_hoja, start_col):
            day = dias_empleado.get(fecha_dia)
            if day is None:
                continue
            otro_mes = not day.get('mes_propio', True)
            if enlace and day['fecha'] in enlace_cols:
                # Espejo: el turno no se copia, se toma de la hoja de semanas.
                # Así un cambio hecho allí aparece aquí sin tocar nada.
                origen = f"'{enlace}'!{get_column_letter(enlace_cols[day['fecha']])}{row}"
                cell = ws.cell(row, col, f'={origen}')
            else:
                cell = ws.cell(row, col, '' if day.get('turno') == 'NV' else day['turno'])
            _cell(cell)
            if otro_mes and day['turno'] in {'', 'NV'}:
                color_celda = color_otro_mes_celda
            elif day.get('es_ultimo_viernes_administrativo') and day['turno'] in {'ADM-GS', 'ADM-AC'}:
                color_celda = color_celda_viernes_adm
            else:
                color_celda = colores.get(day['turno'], 'FFFFFF')
            cell.fill = PatternFill('solid', fgColor=color_celda)
            cell.font = Font(bold=True)
            if otro_mes:
                # Marco del color de «días de otro mes» sin perder el color del turno.
                lado = Side(style='medium', color=color_otro_mes)
                cell.border = Border(left=lado, right=lado, top=lado, bottom=lado)

            detalles = [
                'Día publicado con el mes anterior · no se modifica aquí' if day.get('heredado') else None,
                'Completa la semana; pertenece a otro mes' if otro_mes and not day.get('heredado') else None,
                day.get('observacion'),
                f"Festivo: {day['nombre_festivo']}" if day.get('nombre_festivo') else None,
                f"Capacitación: {day.get('capacitacion_horas', 0):.1f} h" if day.get('capacitacion_horas') else None,
            ]
            detalles = [x for x in detalles if x]
            if detalles and con_comentarios:
                cell.comment = Comment('\n'.join(detalles), 'Sistema')

        # --- Controles con fórmula ------------------------------------
        col = stats_start
        rango_mes = _rangos(cols_mes, row)
        rango_dom = _rangos(cols_domingos_mes, row)

        if enlace and opciones.get('enlace_horas_periodo'):
            # También el total del período viene de la hoja de semanas: si allí
            # cambia un turno, aquí cambia la cifra. Es la única forma de que la
            # columna diga la verdad en una hoja que no tiene esos días.
            letra = get_column_letter(int(opciones['enlace_horas_periodo']))
            _cell(ws.cell(row, col, f"='{enlace}'!{letra}{row}"))
        elif hoja_recortada:
            # La hoja no trae todos los días del período —se pidió solo el mes o
            # una semana—, así que aquí no hay con qué calcularlo. Antes se
            # ponía la fórmula igual y salía la cifra del recorte: dos columnas
            # distintas diciendo lo mismo, y la de la izquierda mintiendo. Ahora
            # se escribe el dato real, y se dice de dónde sale.
            horas_periodo = stat.get('horas_periodo')
            celda_hp = ws.cell(row, col, horas_periodo if horas_periodo is not None else '—')
            _cell(celda_hp)
            if con_comentarios:
                celda_hp.comment = Comment(
                    'Horas del período completo, de semanas enteras.\n'
                    'Esta hoja solo trae ' + recorte_texto + ', por eso no es una fórmula: '
                    'los días que faltan no están en la hoja para poder sumarlos.\n'
                    'Para verla calculada, exporta el libro del período.',
                    'Sistema')
        else:
            _cell(ws.cell(row, col, _formula_horas(
                row, cols_periodo, cols_periodo_ac_semana, cols_periodo_ac_sabado)))
        col += 1
        _cell(ws.cell(row, col, _formula_horas(row, cols_mes, cols_mes_ac_semana, cols_mes_ac_sabado)))
        col += 1
        if controles:
            _cell(ws.cell(row, col, f'={_contar(rango_mes, CODIGOS_TRABAJO)}'))
            col += 1
            _cell(ws.cell(row, col, f'={_contar(rango_dom, CODIGOS_TRABAJO)}'))
            col += 1
            _cell(ws.cell(row, col, f'={_contar(rango_dom, CODIGOS_NO_LABORADOS)}'))
            col += 1
            exento = (
                employee['tipo_turno'] == 'administrativo'
                or employee.get('descanso_fijo') is not None
                or employee.get('exento_especiales')
            )
            objetivo_txt = 'Exento' if exento else (
                f'{objetivo} trabajo / {domingos - objetivo} D' if objetivo == objetivo_max
                else f'{objetivo}-{objetivo_max} de {domingos}'
            )
            _cell(ws.cell(row, col, objetivo_txt))
            col += 1
            letra_dom = get_column_letter(stats_start + 3)
            if exento:
                _cell(ws.cell(row, col, 'EXENTO'))
            else:
                _cell(ws.cell(
                    row, col,
                    f'=IF(AND({letra_dom}{row}>={objetivo},{letra_dom}{row}<={objetivo_max}),"CUMPLE","REVISAR")',
                ))
            col += 1

        if controles:
            for semana in semanas:
                cols_s = [col_por_fecha[d['fecha']] for d in semana]
                cols_s_ac = [col_por_fecha[d['fecha']] for d in semana if _dow(d) <= 4]
                cols_s_sab = [col_por_fecha[d['fecha']] for d in semana if _dow(d) == 5]
                _cell(ws.cell(row, col, _formula_horas(row, cols_s, cols_s_ac, cols_s_sab)))
                col += 1

        if controles:
            primera_col_letra = get_column_letter(start_col)
            ultima_col_letra = get_column_letter(end_day_col)
            _cell(ws.cell(row, col, f'=MAX({primera_col_letra}{fila_aux}:{ultima_col_letra}{fila_aux})'))
            letra_max = get_column_letter(col)
            col += 1
            _cell(ws.cell(
                row, col,
                f'=IF({letra_max}{row}<={tope_racha},"CUMPLE","REVISAR")',
            ))
            col += 1
        _cell(ws.cell(row, col, ''), center=False)

        # Fila auxiliar: racha de días trabajados acumulada, día a día.
        for posicion, day_col in enumerate(range(start_col, end_day_col + 1) if controles else []):
            letra = get_column_letter(day_col)
            condiciones = ','.join(f'{letra}{row}="{c}"' for c in [''] + CODIGOS_NO_LABORADOS)
            if posicion == 0:
                ws.cell(fila_aux, day_col, f'=IF(OR({condiciones}),0,1)')
            else:
                anterior = get_column_letter(day_col - 1)
                ws.cell(fila_aux, day_col, f'=IF(OR({condiciones}),0,{anterior}{fila_aux}+1)')

    for fila in range(fila_aux_inicio, fila_aux_inicio + len(horario)):
        ws.row_dimensions[fila].hidden = True

    # ------------------------------------------------------------------
    # Notas y franjas horarias
    # ------------------------------------------------------------------
    for offset, texto in enumerate(notas):
        fila = fila_nota + offset
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=end_col)
        celda = ws.cell(fila, 1, texto)
        celda.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        celda.font = Font(size=9, italic=True, color='555555')

    rr = fila_franjas
    ws.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=6)
    ws.cell(rr, 1, 'HORARIOS APLICABLES')
    _header(ws.cell(rr, 1), color_header)
    for row_index, row_data in enumerate(FRANJAS, rr + 1):
        for col_index, value in enumerate(row_data, 1):
            cell = ws.cell(row_index, col_index, value)
            _header(cell, color_header) if row_index == rr + 1 else _cell(cell, center=col_index != 2)

    ws.merge_cells(start_row=fila_marca, start_column=1, end_row=fila_marca, end_column=end_col)
    marca = ws.cell(fila_marca, 1, MARCA_AGUA)
    marca.alignment = Alignment(horizontal='center', vertical='center')
    marca.font = Font(size=9, bold=True, color='999999')

    ws.freeze_panes = f'{get_column_letter(start_col)}6'
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.center.text = MARCA_AGUA
    ws.oddFooter.center.size = 8

    widths = {1: 16, 2: 31, 3: 23, 4: 13, 5: 28, 6: 28}
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width
    for col in range(start_col, end_day_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = 8.5 if hay_dias_de_otro_mes else 6.5
    for col in range(stats_start, end_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = 17

    # Los colores siguen al valor de la celda: si alguien cambia un turno dentro
    # del Excel —o si la hoja del mes lo recibe de la de semanas— el color
    # cambia con él. Antes el relleno se quedaba con el del turno anterior.
    _colorear_por_valor(ws, colores, start_col, end_day_col, primera_fila, ultima_fila,
                        {col_por_fecha[d['fecha']] for d in dias
                         if not d.get('mes_propio', True)
                         or (d.get('es_ultimo_viernes_administrativo')
                             and d.get('turno') in {'ADM-GS', 'ADM-AC'})})

    return {
        'ws': ws,
        'col_por_fecha': col_por_fecha,
        'col_horas_periodo': stats_start,
        'nombre_mes': nombre_mes,
        'mes': mes,
        'anio': anio,
        'domingos': domingos,
        'objetivo': objetivo,
        'tope_racha': tope_racha,
    }


def _hojas_de_apoyo(wb, resultado: dict, colores: dict, ctx: dict) -> None:
    """Parámetros, Resumen mensual e Instructivo: material de consulta."""
    horario = resultado['horario']
    stats_by = {s['empleado_id']: s for s in resultado.get('estadisticas', [])}
    color_header = colores['header']
    nombre_mes = ctx['nombre_mes']
    anio = ctx['anio']

    p = wb.create_sheet('Parámetros')
    p.merge_cells('A1:F1')
    p['A1'] = 'PARÁMETROS'
    _header(p['A1'], color_header)
    for row_index, row_data in enumerate(FRANJAS, 3):
        for col_index, value in enumerate(row_data, 1):
            cell = p.cell(row_index, col_index, value)
            _header(cell, color_header) if row_index == 3 else _cell(cell, center=col_index != 2)
    for col in range(1, 7):
        p.column_dimensions[get_column_letter(col)].width = [14, 26, 25, 28, 18, 16][col - 1]

    color_row = 3 + len(FRANJAS) + 2
    p.merge_cells(start_row=color_row, start_column=1, end_row=color_row, end_column=3)
    p.cell(color_row, 1, 'COLORES DEL EXCEL')
    _header(p.cell(color_row, 1), color_header)
    color_labels = [
        ('Encabezado', 'header'), ('Sábado', 'saturday_header'), ('Domingo', 'sunday_header'),
        ('Festivo', 'holiday_header'), ('Encabezado último viernes ADM', 'admin_friday_header'),
        ('Celdas último viernes ADM', 'admin_friday_cell'),
        ('Encabezado de días de otro mes', 'otro_mes_header'),
        ('Celdas de días de otro mes', 'otro_mes_cell'),
        ('AM', 'AM'), ('PM', 'PM'), ('Descanso D', 'D'), ('ADM-GS', 'ADM-GS'),
        ('ADM-AC', 'ADM-AC'), ('Vacaciones', 'VAC'), ('Incapacidad', 'INC'),
        ('Permiso', 'PER'), ('Capacitación', 'CAP'),
    ]
    for offset, (label, key) in enumerate(color_labels, 1):
        row = color_row + offset
        p.cell(row, 1, label)
        _cell(p.cell(row, 1), center=False)
        p.cell(row, 2, f"#{colores.get(key, 'FFFFFF')}")
        _cell(p.cell(row, 2))
        p.cell(row, 3, 'Vista')
        _cell(p.cell(row, 3))
        p.cell(row, 3).fill = PatternFill('solid', fgColor=colores.get(key, 'FFFFFF'))
    p.oddFooter.center.text = MARCA_AGUA

    rs = wb.create_sheet('Resumen mensual')
    rs.merge_cells('A1:K1')
    rs['A1'] = f'RESUMEN DE {nombre_mes.upper()} {anio}' if nombre_mes else 'RESUMEN MENSUAL'
    _header(rs['A1'], color_header)
    rs.merge_cells('A2:K2')
    rs['A2'] = (
        'HORAS DEL PERÍODO: semanas completas, del primer lunes al último domingo. Es la cifra que el horario '
        'equilibra y ahí todo el personal queda parejo. · HORAS DEL MES: solo los días del mes natural; unos '
        'tendrán más y otros menos según dónde caiga su descanso, y eso es normal, porque lo que se compensa '
        'cae en el mes vecino. Por eso la programación se hace por semanas completas y no por meses. '
        'Una semana ordinaria suele sumar 42 h; ADM-GS aporta 7 h de lunes a domingo y ADM-AC 7,5 h de lunes a '
        'viernes y 4,5 h el sábado.'
    )
    rs['A2'].alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    rs['A2'].font = Font(italic=True, color='555555')

    summary_headers = [
        'Colaborador', 'Área', 'Horas del mes', 'Horas del período', 'Días trabajados',
        'Domingos', 'Festivos', 'Especiales trabajados', 'Objetivo especiales',
        'Control especiales', 'Control descanso',
    ]
    for col, value in enumerate(summary_headers, 1):
        _header(rs.cell(3, col, value), color_header)
    for row, employee in enumerate(horario, 4):
        stat = stats_by.get(employee['empleado_id'], {})
        values = [
            employee['nombre'],
            AREA.get(employee['area'], employee['area']),
            stat.get('horas_mes', 0),
            stat.get('horas_periodo', stat.get('horas_mes', 0)),
            stat.get('dias_trabajados', 0),
            stat.get('domingos_trabajados', 0),
            stat.get('festivos_trabajados', 0),
            stat.get('especiales_trabajados', 0),
            stat.get('objetivo_especiales', ''),
            stat.get('control_especiales', ''),
            stat.get('control_descanso', ''),
        ]
        for col, value in enumerate(values, 1):
            _cell(rs.cell(row, col, value), center=col != 1)
    for col in range(1, 12):
        rs.column_dimensions[get_column_letter(col)].width = 21
    rs.oddFooter.center.text = MARCA_AGUA

    ins = wb.create_sheet('Instructivo')
    ins.merge_cells('A1:B1')
    ins['A1'] = 'INSTRUCTIVO'
    _header(ins['A1'], color_header)
    instrucciones = [
        [1, 'El horario se lee por semanas completas de lunes a domingo. La fila de bandas indica dónde empieza y termina cada semana.'],
        [2, 'AM y PM son los turnos operativos; D, el descanso; ADM-GS y ADM-AC, las jornadas administrativas; VAC, INC, PER y CAP, las novedades aprobadas.'],
        [3, 'Los días con marco y color propio pertenecen al mes anterior o al siguiente: completan la semana y no suman a las horas del mes.'],
        [4, 'Los días heredados del mes anterior ya están publicados. Si necesitas cambiarlos, hazlo en ese mes y vuelve a generar este.'],
        [5, 'Este libro es para consultar: trae el horario, los comentarios de cada día y las dos cifras de horas, que sí se recalculan. Los controles de domingos y de fatiga están en el libro «Para trabajar».'],
        [6, 'El libro «Para trabajar» lleva dos hojas: «Semanas completas», donde se hacen los cambios, y «Solo el mes», que los recoge sola.'],
        [7, 'La hoja Parámetros recoge las franjas horarias reales y los colores configurados en la aplicación.'],
        [8, 'Un cambio hecho dentro del Excel no vuelve a la aplicación. Para que quede guardado, hazlo desde la app y exporta de nuevo.'],
    ]
    _header(ins.cell(3, 1, 'Paso'), color_header)
    _header(ins.cell(3, 2, 'Instrucción'), color_header)
    for row_index, row_data in enumerate(instrucciones, 4):
        for col_index, value in enumerate(row_data, 1):
            cell = ins.cell(row_index, col_index, value)
            _cell(cell, center=col_index == 1)
    ins.column_dimensions['A'].width = 10
    ins.column_dimensions['B'].width = 120
    ins.oddFooter.center.text = MARCA_AGUA



def _colorear_por_valor(ws, colores: dict, primera_col: int, ultima_col: int,
                        primera_fila: int, ultima_fila: int, columnas_propias: set) -> None:
    """Hace que el color de cada celda dependa de lo que dice, no de lo que decía.

    El relleno se pinta al exportar, así que al cambiar un turno dentro del
    Excel la celda conservaba el color del turno anterior: en la hoja espejo del
    mes, que recibe sus turnos de la de semanas, eso significaba que ninguna
    celda tendría nunca el color correcto. Con formato condicional el color lo
    decide el propio valor, y son los colores configurados en la aplicación.

    Las columnas con color propio —los días de otro mes y el último viernes
    administrativo— se dejan fuera: ahí el color dice otra cosa.
    """
    if ultima_fila < primera_fila:
        return
    codigos = ['AM', 'PM', 'D', 'ADM-GS', 'ADM-AC', 'VAC', 'INC', 'PER', 'CAP']
    tramos = []
    inicio = None
    for col in range(primera_col, ultima_col + 2):
        propia = col in columnas_propias or col > ultima_col
        if propia:
            if inicio is not None:
                tramos.append((inicio, col - 1))
                inicio = None
        elif inicio is None:
            inicio = col
    for desde, hasta in tramos:
        rango = (f'{get_column_letter(desde)}{primera_fila}:'
                 f'{get_column_letter(hasta)}{ultima_fila}')
        for codigo in codigos:
            color = colores.get(codigo)
            if not color:
                continue
            ws.conditional_formatting.add(rango, CellIsRule(
                operator='equal', formula=[f'"{codigo}"'],
                fill=PatternFill('solid', start_color=color, end_color=color),
                font=Font(bold=True)))


# Las tres formas del libro. La primera es con la que se trabaja; las otras dos
# se reparten y se consultan.
LIBROS = {
    'trabajo': '_Horario',
    'semana': '_Semana',
    'completo': '_Completa',
}


def _libro_pedido(resultado: dict, modo: str | None) -> str:
    """Qué libro se está pidiendo, admitiendo también los nombres antiguos."""
    pedido = str(resultado.get('_export_libro') or modo or resultado.get('_export_version') or '')
    if pedido in LIBROS:
        return pedido
    if resultado.get('_export_week_start'):
        return 'semana'
    if pedido == 'solo_horario':
        return 'trabajo'
    return 'completo'


def crear_excel(resultado: dict, modo: str | None = None) -> Path:
    """Arma el libro pedido.

    Son tres, no cinco. El de trabajo lleva dos hojas: el horario por semanas
    completas —donde se hacen los cambios— y su espejo del mes, que las recibe.
    Los otros dos se reparten: una semana suelta y el libro completo con los
    comentarios y las hojas de consulta. En esos dos, las horas siguen siendo
    fórmula; el resto de controles no, porque no son para quien los lee.
    """
    if not resultado.get('horario'):
        raise ValueError('El horario está vacío.')

    colores = obtener_colores_excel()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    libro = _libro_pedido(resultado, modo)

    wb = Workbook()
    wb.remove(wb.active)

    dias = resultado['horario'][0]['dias']
    dias_del_mes = [d for d in dias if d.get('mes_propio', True)]

    if libro == 'trabajo':
        ctx = _hoja_horario(wb, HOJA_SEMANAS, resultado, dias, colores, {
            'con_comentarios': False, 'controles': True,
        })
        if dias_del_mes and len(dias_del_mes) != len(dias):
            _hoja_horario(wb, HOJA_MES, resultado, dias_del_mes, colores, {
                'con_comentarios': False, 'controles': True,
                'recorte': 'los días del mes',
                'enlace': HOJA_SEMANAS, 'enlace_cols': ctx['col_por_fecha'],
                'enlace_horas_periodo': ctx['col_horas_periodo'],
            })
        sufijo = LIBROS['trabajo']
    elif libro == 'semana':
        inicio = resultado.get('_export_week_start')
        ctx = _hoja_horario(wb, 'Horario de la semana', resultado, dias, colores, {
            'con_comentarios': False, 'controles': False, 'recorte': 'una semana',
        })
        sufijo = f"{LIBROS['semana']}_{inicio}" if inicio else LIBROS['semana']
    else:
        ctx = _hoja_horario(wb, 'Horario con comentarios', resultado, dias, colores, {
            'con_comentarios': True, 'controles': False,
        })
        _hojas_de_apoyo(wb, resultado, colores, ctx)
        sufijo = LIBROS['completo']

    ruta = OUTPUT_DIR / f"Programacion_{resultado['anio']}_{resultado['mes']:02d}{sufijo}.xlsx"
    wb.save(ruta)
    return ruta
