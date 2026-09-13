# -*- coding: utf-8 -*-
"""Reglas particulares que la aplicación aplica sin decir que existen.

Esto no son las reglas de ley —esas están en `nucleo_normativo.py` y valen para
todo el mundo—. Aquí van las decisiones concretas sobre personas concretas:
«Fulana descansa los mismos días que Mengana», «Zutano nunca coincide con
Perengano en el mismo turno», «a Menganita se le procura el sábado libre».

**No aparecen en ninguna pantalla.** Ni en Configuración, ni en Validación, ni
en el Historial. No hay ruta que las liste ni mensaje que las mencione. Quien
usa la aplicación ve el horario resultante y nada más. Para añadir, cambiar o
quitar una se edita `reglas_internas.json`, que va junto a los datos iniciales.

## Por qué en un archivo y no aquí

Estuvieron escritas en este código, con nombres y apellidos, hasta que el
repositorio pasó a ser público. Una regla de estas dice quién no puede coincidir
con quién y **por qué**, y eso es asunto de la oficina y de nadie más. Ahora
viajan con la nómina, fuera del repositorio.

De paso deja de hacer falta recompilar el programa para cambiar una: quién
descansa con quién cambia cuando cambia la gente, que es bastante más a menudo
que una versión.

## Cómo se añade una

En `reglas_internas.json`, que de fábrica no existe:

    [
      {"tipo": "MismosDescansos",
       "referencia": "Carolina Estefanía", "seguidora": "Elena Marcela",
       "porque": "Comparten transporte desde el mismo barrio."},
      {"tipo": "NuncaJuntos", "una": "Fulano", "otra": "Zutano",
       "porque": "Acuerdo de la coordinación tras el incidente de julio."},
      {"tipo": "ProcurarDescanso", "quien": "Mengana", "dias": [5],
       "porque": "Estudia los sábados por la mañana."}
    ]

A las personas se las nombra por un trozo de su nombre, el que baste para que no
haya dos. El `porque` es obligatorio y no se enseña en ninguna parte: está para
quien lea el archivo dentro de dos años. Una regla sin motivo escrito acaba
borrándose por parecer arbitraria, o peor, conservándose sin que nadie sepa por
qué.

## La barrera que ninguna puede saltar

Una regla de aquí **nunca produce un horario inválido**. Se aplican como
preferencias dentro de lo que ya es válido: si mover un descanso rompería el
descanso semanal de alguien, o el tope de jornadas seguidas, el cambio se
deshace y esa semana la regla sencillamente no se aplica. En silencio, sin
avisar, pero sin romper nada.

Eso no es una cortesía: es lo que hace que esto sea seguro. Una regla oculta que
pudiera saltarse las de ley sería una forma de producir horarios ilegales sin
que nadie viera por qué.

## La segunda barrera: lo que decidió una persona gana siempre

Una regla de aquí solo puede tocar dos cosas: un descanso que el motor colocó
por su cuenta y una jornada corriente sin nada encima. Un permiso aprobado, una
asignación, un compensatorio, un descanso fijo configurado, un cambio hecho a
mano: nada de eso se mueve. Si la única forma de aplicar la regla fuera pisar
algo así, no se aplica.

Sin esto, alguien vería su solicitud aceptada en pantalla y el día trabajado en
el horario, y no habría manera de explicarle por qué.

## Dónde se aplican

En `motor/orquestacion.py`, justo después de repartir los descansos semanales y
antes de las reparaciones. Ni antes —no habría descansos que alinear— ni
después —las reparaciones ya habrían dado el mes por bueno y nadie repasaría lo
que las reglas movieron—.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from gestor.dominio import nucleo as nucleo_normativo

LUNES, MARTES, MIERCOLES, JUEVES, VIERNES, SABADO, DOMINGO = range(7)

TRABAJO = nucleo_normativo.TRABAJO

# Qué se puede mover y qué no.
#
# Esto se decide por lista blanca, no por lista negra, y es a propósito. El
# primer intento iba al revés —«todo es movible salvo lo que lleve marca de
# solicitud, requerimiento o ajuste manual»— y al mirar un mes de verdad se vio
# el problema: el motor marca `bloqueado` cada descanso que coloca, y hay ocho
# orígenes distintos de descanso. Una lista negra que se quede corta convierte
# una preferencia oculta en algo capaz de borrar un compensatorio de festivo.
# Al revés, si la lista blanca se queda corta, lo peor que pasa es que la regla
# no se aplique, que es exactamente el fallo que se prefiere.
#
# Solo hay dos casillas movibles:
#
#   · el descanso que el motor repartió por su cuenta, y
#   · una jornada normal sin nada encima.
#
# Queda fuera, y no por olvido: lo heredado del mes anterior (`base_…`), el
# descanso dominical y el de festivo, el compensatorio, el descanso fijo que
# alguien configuró, lo que salió de una solicitud aprobada o de un
# requerimiento, el último viernes administrativo y cualquier ajuste hecho a
# mano. Todo eso son decisiones de una persona o piezas estructurales del mes;
# una preferencia escrita en el código pierde contra ellas siempre.
DESCANSO_MOVIBLE = 'descanso_automatico'
JORNADA_MOVIBLE = 'turno_base'

# Lo último que se aplicó, para poder depurar desde Python. No lo expone ninguna
# ruta ni lo enseña ninguna pantalla: la aplicación no debe dejar ver que estas
# reglas existen.
ultimo_informe: list[str] = []


def _descanso_movible(dia: dict) -> bool:
    """Un día libre que puso el motor por su cuenta y que se puede recolocar."""
    return dia.get('turno') == 'D' and str(dia.get('origen') or '') == DESCANSO_MOVIBLE


def _dia_repartido(dia: dict) -> bool:
    """Un domingo o un festivo: quién libra ese día lo decide una regla de equidad.

    Esto no estaba y era el motivo número uno de que las reglas internas no se
    aplicaran. Las personas con las que se quiere hacer coincidir a alguien
    libran a menudo en domingo —les toca su mitad—, así que la regla intentaba
    llevar el descanso a ese domingo, la validación veía que entonces esa
    persona ya no trabajaba los domingos que le tocaban, y lo deshacía. Cuarenta
    y ocho intentos de setenta se perdían así.

    Los domingos y festivos se reparten entre toda la plantilla para que a nadie
    le toquen siempre los mismos. Una preferencia sobre dos personas no tiene por
    qué poder desequilibrar eso, así que ni se intenta.
    """
    return bool(dia.get('es_domingo') or dia.get('es_festivo'))


def _jornada_movible(dia: dict) -> bool:
    """Un día de trabajo corriente, sin solicitud, asignación ni marca encima."""
    return (dia.get('turno') in TRABAJO
            and str(dia.get('origen') or '') == JORNADA_MOVIBLE
            and not dia.get('bloqueado'))


def _persona(horario: list[dict], quien: str) -> dict | None:
    """Encuentra a alguien por un trozo de su nombre, o por su número."""
    if isinstance(quien, int) or str(quien).isdigit():
        return next((f for f in horario if int(f['empleado_id']) == int(quien)), None)
    trozo = str(quien).lower()
    coincidencias = [f for f in horario if trozo in str(f.get('nombre', '')).lower()]
    return coincidencias[0] if len(coincidencias) == 1 else None


def _por_fecha(fila: dict) -> dict[str, dict]:
    return {d['fecha']: d for d in fila.get('dias', [])}


def _semanas(dias: dict[str, dict]) -> dict[str, list[str]]:
    """Las fechas de cada persona agrupadas por semana."""
    fuera: dict[str, list[str]] = {}
    for fecha, dia in dias.items():
        fuera.setdefault(str(dia.get('lunes_semana') or ''), []).append(fecha)
    return {lunes: sorted(fechas) for lunes, fechas in fuera.items()}


def _alinear_semana(dias: dict[str, dict], fechas: list[str],
                    objetivo: set[str]) -> tuple[list[tuple[str, str]], int] | None:
    """Qué habría que mover para que esta persona descanse dentro de `objetivo`.

    Devuelve los traslados (de dónde, a dónde) y con cuántos días acabaría
    coincidiendo. `None` cuando no hay nada que hacer porque esa semana no
    descansa.

    Es de mejor esfuerzo y no de todo o nada, y eso se decidió mirando los
    números. Exigiendo que **todos** sus descansos de la semana coincidieran, la
    regla se aplicaba en poco más de la mitad de las semanas, y casi siempre
    fallaba por lo mismo: uno de sus dos días libres era un domingo, los
    domingos se reparten con su propia regla de equidad y no se pueden mover.
    Perder la semana entera por eso deja a la persona librando sola un día que
    sí se podía haber hecho coincidir.
    """
    descansos = [f for f in fechas if dias[f]['turno'] == 'D']
    if not descansos:
        return None
    ya_coinciden = [f for f in descansos if f in objetivo]
    # Solo se intentan mover los que el motor puso por su cuenta. Un domingo, un
    # festivo o un compensatorio se quedan donde están aunque no coincidan.
    fuera = [f for f in descansos if f not in objetivo and _descanso_movible(dias[f])]
    destinos = [f for f in sorted(objetivo)
                if f in dias and dias[f]['turno'] != 'D' and _jornada_movible(dias[f])
                and not _dia_repartido(dias[f])]
    traslados = list(zip(sorted(fuera), destinos))
    return traslados, len(ya_coinciden) + len(traslados)


def _aplicar_semana(dias: dict[str, dict], traslados: list[tuple[str, str]],
                    aceptar: Callable[[], bool] | None) -> bool:
    """Mueve los descansos de una semana y los devuelve si no cuelan.

    Deshacer la regla entera porque una semana no cuadra sale carísimo: en las
    mediciones se perdían las cuatro semanas buenas de un mes por la quinta. Se
    pregunta semana a semana.
    """
    if not traslados:
        return False
    foto = [(dias[f], dias[f]['turno'], str(dias[f].get('origen') or ''),
             bool(dias[f].get('bloqueado')))
            for par in traslados for f in par]
    for origen, destino in traslados:
        _mover_descanso(dias, origen, destino)
    if aceptar is not None and not aceptar():
        _restaurar(foto)
        return False
    return True


def _mover_descanso(dias: dict[str, dict], origen: str, destino: str) -> None:
    """Lleva un día libre de un día a otro, dejando las marcas como el motor."""
    turno_previo = dias[destino]['turno']
    dias[destino]['turno'] = 'D'
    dias[destino]['origen'] = DESCANSO_MOVIBLE
    dias[destino]['bloqueado'] = True
    dias[origen]['turno'] = turno_previo
    dias[origen]['origen'] = JORNADA_MOVIBLE
    dias[origen]['bloqueado'] = False


# --------------------------------------------------------------------------
# Los tipos de regla
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Regla:
    """Lo que toda regla interna tiene que traer."""

    porque: str

    def describir(self) -> str:                                  # pragma: no cover
        return self.__class__.__name__

    def aplicar(self, horario: list[dict],
                aceptar: Callable[[], bool] | None = None) -> list[str]:  # pragma: no cover
        """Cambia el horario y cuenta qué hizo.

        `aceptar()` responde si el horario, tal y como está en este momento,
        sigue siendo publicable. Una regla que trabaje por semanas debería
        llamarlo después de cada semana y deshacer solo esa si dice que no: sin
        eso, una semana que no cuadra tira abajo el trabajo de las otras cuatro.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class MismosDescansos(Regla):
    """Que dos personas descansen los mismos días.

    Se toma a la primera como referencia y se intenta que la segunda coincida,
    semana a semana. Si una semana no se puede alinear del todo, esa semana se
    deja como estaba: media alineación no es lo que pide la regla.
    """

    una: str = ''
    otra: str = ''

    def __init__(self, una: str, otra: str, *, porque: str):
        object.__setattr__(self, 'una', una)
        object.__setattr__(self, 'otra', otra)
        object.__setattr__(self, 'porque', porque)

    def describir(self) -> str:
        return f'{self.otra} descansa como {self.una}'

    def aplicar(self, horario: list[dict],
                aceptar: Callable[[], bool] | None = None) -> list[str]:
        referencia = _persona(horario, self.una)
        seguidora = _persona(horario, self.otra)
        if not referencia or not seguidora or referencia is seguidora:
            return []

        dias_ref = _por_fecha(referencia)
        dias_seg = _por_fecha(seguidora)
        hechos = []
        for lunes, fechas in sorted(_semanas(dias_seg).items()):
            objetivo = {f for f in fechas
                        if dias_ref.get(f) and dias_ref[f]['turno'] == 'D'}
            if not objetivo:
                continue
            resultado = _alinear_semana(dias_seg, fechas, objetivo)
            if not resultado or not resultado[0]:
                continue
            traslados = resultado[0]
            if not _aplicar_semana(dias_seg, traslados, aceptar):
                continue
            hechos.append(f'{seguidora["nombre"]} semana del {lunes}: '
                          + ', '.join(f'{o} → {d}' for o, d in traslados))
        return hechos


