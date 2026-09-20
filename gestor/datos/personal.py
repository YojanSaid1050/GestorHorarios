# -*- coding: utf-8 -*-
"""Leer y escribir el personal.

Una decisión que se ve aquí y explica media aplicación: **la configuración de
una persona tiene fecha de vigencia**. Cambiar hoy el turno de alguien no puede
reescribir los meses que ya se publicaron con la configuración anterior; lo que
hace es abrir un tramo nuevo desde el lunes que se indique. Por eso además de la
ficha actual hay un historial, y el motor pide siempre «cómo estaba esta persona
en tal fecha».

Sin eso, corregir el turno de una persona en noviembre cambiaba retroactivamente
agosto, septiembre y octubre, y la oficina veía cómo un horario ya repartido
dejaba de coincidir con el papel que tenía en la pared.
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from gestor.datos.base import abierta, transaccion
from gestor.dominio import vigencia
from gestor.dominio.cobertura import a_texto, desde_texto

#: El orden en que se muestran y se recorren. No es capricho: el motor reparte
#: en este orden y, sin un orden estable, dos generaciones del mismo mes con los
#: mismos datos podían salir distintas.
ORDEN = (
    "CASE area WHEN 'gestion_social' THEN 1 WHEN 'atencion_ciudadano' THEN 2 "
    "WHEN 'comunicaciones' THEN 3 ELSE 9 END, orden_rotacion, id"
)

CAMPOS = (
    'nombre', 'cargo', 'area', 'tipo_turno', 'turno_fijo', 'descanso_fijo',
    'pareja_id', 'inicio_rotacion', 'fecha_ancla_rotacion', 'orden_rotacion',
    'exento_especiales', 'es_nuevo', 'cobertura_dias_json', 'activo',
    'alta_desde', 'retirado_desde', 'origen_siembra',
)


def _como_dict(conexion, fila) -> dict:
    persona = dict(fila)
    persona['activo'] = bool(persona.get('activo', 1))
    persona['exento_especiales'] = bool(persona.get('exento_especiales', 0))
    persona['es_nuevo'] = bool(persona.get('es_nuevo', 0))
    # Se guarda como texto y se devuelve como lista, o `None` para «todos los
    # días», que es como lo entiende el resto del programa.
    persona['cobertura_dias'] = desde_texto(persona.pop('cobertura_dias_json', None))
    pareja = None
    if persona.get('pareja_id'):
        encontrada = conexion.execute(
            'SELECT nombre FROM empleados WHERE id=?', (persona['pareja_id'],)).fetchone()
        pareja = encontrada['nombre'] if encontrada else None
    persona['nombre_pareja'] = pareja
    # Nombres con los que el motor pregunta por la vigencia. Se traducen aquí,
    # en el único sitio que lee la tabla, para que el motor no tenga que saber
    # cómo se llaman las columnas.
    persona['vigente_desde'] = persona.get('alta_desde') or '2026-08-01'
    persona['desactivado_en'] = persona.get('retirado_desde') or None
    return persona


def listar(incluir_retirados: bool = False) -> list[dict]:
    """La plantilla. Quien se retira **el mes que viene** todavía está dentro.

    Un retiro se registra con la fecha del último día, y esa fecha suele ser
    futura: se avisa con semanas. `retirar()` marca `activo=0` en el acto —así
    queda escrito que la salida está decidida— pero hasta que llegue el día esa
    persona sigue trabajando, y el horario tiene que contar con ella.

    Sin esta condición desaparecía de golpe. El mes en curso se volvía a generar
    sin ella, con sus turnos repartidos entre los demás, y el motor ni se
    enteraba: él sabe dejarla en NV a partir del día exacto —lo hace bien— pero
    nunca la recibía. Y si además tenía pareja de PC, la pareja se quedaba
    huérfana y el mes salía **vacío**.
    """
    with abierta() as conexion:
        donde = '' if incluir_retirados else (
            "WHERE activo=1 OR (retirado_desde IS NOT NULL "
            "AND retirado_desde > date('now'))")
        filas = conexion.execute(
            f'SELECT * FROM empleados {donde} ORDER BY activo DESC, {ORDEN}').fetchall()
        return [_como_dict(conexion, f) for f in filas]


def para_periodo(inicio: str, fin: str,
                 incluir_retirados: bool = False) -> list[dict]:
    """La plantilla vista **desde** ese periodo, con sus cambios dentro.

    `listar()` devuelve la ficha final de cada persona: cómo está hoy. Para
    armar un mes eso no sirve, y el fallo era silencioso en la peor dirección:
    programar que alguien pasa a rotativo desde el 2 de noviembre y generar
    octubre daba un octubre con esa persona ya rotando. La configuración del
    futuro se aplicaba hacia atrás.

    El motor sabe hacer esto bien desde el principio —`gestor/dominio/vigencia.py`
    y `motor/construccion.py` resuelven la configuración día a día— pero nadie
    le daba nunca los datos: esperaba `config_inicial` y `cambios_config`, y
    recibía la ficha final y nada más. La pieza estaba entera y desconectada.

    Aquí se arma a partir del historial. Cada fila guarda cómo estaba la persona
    **antes** de ese cambio, así que la configuración que deja un cambio es la
    foto del siguiente, y la del último es la ficha de hoy.
    """
    desde, hasta = str(inicio)[:10], str(fin)[:10]
    gente = listar(incluir_retirados=incluir_retirados)
    with abierta() as conexion:
        filas = conexion.execute(
            'SELECT empleado_id, vigente_desde, datos_json FROM empleados_historial '
            'ORDER BY empleado_id, vigente_desde, id').fetchall()
    historial: dict[int, list] = {}
    for fila in filas:
        historial.setdefault(int(fila['empleado_id']), []).append(fila)

    salida = []
    for persona in gente:
        tramos = historial.get(int(persona['id']), [])
        if not tramos:
            salida.append(persona)
            continue
        # Los estados por los que pasó: la foto de cada cambio, y al final la
        # ficha de hoy, que es como quedó después del último.
        estados = [json.loads(f['datos_json'] or '{}') for f in tramos]
        estados.append(persona)
        cambios = [{'desde': str(tramos[i]['vigente_desde'])[:10],
                    'cfg': vigencia.instantanea(estados[i + 1])}
                   for i in range(len(tramos))
                   if str(tramos[i]['vigente_desde'])[:10] <= hasta]
        inicial, posteriores = vigencia.separar_cambios(estados[0], cambios, desde)
        # La configuración de arranque se aplica **encima de la ficha**, no solo
        # se adjunta. `config_en_fecha` solo mira `config_inicial` cuando además
        # hay transiciones dentro del periodo; con un cambio programado para
        # después —el caso del fallo: rotativo desde el 2 de noviembre— no hay
        # ninguna, y el motor se quedaba con la ficha de hoy y rotaba en
        # octubre. Así la ficha que recibe **es** la del periodo, y las
        # transiciones son solo las que ocurren dentro.
        salida.append({**persona, **inicial, 'config_inicial': inicial,
                       'cambios_config': posteriores})
    return salida


def obtener(empleado_id: int) -> Optional[dict]:
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM empleados WHERE id=?', (int(empleado_id),)).fetchone()
        return _como_dict(conexion, fila) if fila else None


def por_origen_siembra(clave: str) -> Optional[dict]:
    """Quién vino de esa fila de la plantilla inicial, se llame hoy como se llame."""
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM empleados WHERE origen_siembra=?', (str(clave),)).fetchone()
        return _como_dict(conexion, fila) if fila else None


def apuntar_el_origen(empleado_id: int, clave: str) -> None:
    """Para las instalaciones que ya existen, donde la columna nació vacía."""
    with transaccion() as conexion:
        conexion.execute(
            'UPDATE empleados SET origen_siembra=? WHERE id=? AND origen_siembra IS NULL',
            (str(clave), int(empleado_id)))


def por_nombre(nombre: str) -> Optional[dict]:
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM empleados WHERE nombre=?', (nombre,)).fetchone()
        return _como_dict(conexion, fila) if fila else None


# ------------------------------------------------------------------ escribir

def _valores(datos: dict) -> dict:
    salida = {c: datos.get(c) for c in CAMPOS}
    if 'cobertura_dias' in datos:
        salida['cobertura_dias_json'] = a_texto(datos.get('cobertura_dias'))
    salida['cobertura_dias_json'] = salida.get('cobertura_dias_json') or ''
    salida['cargo'] = salida.get('cargo') or 'GUÍA SOCIAL'
    salida['orden_rotacion'] = int(salida.get('orden_rotacion') or 0)
    for bandera in ('exento_especiales', 'es_nuevo'):
        salida[bandera] = 1 if salida.get(bandera) else 0
    salida['activo'] = 0 if salida.get('activo') is False else 1
    salida['alta_desde'] = salida.get('alta_desde') or '2026-08-01'
    return salida


def crear(datos: dict) -> int:
    valores = _valores(datos)
    columnas = ', '.join(valores)
    marcas = ', '.join('?' for _ in valores)
    with transaccion() as conexion:
        cursor = conexion.execute(
            f'INSERT INTO empleados({columnas}) VALUES({marcas})', tuple(valores.values()))
        return int(cursor.lastrowid)


def actualizar(empleado_id: int, datos: dict, vigente_desde: Optional[str] = None,
               grupo: Optional[str] = None) -> None:
    """Cambia la ficha. Con `vigente_desde`, abre un tramo nuevo desde esa fecha.

    Guardar el estado anterior **antes** de pisarlo es lo que permite que un mes
    ya publicado se siga leyendo con la configuración que tenía. Es barato y es
    la única forma de que corregir algo hoy no reescriba el pasado.
    """
    with transaccion() as conexion:
        anterior = conexion.execute(
            'SELECT * FROM empleados WHERE id=?', (int(empleado_id),)).fetchone()
        if anterior is None:
            raise ValueError('Esa persona ya no está en la plantilla.')
        if vigente_desde:
            columnas = set(anterior.keys())
            foto = {c: anterior[c] for c in CAMPOS if c in columnas}
            conexion.execute(
                'INSERT INTO empleados_historial(empleado_id, vigente_desde, '
                'datos_json, grupo) VALUES(?,?,?,?)',
                (int(empleado_id), str(vigente_desde),
                 json.dumps(foto, ensure_ascii=False, default=str),
                 str(grupo) if grupo else None))
        campos = dict(_valores({**dict(anterior), **datos}))
        asignaciones = ', '.join(f'{c}=?' for c in campos)
        conexion.execute(f'UPDATE empleados SET {asignaciones} WHERE id=?',
                         (*campos.values(), int(empleado_id)))


def retirar(empleado_id: int, desde: str) -> None:
    """Marca la salida sin borrar nada.

    Borrar a alguien se llevaría por delante su rastro en meses ya publicados.
    Lo que se hace es dejar escrito desde cuándo ya no está: el motor lo verá
    fuera de vigencia a partir de esa fecha y seguirá viéndolo dentro antes.
    """
    with transaccion() as conexion:
        conexion.execute(
            'UPDATE empleados SET activo=0, retirado_desde=? WHERE id=?',
            (str(desde), int(empleado_id)))
        # Y se deshace la pareja de PC, por los dos lados.
        #
        # Sin esto, quien se quedaba apuntando a la persona retirada dejaba una
        # pareja a medias, y la comprobación de parejas la daba por rota: el mes
        # entero salía con **cero filas**, sin una sola persona, y aun así se
        # podía marcar como oficial y publicar. El mes siguiente partía de ese
        # vacío y salía vacío también.
        #
        # Perder la pareja las últimas semanas es un precio pequeño: lo que hace
        # es evitar que dos personas coincidan en el mismo puesto, y sin una de
        # las dos ya no hay nada que evitar.
        conexion.execute(
            'UPDATE empleados SET pareja_id=NULL WHERE pareja_id=? OR id=?',
            (int(empleado_id), int(empleado_id)))


def reactivar(empleado_id: int) -> None:
    with transaccion() as conexion:
        conexion.execute(
            'UPDATE empleados SET activo=1, retirado_desde=NULL WHERE id=?',
            (int(empleado_id),))


def emparejar(uno: int, otro: Optional[int]) -> None:
    """Une o separa una pareja de punto de contacto, siempre por los dos lados.

    Una pareja escrita en un solo sentido es una pareja que el motor ve desde
    una punta y no desde la otra: a una persona le evita coincidir con la otra y
    a la otra no. Aquí no se puede: la reciprocidad la impone esta función.
    """
    with transaccion() as conexion:
        conexion.execute('UPDATE empleados SET pareja_id=NULL WHERE pareja_id=?', (int(uno),))
        if otro is None:
            conexion.execute('UPDATE empleados SET pareja_id=NULL WHERE id=?', (int(uno),))
            return
        conexion.execute('UPDATE empleados SET pareja_id=NULL WHERE pareja_id=?', (int(otro),))
        conexion.execute('UPDATE empleados SET pareja_id=? WHERE id=?', (int(otro), int(uno)))
        conexion.execute('UPDATE empleados SET pareja_id=? WHERE id=?', (int(uno), int(otro)))


# ------------------------------------------------------------- el historial

def configuracion_en(empleado_id: int, fecha: str) -> Optional[dict]:
    """Cómo estaba configurada esa persona en esa fecha."""
    with abierta() as conexion:
        tramo = conexion.execute(
            'SELECT datos_json FROM empleados_historial '
            'WHERE empleado_id=? AND vigente_desde > ? '
            'ORDER BY vigente_desde, id LIMIT 1',
            (int(empleado_id), str(fecha))).fetchone()
        if tramo:
            return json.loads(tramo['datos_json'])
        fila = conexion.execute(
            'SELECT * FROM empleados WHERE id=?', (int(empleado_id),)).fetchone()
        return _como_dict(conexion, fila) if fila else None


def cambios_programados() -> list[dict]:
    with abierta() as conexion:
        nombres = {int(r['id']): r['nombre']
                   for r in conexion.execute('SELECT id, nombre FROM empleados')}
        filas = conexion.execute(
            'SELECT empleado_id, vigente_desde, datos_json FROM empleados_historial '
            'ORDER BY empleado_id, vigente_desde').fetchall()
    return [{
        'empleado_id': int(f['empleado_id']),
        'nombre': nombres.get(int(f['empleado_id']), '—'),
        'vigente_desde': str(f['vigente_desde']),
        'antes': json.loads(f['datos_json']),
    } for f in filas]


def guardar_muchos(personas: Iterable[dict]) -> int:
    """Alta en bloque. Para la siembra inicial."""
    creadas = 0
    for persona in personas:
        crear(persona)
        creadas += 1
    return creadas
