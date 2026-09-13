# -*- coding: utf-8 -*-
"""Lo que un mes hereda del anterior.

Un mes no se genera en el vacío. Como los períodos van por semanas completas,
**dos meses consecutivos comparten la semana del cambio**: la primera semana de
octubre es también la última de septiembre, y septiembre ya se entregó al
equipo. Esa semana no se vuelve a decidir aquí, se copia literal y se bloquea.

Además hay tres cosas que cruzan la frontera del mes y que sin esto se pierden:

* **el turno con el que venía cada persona**, para que la rotación no se corte;
* **los últimos días trabajados**, para que la racha de jornadas seguidas y la
  regla de no encadenar una tarde con una mañana sigan contando;
* **en qué días de la semana descansó** las semanas anteriores, para que el
  reparto de descansos no repita siempre el mismo día.

Todo se toma del horario **oficial** del mes anterior, nunca de una propuesta
suelta: lo que hereda el mes siguiente tiene que ser lo que la oficina tiene en
la mano.
"""
from __future__ import annotations

from datetime import date, timedelta

from gestor.datos import horarios
from gestor.dominio import calendario, codigos


def periodo_anterior(mes: int, anio: int) -> tuple[int, int]:
    return (12, anio - 1) if int(mes) == 1 else (int(mes) - 1, int(anio))


def _oficial_anterior(mes: int, anio: int):
    anterior_mes, anterior_anio = periodo_anterior(mes, anio)
    return horarios.oficial(anterior_anio, anterior_mes)


def hay_mes_anterior_oficial(mes: int, anio: int) -> bool:
    return _oficial_anterior(mes, anio) is not None


def turnos_previos(mes: int, anio: int) -> dict[int, str]:
    """Con qué turno venía cada persona al empezar el período.

    Se mira el día anterior al **inicio del período**, no el último día del mes
    anterior: con semanas completas ese último día ya cae dentro del período que
    se está generando, y tomarlo como referencia hacía que la rotación se
    comparara consigo misma.
    """
    anterior = _oficial_anterior(mes, anio)
    if not anterior:
        return {}
    limite = calendario.rango(int(mes), int(anio))[0].isoformat()
    salida: dict[int, str] = {}
    for fila in anterior['horario']:
        dias = sorted((d for d in fila.get('dias', ())
                       if str(d.get('fecha') or '') < limite),
                      key=lambda d: str(d.get('fecha') or ''))
        if not dias:
            continue
        ultimo = dias[-1]
        turno = ultimo.get('turno')
        if turno in codigos.OPERATIVOS:
            salida[int(fila['empleado_id'])] = str(turno)
        elif turno in codigos.ADMINISTRATIVOS:
            propio = (ultimo.get('cobertura_operativa')
                      or ultimo.get('turno_operativo_origen'))
            if propio in codigos.OPERATIVOS:
                salida[int(fila['empleado_id'])] = str(propio)
    return salida


def dias_previos(mes: int, anio: int, cuantos: int = 8) -> dict[int, list[dict]]:
    """Los últimos días reales del mes anterior, para las reglas de fatiga.

    La misma secuencia sirve a dos reglas que cruzan el cambio de mes: no
    encadenar una tarde con la mañana siguiente, y el tope de jornadas seguidas.
    Se guardan unos cuantos días de más a propósito: un día administrativo en
    medio no corta una racha, y quedarse corto la partía justo donde había que
    medirla.
    """
    anterior = _oficial_anterior(mes, anio)
    if not anterior:
        return {}
    inicio = calendario.rango(int(mes), int(anio))[0]
    salida: dict[int, list[dict]] = {}
    for fila in anterior['horario']:
        dias = sorted((d for d in fila.get('dias', ())
                       if d.get('fecha')
                       and date.fromisoformat(str(d['fecha'])) < inicio),
                      key=lambda d: str(d.get('fecha') or ''))[-cuantos:]
        if not dias:
            continue
        salida[int(fila['empleado_id'])] = [{
            'fecha': str(d.get('fecha') or ''),
            'turno': str(d.get('turno') or ''),
            'origen': str(d.get('origen') or ''),
            'cobertura_operativa': d.get('cobertura_operativa'),
            'turno_operativo_origen': d.get('turno_operativo_origen'),
        } for d in dias]
    return salida