@dataclass(frozen=True)
class MismosDescansosQueAlguno(Regla):
    """Que alguien descanse con cualquiera de varias personas, la que se pueda.

    La diferencia con `MismosDescansos` es que aquí no hay una sola referencia:
    se da una lista y cada semana vale la que salga. Una semana puede coincidir
    con la primera, la siguiente con la segunda, o dos seguidas con la misma; da
    igual, la regla se cumple mientras coincida con alguna.

    Eso la hace mucho más fácil de cumplir que la de una sola referencia, y es
    justo el motivo de que exista: con una única referencia, la semana en que
    esa persona descansa un día que a la otra no le sirve se pierde entera.

    Se busca coincidir con **una** candidata, no con todas. Un día en el que ya
    descansan dos de ellas no vale como destino: lo que se pidió es que esta
    persona no libre sola, no que el grupo entero libre a la vez, y juntar a
    tres personas el mismo día cuesta cobertura sin dar nada a cambio. Si por su
    cuenta acaban coincidiendo los tres, se deja: esta regla mueve descansos
    para acercarlos, nunca para separarlos.

    Entre las candidatas que se pueden, se elige la que menos haya que mover, y
    a igualdad la que se escribió primero. Así el resultado no depende del orden
    en que Python recorra nada: el mismo mes sale siempre igual.

    Las candidatas pueden ser de otra área. Por eso las reglas se aplican sobre
    el horario completo y no dentro del motor de cada área.
    """

    quien: str = ''
    candidatos: tuple[str, ...] = ()

    def __init__(self, quien: str, candidatos: Sequence[str], *, porque: str):
        object.__setattr__(self, 'quien', quien)
        object.__setattr__(self, 'candidatos', tuple(candidatos))
        object.__setattr__(self, 'porque', porque)

    def describir(self) -> str:
        return f'{self.quien} descansa con alguno de {list(self.candidatos)}'

    def aplicar(self, horario: list[dict],
                aceptar: Callable[[], bool] | None = None) -> list[str]:
        fila = _persona(horario, self.quien)
        if not fila:
            return []
        referencias = [r for r in (_persona(horario, c) for c in self.candidatos)
                       if r is not None and r is not fila]
        if not referencias:
            return []

        dias = _por_fecha(fila)
        dias_ref = [(r['nombre'], _por_fecha(r)) for r in referencias]
        hechos = []

        for lunes, fechas in sorted(_semanas(dias).items()):
            # Se prueba con cada candidata y se elige con la que acabe
            # coincidiendo en más días; a igualdad, la que menos haya que mover,
            # y a igualdad otra vez, la que se escribió primero. El orden fijo
            # importa: sin él el mismo mes podría salir de dos maneras.
            opciones = []
            for indice, (nombre_ref, dias_r) in enumerate(dias_ref):
                objetivo = {f for f in fechas
                            if dias_r.get(f) and dias_r[f]['turno'] == 'D'}
                # Con uno basta, y juntar a los tres no es lo que se pidió: la
                # idea es que esta persona no libre sola, no que el grupo entero
                # libre el mismo día. Un día en el que descansan las dos
                # candidatas se descarta como destino; si ya coincidían por su
                # cuenta se deja como está, porque la regla mueve descansos, no
                # los separa.
                descansan_las_otras = {
                    f
                    for _, dias_o in dias_ref if dias_o is not dias_r
                    for f in fechas
                    if (dias_o.get(f) or {}).get('turno') == 'D'
                }
                objetivo -= descansan_las_otras
                if not objetivo:
                    continue
                resultado = _alinear_semana(dias, fechas, objetivo)
                if resultado is None:
                    continue
                traslados, coincidencias = resultado
                if not coincidencias:
                    continue
                opciones.append((-coincidencias, len(traslados), indice,
                                 nombre_ref, traslados))
            if not opciones:
                continue
            # Se prueban por orden de preferencia y se queda la primera que la
            # validación acepte: que la mejor sobre el papel no quepa no
            # significa que la segunda tampoco.
            for _, _, _, nombre_ref, traslados in sorted(opciones):
                if not traslados:
                    break              # ya coincidía: no hay nada que hacer
                if _aplicar_semana(dias, traslados, aceptar):
                    hechos.append(f'semana del {lunes}: con {nombre_ref} ('
                                  + ', '.join(f'{o} → {d}' for o, d in traslados) + ')')
                    break
        return hechos


