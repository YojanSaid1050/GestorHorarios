# -*- coding: utf-8 -*-
"""Cada norma, comprobada a mano sobre cada mes, con los números delante.

El auditor de `pruebas/auditor.py` contesta sí o no. Esto contesta **qué miró**:
cuántos casos revisó de cada norma, qué cifras salieron y en qué días. Un «0
incumplimientos» sin eso detrás no permite distinguir «la regla se cumple» de
«la regla no se llegó a comprobar», que es exactamente el error que deja pasar
un fallo durante meses.

Cada norma se vuelve a implementar **desde su enunciado**, no llamando a la
validación del motor. Si el motor y su propia validación estuvieran equivocados
de la misma manera —que es lo que pasa cuando alguien «arregla» la validación
para que acepte lo que el motor produce— las pruebas normales seguirían en verde
y esto no.

Las excepciones legítimas están escritas y se cuentan aparte, nunca se callan:

* el **último viernes administrativo**, en el que el área entera hace jornada ADM
  y nadie está en AM ni en PM, a propósito;
* los días **heredados** de un mes ya publicado, que este mes no puede cambiar;
* la **primera semana** del período, que se comparte con el mes anterior;
* la **válvula**: un mínimo nunca puede exigir a toda el área a la vez, porque
  entonces nadie podría descansar.
"""
from __future__ import annotations

import collections
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from qa.encadenado import reglas_vigentes_en  # noqa: E402
from qa.servidor import Servidor, entrar_como_admin  # noqa: E402

MESES = [(2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2), (2027, 3)]

TRABAJO = {'AM', 'PM', 'ADM-GS', 'ADM-AC', 'CAP'}
CONSERVAN_SU_FRANJA = {'ADM-GS', 'CAP'}
NO_TRABAJO = {'D', 'VAC', 'INC', 'PER'}
FUERA = 'NV'
AREAS = ('gestion_social', 'atencion_ciudadano', 'comunicaciones')
NOMBRES = {'gestion_social': 'Gestión Social',
           'atencion_ciudadano': 'Atención al Ciudadano',
           'comunicaciones': 'Comunicaciones'}


class Norma:
    """Lo comprobado de una norma en un mes: cuántos casos y cuántos fallos."""

    def __init__(self, clave: str, enunciado: str):
        self.clave = clave
        self.enunciado = enunciado
        self.revisados = 0
        self.fallos: list[str] = []
        self.exentos: list[str] = []
        self.notas: list[str] = []

    def revisar(self, cumple: bool, detalle: str = '') -> None:
        self.revisados += 1
        if not cumple:
            self.fallos.append(detalle)

    def eximir(self, motivo: str) -> None:
        self.exentos.append(motivo)

    def anotar(self, dato: str) -> None:
        self.notas.append(dato)

    @property
    def bien(self) -> bool:
        return not self.fallos

    def linea(self) -> str:
        marca = 'ok  ' if self.bien else 'FALLA'
        extra = []
        if self.exentos:
            extra.append(f'{len(self.exentos)} exento(s)')
        if self.fallos:
            extra.append(f'{len(self.fallos)} incumple(n)')
        cola = f'   [{" · ".join(extra)}]' if extra else ''
        return f'    [{marca}] {self.clave:34s} {self.revisados:5d} revisados{cola}'


# --------------------------------------------------------------- ayudas

def _por_fecha(fila) -> dict:
    return {str(d['fecha']): d for d in fila.get('dias') or []}


def _heredado(dia) -> bool:
    return bool(dia.get('heredado') or str(dia.get('origen') or '').startswith('base_'))


