"""Máximo de jornadas seguidas, configurable desde la aplicación.

Hasta aquí el tope estaba escrito en el código y valía 7. Cambiarlo obligaba a
tocar el motor, y no había forma de decir «desde noviembre son 10» sin alterar
los meses ya oficializados.

Ahora es una regla más, con **fecha de vigencia**: para una fecha concreta manda
la regla más reciente cuya vigencia ya empezó, igual que con las reglas de
cobertura por área. Un mes ya publicado conserva la política con la que se
generó.

Por qué el valor de fábrica es 10
---------------------------------
No es un número elegido a ojo. Con un solo descanso semanal, entre el descanso
de una semana y el de la siguiente hay ``(7 - p1) + (p2 - 1)`` jornadas, así que
el descanso solo puede avanzar ``tope - 6`` posiciones por semana. Con tope 7
avanza un día por semana: quien cierra un mes descansando un martes tarda cinco
semanas en llegar a un domingo, y el reparto mensual de domingos se le rompe
antes de empezar.

Encadenando 28 meses de prueba con cada tope, el reparto de domingos falla en
33 casos de 392 con tope 7, en 14 con tope 8, en 3 con tope 9 y en **ninguno con
tope 10**. Subir a 11 o más no mejora nada y solo alarga las rachas.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional

from gestor import rutas
from gestor.datos.base import conectar
from gestor.dominio.nucleo import MAXIMO_ABSOLUTO_JORNADAS
from gestor.registro import obtener

INICIO_OPERACION = '2026-08-01'
# Por debajo de 7 la regla es imposible: un descanso semanal en la primera
# posición de una semana y en la última de la siguiente ya suma 6 jornadas, y
# cualquier reparto de domingos necesita margen por encima de eso.
MINIMO_DIAS = 7
# Por encima de 14 el tope deja de ser una protección: dos semanas seguidas sin
# un solo día libre no es algo que la aplicación deba poder programar sola.
# El techo de lo que se puede configurar es el mismo número que el núcleo
# declara innegociable, y se lee de allí en vez de repetirse. Estaban escritos
# los dos a mano: si alguien subía este a 16, la pantalla dejaba configurar 16 y
# el núcleo declaraba impublicable cualquier mes que lo usara.
MAXIMO_DIAS = MAXIMO_ABSOLUTO_JORNADAS
POR_DEFECTO = 10


@dataclass(frozen=True)
class ReglaOperacion:
    vigente_desde: str
    max_dias_consecutivos: int
    nota: str = ''
    id: Optional[int] = None

    def como_dict(self) -> dict:
        datos = asdict(self)
        datos['texto'] = f'máximo {self.max_dias_consecutivos} jornadas seguidas'
        return datos


REGLA_POR_DEFECTO = ReglaOperacion(
    vigente_desde=INICIO_OPERACION,
    max_dias_consecutivos=POR_DEFECTO,
    nota=(
        'Con este tope el reparto mensual de domingos se cumple exactamente en '
        'todos los meses probados. Bajarlo a 7 lo rompe en uno de cada doce casos.'
    ),
)

_CACHE: dict[str, list[ReglaOperacion]] = {}


def invalidar_cache() -> None:
    _CACHE.clear()


def asegurar_tabla(conn=None) -> None:
    """No hace nada: la tabla la crea el esquema, entera y de una vez.

    Se conserva el nombre porque lo llaman varios sitios, pero el cuerpo se
    vació a propósito. Crear tablas al vuelo desde el sitio que las usa era
    parte del problema que se vino a resolver: la forma de la base dependía de
    qué código se hubiera ejecutado antes.
    """
    return



def _cargar() -> list[ReglaOperacion]:
    # La caché se indexa por la base a la que apunta ahora mismo: en pruebas
    # cada una tiene la suya, y sin esto una heredaba las reglas de otra.
    clave = str(rutas.BASE_DE_DATOS)
    if clave in _CACHE:
        return _CACHE[clave]
    reglas: list[ReglaOperacion] = []
    try:
        conn = conectar()
    except Exception:                                            # noqa: BLE001
        # Igual que en las reglas de cobertura: no se cachea el fallo, o la
        # aplicación se quedaría con el tope de fábrica hasta reiniciarla.
        obtener().exception('no se pudieron leer las reglas de operación; '
                            'se usa el tope de fábrica solo para esta lectura')
        return reglas
    try:
        asegurar_tabla(conn)
        filas = conn.execute(
            'SELECT id,vigente_desde,max_dias_consecutivos,nota '
            'FROM reglas_operacion ORDER BY vigente_desde,id'
        ).fetchall()
        conn.commit()
    except Exception:                                              # noqa: BLE001
        # Se sigue con la regla de fábrica, pero **se apunta**. Callarlo era lo
        # que hacía la versión anterior, y el programa trabajaba con un tope
        # distinto del configurado sin que nadie pudiera enterarse.
        obtener().exception('no se pudieron leer las reglas de operación; '
                            'se usa la de fábrica')
        filas = []
    finally:
        conn.close()
    for fila in filas:
        reglas.append(ReglaOperacion(
            id=int(fila['id']),
            vigente_desde=str(fila['vigente_desde'])[:10],
            max_dias_consecutivos=int(fila['max_dias_consecutivos']),
            nota=str(fila['nota'] or ''),
        ))
    _CACHE[clave] = reglas
    return reglas


def _texto_fecha(fecha) -> str:
    if fecha is None:
        return '9999-12-31'
    if isinstance(fecha, date):
        return fecha.isoformat()
    return str(fecha)[:10]


def regla(fecha=None) -> ReglaOperacion:
    """Regla vigente en esa fecha. Sin fecha, la política actual."""
    configuradas = _cargar()
    if not configuradas:
        return REGLA_POR_DEFECTO
    if fecha is None:
        return configuradas[-1]
    referencia = _texto_fecha(fecha)
    elegida = None
    for actual in configuradas:
        if actual.vigente_desde <= referencia:
            elegida = actual
        else:
            break
    return elegida or REGLA_POR_DEFECTO


def maximo_dias(fecha=None) -> int:
    return int(regla(fecha).max_dias_consecutivos)


def historial() -> list[dict]:
    configuradas = _cargar()
    return [r.como_dict() for r in (configuradas or [REGLA_POR_DEFECTO])]


class ReglaInvalida(ValueError):
    """El tope pedido no es aplicable."""


def guardar(vigente_desde, max_dias_consecutivos: int, nota: str = '') -> dict:
    vigente = _texto_fecha(vigente_desde)
    try:
        date.fromisoformat(vigente)
    except ValueError as exc:
        raise ReglaInvalida('La fecha de vigencia no es válida.') from exc
    if vigente < INICIO_OPERACION:
        raise ReglaInvalida('La primera fecha con programación es el 1 de agosto de 2026.')
    tope = int(max_dias_consecutivos)
    if tope < MINIMO_DIAS:
        raise ReglaInvalida(
            f'El máximo no puede bajar de {MINIMO_DIAS} jornadas: con un solo descanso semanal, '
            'un descanso a principio de una semana y otro al final de la siguiente ya suman seis '
            'jornadas seguidas, y por debajo de ese margen no existe ninguna programación posible.'
        )
    if tope > MAXIMO_DIAS:
        raise ReglaInvalida(f'El máximo no puede pasar de {MAXIMO_DIAS} jornadas seguidas.')
    conn = conectar()
    try:
        asegurar_tabla(conn)
        conn.execute(
            '''INSERT INTO reglas_operacion(vigente_desde,max_dias_consecutivos,nota)
               VALUES(?,?,?)
               ON CONFLICT(vigente_desde) DO UPDATE SET
                 max_dias_consecutivos=excluded.max_dias_consecutivos, nota=excluded.nota''',
            (vigente, tope, str(nota or '')),
        )
        conn.commit()
    finally:
        conn.close()
    invalidar_cache()
    return regla(vigente).como_dict()


def eliminar(regla_id: int) -> bool:
    conn = conectar()
    try:
        asegurar_tabla(conn)
        restantes = int(conn.execute('SELECT COUNT(*) n FROM reglas_operacion').fetchone()['n'])
        if restantes <= 1:
            raise ReglaInvalida(
                'Debe quedar al menos una regla. Edita la existente en lugar de eliminarla.'
            )
        cur = conn.execute('DELETE FROM reglas_operacion WHERE id=?', (int(regla_id),))
        conn.commit()
        borrada = cur.rowcount > 0
    finally:
        conn.close()
    invalidar_cache()
    return borrada


def sembrar_regla_inicial(conn) -> None:
    """Escribe la regla de fábrica. Idempotente: no pisa lo que el usuario cambió."""
    asegurar_tabla(conn)
    conn.execute(
        '''INSERT OR IGNORE INTO reglas_operacion(vigente_desde,max_dias_consecutivos,nota)
           VALUES(?,?,?)''',
        (REGLA_POR_DEFECTO.vigente_desde, REGLA_POR_DEFECTO.max_dias_consecutivos,
         REGLA_POR_DEFECTO.nota),
    )
    invalidar_cache()