@dataclass(frozen=True)
class NuncaJuntos(Regla):
    """Que dos personas no coincidan nunca en la misma franja el mismo día.

    Se cambia el turno de la segunda cuando coinciden, y solo si ese día es un
    turno que puso el motor. No se toca a la primera.
    """

    una: str = ''
    otra: str = ''

    def __init__(self, una: str, otra: str, *, porque: str):
        object.__setattr__(self, 'una', una)
        object.__setattr__(self, 'otra', otra)
        object.__setattr__(self, 'porque', porque)

    def describir(self) -> str:
        return f'{self.una} y {self.otra} nunca en el mismo turno'

    def aplicar(self, horario: list[dict],
                aceptar: Callable[[], bool] | None = None) -> list[str]:
        primera = _persona(horario, self.una)
        segunda = _persona(horario, self.otra)
        if not primera or not segunda or primera is segunda:
            return []

        dias_a = _por_fecha(primera)
        dias_b = _por_fecha(segunda)
        hechos = []
        for fecha, dia_b in dias_b.items():
            dia_a = dias_a.get(fecha)
            if not dia_a or dia_a['turno'] not in {'AM', 'PM'}:
                continue
            if dia_b['turno'] != dia_a['turno'] or not _jornada_movible(dia_b):
                continue
            antes = dia_b['turno']
            dia_b['turno'] = 'PM' if antes == 'AM' else 'AM'
            if aceptar is not None and not aceptar():
                dia_b['turno'] = antes
                continue
            hechos.append(f'{segunda["nombre"]} {fecha}: pasa a {dia_b["turno"]}')
        return hechos