def dias_heredados(mes: int, anio: int) -> dict[int, dict[str, dict]]:
    """La semana compartida: días que el mes anterior ya publicó.

    Es lo que hace que el 28 de septiembre de la programación de octubre sea
    exactamente el 28 de septiembre que ya estaba publicado, y no una segunda
    versión de ese día.
    """
    anterior = _oficial_anterior(mes, anio)
    if not anterior:
        return {}
    from gestor.motor.construccion import dias_heredados_desde_horario

    inicio, fin = calendario.rango(int(mes), int(anio))
    fechas = set()
    fecha = inicio
    while fecha <= fin:
        fechas.add(fecha.isoformat())
        fecha += timedelta(days=1)
    return dias_heredados_desde_horario(anterior['horario'], fechas)


def _historial(mes: int, anio: int, filtro, max_semanas: int = 2
               ) -> dict[int, dict[str, set[int]]]:
    anterior = _oficial_anterior(mes, anio)
    if not anterior:
        return {}
    inicio = calendario.rango(int(mes), int(anio))[0]
    desde = inicio - timedelta(days=max_semanas * 7 + 7)

    salida: dict[int, dict[str, set[int]]] = {}
    for fila in anterior['horario']:
        semanas: dict[str, set[int]] = {}
        for dia in fila.get('dias', ()):
            if not dia.get('fecha') or not dia.get('lunes_semana'):
                continue
            cuando = date.fromisoformat(str(dia['fecha']))
            if not (desde <= cuando < inicio) or not filtro(dia):
                continue
            semanas.setdefault(str(dia['lunes_semana']), set()).add(
                int(dia['dia_semana_numero']))
        if semanas:
            # Si el período empieza a mitad de semana, esa semana parcial hace
            # falta entera para poder juzgar una racha de descansos iguales.
            conservar = max_semanas + (0 if inicio.weekday() == 0 else 1)
            elegidas = sorted(semanas)[-conservar:]
            salida[int(fila['empleado_id'])] = {k: semanas[k] for k in elegidas}
    return salida


def descansos_previos(mes: int, anio: int) -> dict[int, dict[str, set[int]]]:
    return _historial(mes, anio, lambda d: (
        d.get('turno') == codigos.DESCANSO
        and d.get('origen') not in {'descanso_extra_solicitado', 'descanso_administrativo'}))


def no_laborados_previos(mes: int, anio: int) -> dict[int, dict[str, set[int]]]:
    return _historial(mes, anio, lambda d: (
        d.get('turno') in {'VAC', 'INC', 'PER'}
        or (d.get('turno') == codigos.DESCANSO
            and d.get('origen') not in {'descanso_festivo', 'compensatorio_festivo',
                                        'descanso_extra_solicitado'})))


def descansos_especiales_previos(mes: int, anio: int) -> dict[int, dict[str, set[int]]]:
    return _historial(mes, anio, lambda d: (
        d.get('turno') == codigos.DESCANSO
        and d.get('origen') in {'descanso_domingo', 'descanso_especial'}))


def todo(mes: int, anio: int) -> dict:
    """Todo lo que hay que pasarle al motor para enlazar con el mes anterior."""
    return {
        'turnos_previos': turnos_previos(mes, anio),
        'dias_previos_fatiga': dias_previos(mes, anio),
        'dias_heredados': dias_heredados(mes, anio),
        'historial_descansos': descansos_previos(mes, anio),
        'historial_no_laborados': no_laborados_previos(mes, anio),
        'historial_descansos_especiales': descansos_especiales_previos(mes, anio),
    }


def falta_el_mes_anterior(mes: int, anio: int) -> str:
    """Explica, en castellano, qué hay que hacer antes de generar este mes.

    Cadena vacía cuando no falta nada. Este texto es lo único que verá quien se
    encuentre el botón sin poder usarlo, así que dice qué mes hay que preparar y
    por qué, en vez de un «no se puede».
    """
    inicio = calendario.rango(int(mes), int(anio))[0]
    if inicio <= calendario.PRIMER_DIA:
        return ''
    if hay_mes_anterior_oficial(mes, anio):
        return ''
    anterior_mes, anterior_anio = periodo_anterior(mes, anio)
    return (
        f'Todavía no se puede crear el horario de {calendario.nombre_del_periodo(mes, anio)}. '
        f'Ve a {calendario.nombre_del_periodo(anterior_mes, anterior_anio)}, genera su '
        'horario y marca como oficial una de las propuestas. Cada mes se calcula a partir '
        'del horario oficial del anterior, para que las rachas, los descansos y la rotación '
        'no se corten en la frontera entre meses.')