def _es_festivo(horario, fecha: str) -> bool:
    """¿Ese día lo marca el calendario como festivo?

    Hace falta porque la oficina cierra por festivo antes que por cualquier otra
    cosa, y dos de los seis meses lo ponen a prueba: Navidad de 2026 y el
    Viernes Santo de 2027 caen **en el último viernes de su mes**. El programa
    conserva ahí el festivo y no reparte jornada administrativa —así está
    escrito y así se quiere—, de modo que exigir ADM esos días era medir la
    norma equivocada.

    La exención se cuenta y se nombra, nunca se calla: si algún día se decide
    lo contrario, el número de exentos es lo que lo delata.
    """
    return any(d.get('es_festivo')
               for fila in horario
               for d in fila.get('dias', [])
               if str(d.get('fecha')) == fecha)


def _cuenta_para_el_area(fila, dia) -> bool:
    """¿Esta persona cuenta ese día para el mínimo de su área?"""
    dias = fila.get('cobertura_dias')
    if dias is None:
        return True
    return int(dia.get('dia_semana_numero', -1)) in set(dias)


def _franja(dia):
    """Qué franja operativa cubre esa casilla, según el enunciado de la norma.

    AM y PM se cubren a sí mismas. La **jornada administrativa general conserva
    la franja que la persona tenía**: cambia lo que hace, no el hueco que deja
    en el cuadro. ADM-AC es el horario propio y permanente de Atención al
    Ciudadano y **no cubre nada**: no releva a nadie.
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


def _semanas(horario) -> dict:
    por_semana = collections.defaultdict(set)
    for fila in horario:
        for dia in fila['dias']:
            if dia.get('lunes_semana'):
                por_semana[str(dia['lunes_semana'])].add(str(dia['fecha']))
    return {k: sorted(v) for k, v in por_semana.items()}


# ------------------------------------------------------------ las normas

def norma_casillas(horario) -> Norma:
    n = Norma('sin casillas vacías',
              'cada persona tiene exactamente un turno en cada día del período')
    for fila in horario:
        vistas = collections.Counter(str(d['fecha']) for d in fila['dias'])
        for fecha, veces in vistas.items():
            n.revisar(veces == 1, f"{fila['nombre']}: {fecha} aparece {veces} veces")
        for dia in fila['dias']:
            turno = str(dia.get('turno') or '')
            n.revisar(bool(turno.strip()), f"{fila['nombre']}: {dia['fecha']} sin turno")
            n.revisar('+' not in turno,
                      f"{fila['nombre']}: {dia['fecha']} lleva dos turnos ({turno})")
    return n


def norma_cobertura(horario, reglas) -> tuple[Norma, Norma]:
    suelo = Norma('cobertura mínima del área',
                  'cada área conserva su mínimo cada día, y un mínimo nunca '
                  'puede exigir a toda el área: alguien tiene que descansar')
    techo = Norma('techos de mañana y tarde',
                  'ningún área pasa del máximo configurado en cada franja')

    fechas = sorted({str(d['fecha']) for f in horario for d in f['dias']})
    por_area = collections.defaultdict(list)
    for fila in horario:
        por_area[fila['area']].append(fila)

    for area in AREAS:
        filas = por_area.get(area) or []
        if not filas:
            continue
        regla = reglas.get(area) or {}
        am_min = int(regla.get('am_minimo') or 0)
        pm_min = int(regla.get('pm_minimo') or 0)
        min_area = int(regla.get('minimo_area') or 0)
        am_max, pm_max = regla.get('am_maximo'), regla.get('pm_maximo')

        for fecha in fechas:
            dias = [_por_fecha(f).get(fecha) for f in filas]
            dias = [d for d in dias if d]
            if not dias:
                continue
            if any(d.get('es_ultimo_viernes_administrativo') for d in dias):
                suelo.eximir(f'{NOMBRES[area]} {fecha}: último viernes administrativo')
                continue
            if all(_heredado(d) for d in dias):
                suelo.eximir(f'{NOMBRES[area]} {fecha}: heredado de un mes publicado')
                continue

            presentes = {'AM': 0, 'PM': 0}
            trabajando = vigentes = 0
            for fila in filas:
                dia = _por_fecha(fila).get(fecha)
                if not dia or dia.get('turno') == FUERA or dia.get('vigente') is False:
                    continue
                vigentes += 1
                franja = _franja(dia) if _cuenta_para_el_area(fila, dia) else None
                if franja:
                    trabajando += 1
                    presentes[franja] += 1
            if vigentes == 0:
                continue

            # La válvula, escrita aquí y no heredada del motor.
            exigible = max(0, vigentes - 1)
            if am_min:
                pide = min(am_min, exigible)
                suelo.revisar(presentes['AM'] >= pide,
                              f"{NOMBRES[area]} {fecha}: {presentes['AM']} en AM, "
                              f'exige {pide}')
            if pm_min:
                pide = min(pm_min, exigible)
                suelo.revisar(presentes['PM'] >= pide,
                              f"{NOMBRES[area]} {fecha}: {presentes['PM']} en PM, "
                              f'exige {pide}')
            if min_area:
                pide = min(min_area, exigible)
                suelo.revisar(trabajando >= pide,
                              f'{NOMBRES[area]} {fecha}: {trabajando} cubriendo turno, '
                              f'exige {pide}')
            if am_max is not None:
                techo.revisar(presentes['AM'] <= int(am_max),
                              f"{NOMBRES[area]} {fecha}: {presentes['AM']} en AM, "
                              f'techo {am_max}')
            if pm_max is not None:
                techo.revisar(presentes['PM'] <= int(pm_max),
                              f"{NOMBRES[area]} {fecha}: {presentes['PM']} en PM, "
                              f'techo {pm_max}')
    return suelo, techo


def norma_descanso_semanal(horario) -> Norma:
    n = Norma('descanso semanal',
              'cada persona operativa descansa un día en cada semana completa')
    semanas = _semanas(horario)
    primera = min(semanas) if semanas else None
    for fila in horario:
        dias = _por_fecha(fila)
        for lunes, fechas in semanas.items():
            propios = [dias[f] for f in fechas if f in dias]
            if len(propios) < 7:
                continue
            if lunes == primera:
                n.eximir(f"{fila['nombre']}: semana del {lunes} compartida con el "
                         'mes anterior')
                continue
            if any(_heredado(d) for d in propios):
                n.eximir(f"{fila['nombre']}: semana del {lunes} heredada")
                continue
            if all(d.get('turno') == FUERA or d.get('vigente') is False
                   for d in propios):
                n.eximir(f"{fila['nombre']}: semana del {lunes} fuera de su vigencia")
                continue
            n.revisar(any(d['turno'] in NO_TRABAJO for d in propios),
                      f"{fila['nombre']}: la semana del {lunes} sin ningún día libre")
    return n


def norma_jornadas_seguidas(horario, tope: int) -> Norma:
    n = Norma('máximo de jornadas seguidas',
              f'nadie encadena más de {tope} jornadas seguidas dentro del período')
    for fila in horario:
        racha = mayor = 0
        desde = arranque = None
        for dia in sorted(fila['dias'], key=lambda x: x['fecha']):
            if dia['turno'] in TRABAJO:
                if racha == 0:
                    arranque = dia['fecha']
                racha += 1
                if racha > mayor:
                    mayor, desde = racha, arranque
            else:
                racha = 0
        n.revisar(mayor <= tope,
                  f"{fila['nombre']}: {mayor} jornadas seguidas desde {desde}")
        n.anotar(f"{fila['nombre']}: racha mayor {mayor}")
    return n


def norma_pm_am(horario) -> Norma:
    n = Norma('de la tarde a la mañana siguiente',
              'nadie sale de PM y entra en AM al día siguiente: no caben las '
              'horas de descanso en una noche')
    for fila in horario:
        ordenados = sorted(fila['dias'], key=lambda x: x['fecha'])
        for previo, siguiente in zip(ordenados, ordenados[1:], strict=False):
            if previo['turno'] != 'PM' or siguiente['turno'] != 'AM':
                continue
            uno = date.fromisoformat(previo['fecha'])
            dos = date.fromisoformat(siguiente['fecha'])
            if (dos - uno).days != 1:
                continue
            if _heredado(previo) and _heredado(siguiente):
                n.eximir(f"{fila['nombre']}: {previo['fecha']} heredado")
                continue
            n.revisar(False, f"{fila['nombre']}: PM el {previo['fecha']} y AM el "
                             f"{siguiente['fecha']}")
        n.revisar(True)
    return n


def norma_parejas(horario) -> Norma:
    n = Norma('la pareja nunca en el mismo turno',
              'dos personas emparejadas se cubren entre sí: si coincidieran, la '
              'otra franja quedaría sin ninguna de las dos')
    por_id = {int(f['empleado_id']): f for f in horario}
    vistas = set()
    for fila in horario:
        pareja = fila.get('pareja_id')
        if not pareja or int(pareja) not in por_id:
            continue
        clave = tuple(sorted((int(fila['empleado_id']), int(pareja))))
        if clave in vistas:
            continue
        vistas.add(clave)
        otra = por_id[int(pareja)]
        unos, otros = _por_fecha(fila), _por_fecha(otra)
        for fecha in sorted(set(unos) & set(otros)):
            a, b = unos[fecha], otros[fecha]
            if a['turno'] not in ('AM', 'PM') or a['turno'] != b['turno']:
                n.revisar(True)
                continue
            if a.get('requerimiento_id') or b.get('requerimiento_id'):
                n.eximir(f"{fila['nombre']} y {otra['nombre']} el {fecha}: "
                         'lo autoriza una asignación directa')
                continue
            if a.get('excepcion_forzada') or b.get('excepcion_forzada'):
                n.eximir(f"{fila['nombre']} y {otra['nombre']} el {fecha}: "
                         'excepción autorizada a mano')
                continue
            if _heredado(a) and _heredado(b):
                n.eximir(f"{fila['nombre']} y {otra['nombre']} el {fecha}: heredado")
                continue
            n.revisar(False, f"{fila['nombre']} y {otra['nombre']}: {a['turno']} "
                             f'el {fecha}')
    return n


def norma_compensatorios(horario) -> Norma:
    n = Norma('compensatorio por festivo',
              'quien trabaja un domingo o un festivo del mes tiene después su '
              'día de descanso')
    festivos = sorted({str(d['fecha']) for f in horario for d in f['dias']
                       if d.get('es_festivo')})
    for fila in horario:
        dias = _por_fecha(fila)
        for fecha in festivos:
            dia = dias.get(fecha)
            if not dia or dia['turno'] not in TRABAJO:
                continue
            if not dia.get('mes_propio', True):
                n.eximir(f"{fila['nombre']}: festivo {fecha} es de otro mes")
                continue
            if _heredado(dia):
                n.eximir(f"{fila['nombre']}: festivo {fecha} heredado")
                continue
            tiene = any(x.get('turno') == 'D'
                        and str(x.get('origen') or '') == 'compensatorio_festivo'
                        and x.get('festivo_origen') == fecha
                        for x in fila['dias'])
            n.revisar(tiene, f"{fila['nombre']}: trabajó el festivo {fecha} y no "
                             'tiene compensatorio')
    return n


def norma_domingos(horario, avisos=None) -> Norma:
    """El reparto de domingos, comprobado aquí y no solo por el motor.

    Era la única regla estricta del motor sin comprobación independiente: el
    documento de aceptación de la 4.3.2 lo reconoce («la equidad de domingos
    queda reflejada en los rechazos del motor»). Si el motor y su validación se
    equivocaran a la vez en esto, nada lo diría.

    El enunciado: de los domingos del mes, la mitad trabajados y la mitad
    descansados; con un número impar, el que sobra se descansa. El domingo
    heredado de la semana compartida **cuenta** para el total —es un domingo del
    mes—, aunque este mes no pueda cambiarlo: los demás los decide el programa.

    Exentos, con su motivo:

    * administrativos, quien tiene descanso fijo y quien está exento de
      especiales, a quienes no se les reparte;
    * quien entra o sale a mitad de mes: no alcanza todos los domingos y el
      reparto mensual no se le puede exigir entero (el motor lo deja en aviso);
    * lo que el motor haya **avisado expresamente** para esa persona: es su
      último recurso cuando no existe ningún reparto posible, y se acepta solo si
      queda dicho. Callado sería un fallo.
    """
    n = Norma('reparto de domingos',
              'cada persona trabaja la mitad de los domingos del mes; si son '
              'impares, el que sobra lo descansa')
    avisados = [str(a) for a in (avisos or []) if 'domingos' in str(a)]
    for fila in horario:
        if (fila.get('tipo_turno') == 'administrativo' or fila.get('descanso_fijo') is not None
                or fila.get('exento_especiales')):
            n.eximir(f"{fila['nombre']}: no entra en el reparto de domingos")
            continue
        domingos = [d for d in fila['dias'] if d.get('es_domingo') and d.get('mes_propio', True)]
        if not domingos:
            continue
        vigentes = [d for d in domingos if d['turno'] != FUERA]
        if len(vigentes) < len(domingos):
            n.eximir(f"{fila['nombre']}: vigente en {len(vigentes)} de {len(domingos)} domingos")
            continue
        if all(_heredado(d) for d in vigentes):
            n.eximir(f"{fila['nombre']}: todos sus domingos son heredados")
            continue
        trabajados = sum(d['turno'] in TRABAJO for d in vigentes)
        debe = len(vigentes) // 2
        # El aviso tiene que ser **el de este reparto**, no cualquiera que nombre a
        # la persona y diga «domingos». Con la comprobación floja, un aviso del
        # motor sobre cómo cerró alguien la semana anterior —que menciona los
        # domingos de pasada— servía de permiso, y así se escondían veintidós
        # repartos que el propio motor había rechazado.
        declarado = f"{fila['nombre']}: trabaja {trabajados} de {len(vigentes)} domingos"
        if trabajados != debe and any(declarado in a for a in avisados):
            n.eximir(f"{fila['nombre']}: {trabajados} de {len(vigentes)} domingos, "
                     'avisado por el motor como excepción')
            continue
        n.revisar(trabajados == debe,
                  f"{fila['nombre']}: trabaja {trabajados} de {len(vigentes)} domingos; "
                  f'le tocaban {debe}')
    return n


def norma_ultimo_viernes(horario) -> Norma:
    n = Norma('último viernes administrativo',
              'ese día toda la oficina hace jornada administrativa, salvo quien '
              'tenga una ausencia aprobada y salvo que el día sea festivo')
    fechas = sorted({str(d['fecha']) for f in horario for d in f['dias']
                     if d.get('es_ultimo_viernes_administrativo')})
    if not fechas:
        n.anotar('el período no contiene ningún último viernes')
        return n
    for fecha in fechas:
        if _es_festivo(horario, fecha):
            n.eximir(f'{fecha} es festivo: manda el festivo, no la jornada '
                     'administrativa')
            continue
        for fila in horario:
            dia = _por_fecha(fila).get(fecha)
            if not dia or dia['turno'] == FUERA or dia.get('vigente') is False:
                continue
            if _heredado(dia):
                n.eximir(f"{fila['nombre']}: {fecha} heredado")
                continue
            if dia['turno'] in NO_TRABAJO or dia['turno'] == 'CAP':
                n.eximir(f"{fila['nombre']}: {fecha} con {dia['turno']}")
                continue
            n.revisar(str(dia['turno']).startswith('ADM'),
                      f"{fila['nombre']}: {fecha} con {dia['turno']} y tocaba ADM")
    return n


def norma_adm_ac(horario, reglas) -> Norma:
    """La distinción que este archivo se comió durante varias versiones."""
    n = Norma('ADM-AC no cubre ningún turno',
              'la jornada administrativa de Atención al Ciudadano es un horario '
              'propio y permanente: no releva a nadie')
    filas = [f for f in horario if f['area'] == 'atencion_ciudadano']
    if not filas:
        return n
    regla = reglas.get('atencion_ciudadano') or {}
    min_area = int(regla.get('minimo_area') or 0)
    fechas = sorted({str(d['fecha']) for f in filas for d in f['dias']})
    for fecha in fechas:
        dias = [_por_fecha(f).get(fecha) for f in filas]
        dias = [d for d in dias if d]
        # El viernes administrativo se salta **solo si de verdad lo hay**: la
        # marca del calendario por sí sola exime también a Navidad y al Viernes
        # Santo, que caen en el último viernes de su mes y se programan como
        # festivos con todo el mundo en AM o en PM. Ese fue el agujero que se
        # tapó en `cobertura.py`; aquí se evita el mismo.
        if not dias or any(d.get('es_ultimo_viernes_administrativo')
                           and str(d.get('turno') or '').startswith('ADM')
                           for d in dias):
            continue
        hay_adm_ac = any(d.get('turno') == 'ADM-AC' for d in dias)
        if not hay_adm_ac:
            continue
        # Con ADM-AC en el área, el mínimo lo tiene que cubrir alguien más.
        cubriendo = sum(1 for f in filas
                        if (d := _por_fecha(f).get(fecha))
                        and _franja(d) and _cuenta_para_el_area(f, d))
        if all(_heredado(d) for d in dias):
            n.eximir(f'{fecha}: heredado de un mes publicado')
            continue
        vigentes = sum(1 for d in dias
                       if d.get('turno') != FUERA and d.get('vigente') is not False)
        pide = min(min_area, max(0, vigentes - 1))
        n.revisar(cubriendo >= pide,
                  f'{fecha}: hay ADM-AC y solo {cubriendo} cubriendo turno, '
                  f'exige {pide}')
    return n


def norma_vigencia(horario) -> Norma:
    n = Norma('nadie fuera de su vigencia',
              'antes del alta y después del retiro no se reparte turno: esa '
              'persona no cuenta para nada')
    for fila in horario:
        for dia in fila['dias']:
            if dia.get('vigente') is False:
                n.revisar(dia['turno'] == FUERA,
                          f"{fila['nombre']}: {dia['fecha']} fuera de vigencia "
                          f"con turno {dia['turno']}")
            elif dia['turno'] == FUERA:
                n.revisar(dia.get('vigente') is False,
                          f"{fila['nombre']}: {dia['fecha']} marcado NV estando vigente")
            else:
                n.revisar(True)
    return n


def norma_codigos(horario) -> Norma:
    from gestor.dominio import codigos
    n = Norma('solo códigos que existen',
              f'los turnos son {", ".join(codigos.TODOS)} y ninguno más')
    validos = set(codigos.TODOS)
    for fila in horario:
        for dia in fila['dias']:
            n.revisar(dia['turno'] in validos,
                      f"{fila['nombre']}: {dia['fecha']} = «{dia['turno']}»")
    return n


#: El descanso que el motor colocó por su cuenta y que, por tanto, se puede
#: recolocar. Un domingo, un festivo o un compensatorio llevan otro origen.
DESCANSO_MOVIBLE = 'descanso_automatico'


def _reglas_internas() -> list[dict]:
    """Las reglas particulares que tenga puesta esta instalación, o ninguna."""
    import json

    from gestor import rutas
    archivo = rutas.dato_inicial('reglas_internas.json')
    if not archivo.is_file():
        return []
    try:
        escritas = json.loads(archivo.read_text(encoding='utf-8'))
    except Exception:                                              # noqa: BLE001
        return []
    return [r for r in (escritas or []) if isinstance(r, dict)]


def norma_internas(horario) -> Norma:
    """Las reglas particulares sobre personas concretas, si las hay.

    Estaban escritas en el código con nombres y apellidos, y esta comprobación
    también: preguntaba por tres personas por su nombre. Al pasar el repositorio
    a público, las reglas se fueron a un archivo que viaja con la nómina, así que
    esto lee ese archivo y comprueba lo que ponga.

    Hay una exención que costó entenderla y conviene dejarla escrita. Quién libra
    en **domingo** lo decide la regla de equidad de domingos y festivos, que
    reparte los especiales entre todo el mundo y es más fuerte que esta. Cuando
    los tres coinciden en un domingo, la regla no puede separarlos sin romper esa
    otra, así que no lo intenta, y hace bien.

    Se cuenta aparte y con su motivo, nunca se calla: callarlo sería el mismo
    error que dejó un viernes sin cobertura sin aparecer en ninguna pantalla.
    """
    n = Norma('reglas internas de la oficina',
              'lo que pida reglas_internas.json sobre personas concretas')
    escritas = _reglas_internas()
    if not escritas:
        # Esto **no** es un aprobado: es un «aquí no había nada que mirar», y
        # decirlo importa. Un informe que enseña una norma en verde sin haber
        # revisado un solo caso es exactamente lo que no se quiere.
        n.anotar('esta instalación no tiene ninguna regla interna puesta')
        return n

    nombres = {f['nombre']: f for f in horario}

    def buscar(trozo):
        hallados = [f for k, f in nombres.items() if str(trozo).lower() in k.lower()]
        return hallados[0] if len(hallados) == 1 else None

    for escrita in escritas:
        tipo = str(escrita.get('tipo'))
        if tipo != 'MismosDescansosQueAlguno':
            n.anotar(f'regla de tipo «{tipo}» no comprobada aquí todavía')
            continue
        seguidora = buscar(escrita.get('seguidora'))
        referencias = [buscar(x) for x in (escrita.get('referencias') or [])]
        referencias = [x for x in referencias if x]
        if not seguidora or not referencias:
            n.anotar(f'«{escrita.get("seguidora")}» o sus acompañantes no están '
                     'en este mes')
            continue

        suyos = _por_fecha(seguidora)
        acompañados = solos = 0
        for fecha, dia in sorted(suyos.items()):
            if dia['turno'] != 'D' or _heredado(dia):
                continue
            con = [r for r in referencias
                   if (_por_fecha(r).get(fecha) or {}).get('turno') == 'D']
            if len(con) == len(referencias) and len(referencias) > 1:
                repartido = (dia.get('es_domingo') or dia.get('es_festivo')
                             or str(dia.get('origen') or '') != DESCANSO_MOVIBLE)
                if repartido:
                    razon = ('domingo' if dia.get('es_domingo') else
                             'festivo' if dia.get('es_festivo') else
                             f"descanso de origen «{dia.get('origen')}»")
                    n.eximir(f'{fecha}: coinciden todos, pero es un {razon} y '
                             'quién libra ese día lo decide la regla de equidad')
                    continue
                n.revisar(False, f'{fecha}: descansan todos a la vez pudiendo '
                                 'haberlo evitado')
            elif con:
                acompañados += 1
                n.revisar(True)
            else:
                solos += 1
                n.revisar(True)
        n.anotar(f'descansos acompañados: {acompañados} · en solitario: {solos}')
    return n


# ------------------------------------------------------------- el informe

def revisar_mes(horario, reglas, tope, avisos=None) -> list[Norma]:
    """Todas las normas de un mes. `avisos`, los del motor para esa opción."""
    suelo, techo = norma_cobertura(horario, reglas)
    return [
        norma_casillas(horario),
        norma_codigos(horario),
        suelo,
        techo,
        norma_adm_ac(horario, reglas),
        norma_descanso_semanal(horario),
        norma_jornadas_seguidas(horario, tope),
        norma_pm_am(horario),
        norma_parejas(horario),
        norma_domingos(horario, avisos),
        norma_compensatorios(horario),
        norma_ultimo_viernes(horario),
        norma_vigencia(horario),
        norma_internas(horario),
    ]


def lo_rechazo_el_motor(fallo: str, alternativa: dict) -> bool:
    """¿Este incumplimiento ya lo dijo el motor, y por eso la opción no vale?

    El programa ofrece también las opciones que no cumplen, marcadas como no
    válidas y con su error escrito, para que se vea por qué se descartan. Que
    esta comprobación encuentre lo mismo en una de ellas no es un fallo: es el
    motor y la comprobación independiente diciendo lo mismo. Lo que sí sería un
    fallo, y se sigue contando, es:

    * un incumplimiento en una opción que el motor da por **válida**;
    * o uno en una opción no válida que el motor **no** nombra en sus errores.

    Se compara lo que va antes del «;» —«Fulano: trabaja 3 de 4 domingos»— con
    el texto de los errores: si el motor se calla ese caso, no se exime.
    """
    if alternativa.get('valido', True):
        return False
    esencial = fallo.split(';', 1)[0].strip()
    return bool(esencial) and any(esencial in str(e) for e in alternativa.get('errores') or [])


def main() -> int:
    from gestor.dominio import calendario

    problemas = 0
    revisados_total = 0
    with Servidor('/tmp/qa_reglas') as servidor:
        cabeceras = entrar_como_admin(servidor)
        print(f'Servidor en {servidor.base}\n')
        estado, operacion = servidor.pedir('/api/configuracion/reglas-operacion',
                                           cabeceras=cabeceras)
        tope = int(operacion['vigente']['max_dias_consecutivos'])
        print(f'Tope de jornadas seguidas configurado: {tope}\n')

        for anio, mes in MESES:
            nombre = calendario.nombre_del_periodo(mes, anio)
            estado, generado = servidor.pedir('/api/horarios/generar', 'POST',
                                              {'mes': mes, 'anio': anio}, cabeceras)
            if estado != 200:
                print(f'{nombre.upper()}: no se pudo generar · '
                      f'{generado.get("detail")}')
                problemas += 1
                continue

            reglas = reglas_vigentes_en(servidor, cabeceras, anio, mes)
            print(f'{nombre.upper()}  ({len(generado["alternativas"])} propuestas)')
            for numero, alternativa in enumerate(generado['alternativas'], 1):
                normas = revisar_mes(alternativa['horario'], reglas, tope,
                                     alternativa.get('advertencias'))
                revisados = sum(n.revisados for n in normas)
                revisados_total += revisados
                malas = [n for n in normas if not n.bien]
                cabecera = f'  opción {numero} · {revisados} comprobaciones'
                if malas and not alternativa.get('valido', True):
                    cabecera += '  ← no válida: el motor la descarta'
                elif malas:
                    cabecera += '  ← INCUMPLE'
                print(cabecera)
                for norma in normas:
                    print(norma.linea())
                    for fallo in norma.fallos[:4]:
                        if lo_rechazo_el_motor(fallo, alternativa):
                            print(f'          · {fallo}  [el motor también la rechaza: coinciden]')
                            continue
                        print(f'          · {fallo}')
                        problemas += 1
                    for nota in norma.notas[:1]:
                        print(f'          ({nota})')

            elegida = next((a for a in generado['alternativas'] if a['valido']),
                           generado['alternativas'][0])
            servidor.pedir(f'/api/horarios/{elegida["horario_id"]}/oficial',
                           'PATCH', None, cabeceras)
            servidor.pedir(f'/api/operacion/publicacion/{elegida["horario_id"]}',
                           'POST', {'confirmar_excepciones': True}, cabeceras)
            print()

    print('=' * 72)
    print(f'{revisados_total} comprobaciones de norma sobre {len(MESES)} meses.')
    if problemas:
        print(f'{problemas} incumplimiento(s).')
        return 1
    print('Ninguna norma incumplida.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