@dataclass(frozen=True)
class ProcurarDescanso(Regla):
    """Procurar que a alguien le toque libre cierto día de la semana.

    «Procurar» y no «garantizar»: si esa semana no hay forma de moverlo sin
    romper algo, se deja como estaba.
    """

    quien: str = ''
    dias: tuple[int, ...] = ()

    def __init__(self, quien: str, *, dias: Sequence[int], porque: str):
        object.__setattr__(self, 'quien', quien)
        object.__setattr__(self, 'dias', tuple(dias))
        object.__setattr__(self, 'porque', porque)

    def describir(self) -> str:
        return f'a {self.quien} se le procura libre el día {self.dias}'

    def aplicar(self, horario: list[dict],
                aceptar: Callable[[], bool] | None = None) -> list[str]:
        fila = _persona(horario, self.quien)
        if not fila:
            return []
        dias = _por_fecha(fila)
        hechos = []
        semanas: dict[str, list[str]] = {}
        for fecha, dia in dias.items():
            semanas.setdefault(str(dia.get('lunes_semana') or ''), []).append(fecha)

        for lunes, fechas in sorted(semanas.items()):
            preferidos = [f for f in sorted(fechas)
                          if int(dias[f].get('dia_semana_numero', -1)) in self.dias]
            if not preferidos or any(dias[f]['turno'] == 'D' for f in preferidos):
                continue
            destino = next((f for f in preferidos if _jornada_movible(dias[f])), None)
            origen = next((f for f in sorted(fechas) if _descanso_movible(dias[f])), None)
            if not destino or not origen:
                continue
            if not _aplicar_semana(dias, [(origen, destino)], aceptar):
                continue
            hechos.append(f'{fila["nombre"]}: descanso {origen} → {destino} (semana del {lunes})')
        return hechos


# --------------------------------------------------------------------------
# Las reglas activas
# --------------------------------------------------------------------------
#
# De fábrica no hay ninguna. Se leen de un archivo que viaja **fuera del
# repositorio**, junto a la nómina, y por un motivo que no es técnico: una regla
# de estas nombra a personas concretas y dice por qué —«que no libre sola», «que
# no coincida con»—. Eso es asunto de la oficina y de nadie más, y el
# repositorio es público.
#
# El archivo es `reglas_internas.json`, y va al lado de los datos iniciales:
#
#     [
#       {"tipo": "MismosDescansos",
#        "referencia": "Carolina Estefanía", "seguidora": "Elena Marcela",
#        "porque": "Comparten transporte desde el mismo barrio."},
#       {"tipo": "MismosDescansosQueAlguno",
#        "seguidora": "Mengana", "referencias": ["Fulano", "Zutano"],
#        "porque": "..."},
#       {"tipo": "NuncaJuntos", "una": "Fulano", "otra": "Zutano",
#        "porque": "..."},
#       {"tipo": "ProcurarDescanso", "quien": "Fulana", "dias": [5],
#        "porque": "..."}
#     ]
#
# El `porque` sigue siendo obligatorio y sigue sin enseñarse en ninguna parte:
# está para quien lea el archivo dentro de dos años. Una regla sin motivo escrito
# acaba borrándose por parecer arbitraria, o peor, conservándose sin que nadie
# sepa por qué.
#
# Sin archivo no hay reglas internas y la aplicación funciona igual. Un archivo
# roto tampoco tumba nada: se anota en el registro y se sigue sin él, porque
# quedarse sin horario por una preferencia sería cambiar un problema pequeño por
# uno grande.

def _leer_las_reglas() -> tuple[Regla, ...]:
    import json

    from gestor import rutas
    from gestor.registro import obtener as obtener_registro

    archivo = rutas.dato_inicial('reglas_internas.json')
    if not archivo.is_file():
        return ()
    try:
        escritas = json.loads(archivo.read_text(encoding='utf-8'))
    except Exception:                                              # noqa: BLE001
        obtener_registro().exception('no se pudo leer %s', archivo)
        return ()

    construir = {
        'MismosDescansos': lambda d: MismosDescansos(
            d['referencia'], d['seguidora'], porque=d['porque']),
        'MismosDescansosQueAlguno': lambda d: MismosDescansosQueAlguno(
            d['seguidora'], tuple(d['referencias']), porque=d['porque']),
        'NuncaJuntos': lambda d: NuncaJuntos(d['una'], d['otra'], porque=d['porque']),
        'ProcurarDescanso': lambda d: ProcurarDescanso(
            d['quien'], dias=tuple(d['dias']), porque=d['porque']),
    }
    salida = []
    for escrita in escritas or ():
        hacer = construir.get(str((escrita or {}).get('tipo')))
        if hacer is None:
            obtener_registro().warning(
                'regla interna de tipo desconocido: %r', (escrita or {}).get('tipo'))
            continue
        try:
            salida.append(hacer(escrita))
        except Exception:                                          # noqa: BLE001
            obtener_registro().exception('regla interna mal escrita: %r', escrita)
    return tuple(salida)


def reglas_activas() -> tuple[Regla, ...]:
    """Las reglas escritas ahora mismo. Se lee el archivo cada vez.

    Leerlo una sola vez al importar el módulo sería más barato y estaría mal:
    la carpeta de datos se decide después de importar —en las pruebas cambia con
    cada una, y restablecer de fábrica la vuelve a sembrar—, así que las reglas
    se quedarían congeladas en lo que hubiera en el primer momento. El archivo
    tiene cuatro líneas; leerlo otra vez no se nota.
    """
    return _leer_las_reglas()

# --------------------------------------------------------------------------
# Aplicarlas
# --------------------------------------------------------------------------

def _foto(horario: list[dict]) -> list[tuple[dict, str, str, bool]]:
    # También el bloqueo: restaurar solo turno y origen dejaría el día a medias
    # y el motor lo trataría como movible cuando no lo es.
    return [(d, d['turno'], str(d.get('origen') or ''), bool(d.get('bloqueado')))
            for fila in horario for d in fila.get('dias', [])]


def _restaurar(foto) -> None:
    for dia, turno, origen, bloqueado in foto:
        dia['turno'] = turno
        dia['origen'] = origen
        dia['bloqueado'] = bloqueado


def aplicar(horario: list[dict], reglas: Sequence[Regla] | None = None,
            validar: Callable[[list[dict]], list[str]] | None = None) -> None:
    """Aplica las reglas internas sobre un horario ya armado.

    No devuelve nada ni añade avisos: la aplicación no debe dejar ver que estas
    reglas existen. Lo único que queda es `ultimo_informe`, que solo se puede
    leer desde Python y sirve para depurar.

    Cada regla se aplica sobre una foto del horario. Si al terminar el resultado
    tiene un problema que antes no tenía, se deshace entera: una preferencia
    escrita en el código no puede producir un horario que no se pueda publicar.

    `validar` decide qué cuenta como problema. Sin él se mira solo el núcleo
    normativo, que es lo mínimo. El motor le pasa la validación completa del
    mes, que además vigila la cobertura de cada área y las rachas —hace falta,
    porque para cuando estas reglas se aplican las reparaciones ya pasaron y
    nadie va a repasar lo que se mueva—.
    """
    global ultimo_informe
    ultimo_informe = []
    reglas = reglas_activas() if reglas is None else reglas
    if not reglas or not horario:
        return

    revisar = validar or nucleo_normativo.revisar
    problemas_antes = set(revisar(horario))

    def aceptar() -> bool:
        """¿El horario, tal y como está ahora, sigue siendo publicable?

        No basta con que no tenga problemas: puede que ya viniera con alguno y
        no es trabajo de estas reglas arreglarlo. Lo que no puede es tener uno
        que antes no tenía.
        """
        nonlocal problemas_antes
        ahora = set(revisar(horario))
        if ahora - problemas_antes:
            return False
        problemas_antes = ahora
        return True

    for regla in reglas:
        foto = _foto(horario)
        try:
            hechos = regla.aplicar(horario, aceptar)
        except Exception as exc:                                 # noqa: BLE001
            # Una regla mal escrita no puede tumbar la generación de un mes.
            _restaurar(foto)
            ultimo_informe.append(f'[{regla.describir()}] falló y se ignoró: {exc}')
            continue

        if not hechos:
            continue

        problemas_despues = set(revisar(horario))
        nuevos = problemas_despues - problemas_antes
        if nuevos:
            _restaurar(foto)
            ultimo_informe.append(
                f'[{regla.describir()}] se deshizo: habría roto '
                f'{len(nuevos)} cosa(s). ' + '; '.join(sorted(nuevos)[:2]))
            continue

        problemas_antes = problemas_despues
        ultimo_informe.append(f'[{regla.describir()}] ' + ' · '.join(hechos[:12]))


def catalogo() -> list[dict]:
    """Las reglas activas con su motivo. Para leer desde Python, no para la aplicación.

    Ninguna ruta la expone y ninguna pantalla la enseña, a propósito. Existe
    para que quien mantenga el programa pueda responder «¿por qué sale esto
    así?» sin tener que leer el archivo entero.
    """
    return [{'tipo': type(r).__name__, 'describe': r.describir(), 'porque': r.porque}
            for r in reglas_activas()]
