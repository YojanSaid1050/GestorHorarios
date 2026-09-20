# -*- coding: utf-8 -*-
"""Cambiar de turno a alguien desde una fecha, y poder deshacerlo.

Un cambio de turno no es una novedad de un día: cambia la configuración de una
persona **desde un lunes concreto y para siempre**. Por eso vive aquí y no en
las solicitudes.

Tres cosas que este archivo existe para garantizar:

* **Empieza en lunes.** El reparto AM/PM se decide una vez por semana. Un cambio
  que arranque un miércoles parte la semana en dos turnos distintos, que es
  justo lo que la programación por semanas completas evita. La fecha que se pida
  se corre al lunes siguiente y se dice que se ha corrido.
* **La pareja se mueve con ella.** Dos personas emparejadas van siempre en
  turnos contrarios: son la cobertura la una de la otra. Cambiar solo a una las
  dejaría a las dos en el mismo turno, que es exactamente el hueco que la pareja
  existe para tapar.
* **Se puede deshacer.** Antes solo se podía añadir. Quien se equivocaba de
  fecha o de persona no tenía forma de quitarlo: podía programar otro encima,
  pero el equivocado se quedaba para siempre y seguía moviendo el horario de las
  semanas intermedias.

Deshacer no borra historia. Quita ese cambio y deja a la persona con lo que
tenía justo antes, que es lo que significa «esto no llegó a pasar».
"""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

from gestor.datos import personal
from gestor.datos.base import abierta, transaccion

CONTRARIO = {'AM': 'PM', 'PM': 'AM'}

#: Lo que un cambio de turno decide. El resto de la ficha no se toca: cambiar el
#: turno de alguien no es motivo para tocarle el área ni la pareja.
CAMPOS = ('tipo_turno', 'turno_fijo', 'inicio_rotacion', 'fecha_ancla_rotacion',
          'descanso_fijo', 'exento_especiales')


def proximo_lunes(fecha: date) -> date:
    return fecha if fecha.weekday() == 0 else fecha + timedelta(days=7 - fecha.weekday())


def _fecha(texto) -> date:
    try:
        return date.fromisoformat(str(texto)[:10])
    except (TypeError, ValueError):
        raise ValueError(f'«{texto}» no es una fecha válida.') from None


def _configuracion_nueva(persona: dict, pedido: dict, desde: str) -> dict:
    """La ficha que queda, con los campos que ya no significan nada en blanco.

    Dejar `inicio_rotacion` puesto en alguien que pasa a turno fijo es cómo se
    acumulan los datos que se contradicen entre sí: un día alguien lee ese campo
    creyendo que sigue vigente.
    """
    tipo = str(pedido.get('tipo_turno') or persona.get('tipo_turno'))
    nueva = {'tipo_turno': tipo}
    if tipo == 'fijo':
        nueva.update(turno_fijo=pedido.get('turno_fijo'), inicio_rotacion=None,
                     fecha_ancla_rotacion=None, es_nuevo=False)
    elif tipo == 'rotativo':
        # El carrusel arranca justo el lunes del cambio: esa semana la persona
        # trabaja el turno que se eligió como inicio.
        nueva.update(turno_fijo=None, inicio_rotacion=pedido.get('inicio_rotacion'),
                     fecha_ancla_rotacion=desde, es_nuevo=False)
    else:
        nueva.update(turno_fijo=None, inicio_rotacion=None, fecha_ancla_rotacion=None,
                     descanso_fijo=None, exento_especiales=True)
    if 'descanso_fijo' in pedido and tipo != 'administrativo':
        nueva['descanso_fijo'] = pedido['descanso_fijo']
    return nueva


def _espejo(configuracion: dict, pareja: dict) -> dict:
    """La misma configuración, en el turno contrario."""
    espejo = dict(configuracion)
    if configuracion['tipo_turno'] == 'fijo':
        espejo['turno_fijo'] = CONTRARIO.get(str(configuracion.get('turno_fijo') or ''))
    elif configuracion['tipo_turno'] == 'rotativo':
        espejo['inicio_rotacion'] = CONTRARIO.get(str(configuracion.get('inicio_rotacion') or ''))
    espejo['descanso_fijo'] = configuracion.get('descanso_fijo', pareja.get('descanso_fijo'))
    return espejo


def _validar(pedido: dict) -> None:
    tipo = pedido.get('tipo_turno')
    if tipo not in ('fijo', 'rotativo', 'administrativo'):
        raise ValueError('El tipo de turno tiene que ser fijo, rotativo o administrativo.')
    if tipo == 'fijo' and pedido.get('turno_fijo') not in ('AM', 'PM'):
        raise ValueError('Un cambio a turno fijo necesita saber si es de mañana o de tarde.')
    if tipo == 'rotativo' and pedido.get('inicio_rotacion') not in ('AM', 'PM'):
        raise ValueError('Un cambio a rotativo necesita saber con qué turno empieza.')


def programar(empleado_id: int, pedido: dict) -> dict:
    """Aplica el cambio a la persona y, si procede, a su pareja."""
    _validar(pedido)
    persona = personal.obtener(empleado_id)
    if persona is None:
        raise ValueError('Esa persona ya no está en la plantilla.')
    if not persona.get('activo', True):
        raise ValueError(
            f'{persona["nombre"]} está retirada. Reactívala antes de cambiarle el turno.')

    pedida = _fecha(pedido.get('vigente_desde'))
    alta = _fecha(persona.get('alta_desde') or '2026-08-01')
    if pedida < alta:
        raise ValueError(
            f'El cambio no puede empezar antes del {alta.isoformat()}, que es desde cuándo '
            f'{persona["nombre"]} está en la plantilla.')
    lunes = proximo_lunes(pedida)
    desde = lunes.isoformat()

    nueva = _configuracion_nueva(persona, pedido, desde)
    if all(persona.get(campo) == valor for campo, valor in nueva.items()):
        raise ValueError(
            f'{persona["nombre"]} ya está así. El cambio no dejaría nada distinto.')

    # Quiénes cambian juntos queda escrito **ahora**, con el cambio, y no se
    # deduce después preguntando por la pareja de hoy: la pareja de hoy puede no
    # ser la de entonces, y deshacer el cambio le tocaba el turno a alguien que
    # nunca estuvo en él.
    grupo = uuid.uuid4().hex[:12]
    nombres = [persona['nombre']]
    personal.actualizar(empleado_id, nueva, vigente_desde=desde, grupo=grupo)

    pareja_id = persona.get('pareja_id')
    mueve_la_pareja = (pedido.get('aplicar_a_pareja', True) and pareja_id
                       and nueva['tipo_turno'] != 'administrativo')
    if mueve_la_pareja:
        pareja = personal.obtener(int(pareja_id))
        if pareja and pareja.get('activo', True):
            personal.actualizar(int(pareja_id), _espejo(nueva, pareja),
                                vigente_desde=desde, grupo=grupo)
            nombres.append(pareja['nombre'])

    etiqueta = {'fijo': f'turno fijo {nueva.get("turno_fijo") or ""}'.strip(),
                'rotativo': 'rotativo', 'administrativo': 'administrativo'}[nueva['tipo_turno']]
    aviso = (f' La fecha se ajustó al lunes {desde} para no partir la semana.'
             if lunes != pedida else '')
    return {
        'vigente_desde': desde,
        'ajustada_a_lunes': lunes != pedida,
        'afectados': nombres,
        'area': persona['area'],
        'mensaje': (f'{" y ".join(nombres)} pasa{"n" if len(nombres) > 1 else ""} a '
                    f'{etiqueta} desde el {desde}.' + aviso),
    }


def _cadena(conexion, empleado_id: int) -> tuple[list, list[dict]]:
    """La vida de esa ficha, en orden: las filas y un estado por tramo.

    Cada fila del historial guarda cómo estaba la persona **antes** de ese
    cambio. Los estados son, entonces, esas fotos en orden y al final la ficha
    de hoy, que es cómo quedó después del último cambio. Con `n` cambios hay
    `n + 1` estados.
    """
    filas = conexion.execute(
        'SELECT id, vigente_desde, datos_json, grupo FROM empleados_historial '
        'WHERE empleado_id=? ORDER BY vigente_desde, id',
        (int(empleado_id),)).fetchall()
    actual = conexion.execute(
        'SELECT * FROM empleados WHERE id=?', (int(empleado_id),)).fetchone()
    if actual is None:
        return [], []
    estados = [json.loads(f['datos_json'] or '{}') for f in filas]
    columnas = set(actual.keys())
    estados.append({c: actual[c] for c in CAMPOS if c in columnas})
    return list(filas), estados


def _rehacer_sin(conexion, empleado_id: int, quitar_id: int) -> None:
    """Quita un cambio de la cadena y vuelve a montar lo que venía después.

    Deshacer restauraba la foto de antes sobre la ficha y borraba la fila. Con
    un cambio posterior ya programado eso era mentira: cancelar el de octubre
    devolvía a la persona a lo que tenía en septiembre, aunque el cambio de
    noviembre siguiera guardado y siguiera figurando en la lista. La línea de
    cambios y el estado que usa la aplicación dejaban de coincidir.

    Lo que se hace es reconstruir. Cada cambio aporta lo que **dejó distinto**
    respecto del tramo anterior, y eso se saca comparando dos fotos
    consecutivas. Se quita el que sobra y se vuelven a aplicar los demás, en
    orden, sobre el estado en el que la persona queda.

    Cuando el que se quita es el último no hay nada que recomponer y todo
    funciona igual que antes, que es el caso normal.
    """
    filas, estados = _cadena(conexion, empleado_id)
    posicion = next((i for i, f in enumerate(filas)
                     if int(f['id']) == int(quitar_id)), None)
    if posicion is None:
        return

    saltos = [{c: estados[i + 1].get(c) for c in CAMPOS
               if estados[i + 1].get(c) != estados[i].get(c)}
              for i in range(len(estados) - 1)]

    estado = dict(estados[posicion])
    for i in range(posicion + 1, len(filas)):
        # La foto de ese tramo pasa a ser el estado desde el que ahora arranca.
        conexion.execute(
            'UPDATE empleados_historial SET datos_json=? WHERE id=?',
            (json.dumps(estado, ensure_ascii=False, default=str),
             int(filas[i]['id'])))
        estado = {**estado, **saltos[i]}

    conexion.execute('DELETE FROM empleados_historial WHERE id=?',
                     (int(quitar_id),))
    campos = {c: v for c, v in estado.items() if c in CAMPOS}
    if campos:
        asignaciones = ', '.join(f'{c}=?' for c in campos)
        conexion.execute(f'UPDATE empleados SET {asignaciones} WHERE id=?',
                         (*campos.values(), int(empleado_id)))


def deshacer(empleado_id: int, vigente_desde: str, incluir_pareja: bool = True) -> dict:
    """Quita ese cambio y recompone lo que viniera después.

    «Deshacer» significa «esto no llegó a pasar», no «vuelve a como estabas en
    aquel momento». La diferencia solo se nota cuando hay un cambio posterior
    programado, y entonces se nota mucho: cancelar el de octubre devolvía a la
    persona a lo de septiembre y el de noviembre se quedaba en la lista sin
    efecto ninguno.

    La pareja se deshace con ella cuando cambió en el mismo acto: cambian juntas
    y en turnos contrarios, así que quitar solo una las dejaría a las dos en el
    mismo turno. Quién cambió con quién está escrito en el propio cambio; en los
    guardados antes de que esa columna existiera se recurre a la pareja de hoy
    con la misma fecha, que es lo que se hacía siempre.
    """
    fecha = _fecha(vigente_desde).isoformat()
    persona = personal.obtener(empleado_id)
    if persona is None:
        raise ValueError('Esa persona ya no está en la plantilla.')

    deshechos: list[str] = []
    with transaccion() as conexion:
        mia = conexion.execute(
            'SELECT id, grupo FROM empleados_historial '
            'WHERE empleado_id=? AND vigente_desde=? ORDER BY id DESC LIMIT 1',
            (int(empleado_id), fecha)).fetchone()
        if mia is None:
            raise ValueError(
                'No hay ningún cambio de turno guardado con fecha '
                f'{fecha} para esta persona.')

        a_quitar = [(int(empleado_id), int(mia['id']))]
        if incluir_pareja:
            if mia['grupo']:
                companeros = conexion.execute(
                    'SELECT id, empleado_id FROM empleados_historial '
                    'WHERE grupo=? AND empleado_id<>?',
                    (str(mia['grupo']), int(empleado_id))).fetchall()
            else:
                pareja_id = persona.get('pareja_id')
                companeros = conexion.execute(
                    'SELECT id, empleado_id FROM empleados_historial '
                    'WHERE empleado_id=? AND vigente_desde=?',
                    (int(pareja_id), fecha)).fetchall() if pareja_id else []
            a_quitar += [(int(f['empleado_id']), int(f['id'])) for f in companeros]

        for eid, fila_id in a_quitar:
            _rehacer_sin(conexion, eid, fila_id)
            nombre = conexion.execute(
                'SELECT nombre FROM empleados WHERE id=?', (eid,)).fetchone()
            deshechos.append(str(nombre['nombre']) if nombre else str(eid))

    plural = 'n' if len(deshechos) > 1 else ''
    return {
        'deshechos': deshechos,
        'area': persona['area'],
        'vigente_desde': fecha,
        'mensaje': (f'Se deshizo el cambio del {fecha}: {" y ".join(deshechos)} '
                    f'vuelve{plural} a la configuración que tenía{plural} antes.'),
    }


def corregir(empleado_id: int, vigente_desde_anterior: str, pedido: dict) -> dict:
    """Cambiar la fecha o el turno de un cambio ya programado, de una vez.

    O no cambiar nada. Antes esto deshacía primero y programaba después, y si lo
    segundo fallaba —un turno de inicio inválido bastaba— el cambio original ya
    se había perdido: el error se contaba honestamente, pero el dato no volvía.
    Una operación que falla no puede dejar rastro.

    Se copia el estado de las personas que toca y sus filas de historial, se
    intenta, y si algo sale mal se vuelve a poner exactamente como estaba.
    """
    _validar(pedido)
    copia = _copia_de_seguridad([int(empleado_id)] + _acompanantes(
        int(empleado_id), _fecha(vigente_desde_anterior).isoformat()))
    antes = deshacer(empleado_id, vigente_desde_anterior)
    try:
        resultado = programar(empleado_id, pedido)
    except Exception as fallo:                                     # noqa: BLE001
        _restaurar(copia)
        raise ValueError(
            f'No se pudo aplicar la corrección, así que no se ha tocado nada: '
            f'{fallo}') from None
    resultado['anterior'] = antes['vigente_desde']
    resultado['mensaje'] = f'Cambio corregido. {resultado["mensaje"]}'
    return resultado


def _acompanantes(empleado_id: int, fecha: str) -> list[int]:
    """Quién más cambió en ese mismo acto, para copiarlo también."""
    with abierta() as conexion:
        mia = conexion.execute(
            'SELECT grupo FROM empleados_historial '
            'WHERE empleado_id=? AND vigente_desde=? ORDER BY id DESC LIMIT 1',
            (int(empleado_id), fecha)).fetchone()
        if mia is None:
            return []
        if mia['grupo']:
            filas = conexion.execute(
                'SELECT DISTINCT empleado_id FROM empleados_historial '
                'WHERE grupo=? AND empleado_id<>?',
                (str(mia['grupo']), int(empleado_id))).fetchall()
        else:
            filas = conexion.execute(
                'SELECT DISTINCT empleado_id FROM empleados_historial '
                'WHERE vigente_desde=? AND empleado_id<>?',
                (fecha, int(empleado_id))).fetchall()
    return [int(f['empleado_id']) for f in filas]


def _copia_de_seguridad(ids: list[int]) -> dict:
    """La ficha y el historial de esas personas, tal y como están ahora."""
    unicos = sorted({int(i) for i in ids})
    marcas = ', '.join('?' for _ in unicos)
    with abierta() as conexion:
        fichas = [dict(f) for f in conexion.execute(
            f'SELECT * FROM empleados WHERE id IN ({marcas})', unicos)]
        historial = [dict(f) for f in conexion.execute(
            f'SELECT * FROM empleados_historial WHERE empleado_id IN ({marcas})',
            unicos)]
    return {'ids': unicos, 'fichas': fichas, 'historial': historial}


def _restaurar(copia: dict) -> None:
    unicos = copia['ids']
    if not unicos:
        return
    marcas = ', '.join('?' for _ in unicos)
    with transaccion() as conexion:
        for ficha in copia['fichas']:
            campos = {c: v for c, v in ficha.items() if c != 'id'}
            asignaciones = ', '.join(f'{c}=?' for c in campos)
            conexion.execute(f'UPDATE empleados SET {asignaciones} WHERE id=?',
                             (*campos.values(), int(ficha['id'])))
        conexion.execute(
            f'DELETE FROM empleados_historial WHERE empleado_id IN ({marcas})', unicos)
        for fila in copia['historial']:
            columnas = ', '.join(fila)
            valores = ', '.join('?' for _ in fila)
            conexion.execute(
                f'INSERT INTO empleados_historial({columnas}) VALUES({valores})',
                tuple(fila.values()))


# ------------------------------------------------------------------ listar

def _lectura(configuracion: dict) -> str:
    tipo = str(configuracion.get('tipo_turno') or '')
    if tipo == 'administrativo':
        return 'Administrativo'
    if tipo == 'fijo':
        return f'Turno fijo {configuracion.get("turno_fijo") or ""}'.strip()
    if tipo == 'rotativo':
        inicio = configuracion.get('inicio_rotacion')
        return f'Rotativo, empieza en {inicio}' if inicio else 'Rotativo'
    return tipo or '—'


def programados() -> list[dict]:
    """Los cambios guardados, con lo que había antes y lo que hay después.

    El «después» de un tramo es el «antes» del siguiente, y el del último es la
    ficha actual. Calcularlo aquí y no en la pantalla evita que dos pantallas
    distintas lo cuenten de dos maneras distintas.
    """
    with abierta() as conexion:
        actuales = {int(f['id']): dict(f) for f in conexion.execute(
            'SELECT * FROM empleados')}
        filas = [dict(f) for f in conexion.execute(
            'SELECT empleado_id, vigente_desde, datos_json FROM empleados_historial '
            'ORDER BY empleado_id, vigente_desde, id')]

    por_persona: dict[int, list[dict]] = {}
    for fila in filas:
        try:
            configuracion = json.loads(fila['datos_json'] or '{}')
        except (TypeError, ValueError):
            continue
        por_persona.setdefault(int(fila['empleado_id']), []).append(
            {'desde': str(fila['vigente_desde'])[:10], 'cfg': configuracion})

    salida = []
    for eid, tramos in por_persona.items():
        persona = actuales.get(eid) or {}
        for numero, tramo in enumerate(tramos):
            siguiente = tramos[numero + 1]['cfg'] if numero + 1 < len(tramos) else persona
            if all(tramo['cfg'].get(c) == siguiente.get(c)
                   for c in ('tipo_turno', 'turno_fijo', 'inicio_rotacion')):
                # No es un cambio de turno: es una edición de otra cosa de la
                # ficha que también dejó su foto. No tiene nada que enseñar aquí.
                continue
            salida.append({
                'empleado_id': eid,
                'empleado_nombre': persona.get('nombre', '—'),
                'vigente_desde': tramo['desde'],
                'antes': _lectura(tramo['cfg']),
                'despues': _lectura(siguiente),
                'lunes_referencia': siguiente.get('fecha_ancla_rotacion'),
                # No son adorno: con esto la pantalla puede volver a abrir el
                # formulario y corregir la fecha sin obligar a deshacer y crear
                # el cambio otra vez a mano.
                'tipo_turno': siguiente.get('tipo_turno'),
                'turno_fijo': siguiente.get('turno_fijo'),
                'inicio_rotacion': siguiente.get('inicio_rotacion'),
                'descanso_fijo': siguiente.get('descanso_fijo'),
            })
    salida.sort(key=lambda x: (x['vigente_desde'], x['empleado_nombre']))
    return salida


# ------------------------------------------------------- borrar un alta mala

def borrar_definitivo(empleado_id: int) -> dict:
    """Borra un registro creado por error. Solo si no dejó rastro real.

    Retirar es lo correcto para alguien que sí trabajó: su nombre tiene que
    seguir apareciendo en los meses que ya se repartieron. Esto es para el alta
    equivocada que se creó hace cinco minutos, y por eso comprueba antes que no
    haya nada colgando de ella.
    """
    persona = personal.obtener(empleado_id)
    if persona is None:
        raise ValueError('Esa persona ya no está en la plantilla.')

    with abierta() as conexion:
        cuentas = {
            'tiene solicitudes o figura como reemplazo': conexion.execute(
                'SELECT COUNT(*) n FROM solicitudes WHERE empleado_id=? OR '
                'reemplazo_empleado_id=? OR intercambio_empleado_id=?',
                (empleado_id, empleado_id, empleado_id)).fetchone()['n'],
            'tiene asignaciones': conexion.execute(
                'SELECT COUNT(*) n FROM asignaciones WHERE empleado_id=? OR '
                'reemplazo_empleado_id=?', (empleado_id, empleado_id)).fetchone()['n'],
            'tiene cambios manuales guardados': conexion.execute(
                'SELECT COUNT(*) n FROM ajustes_manuales WHERE empleado_id=?',
                (empleado_id,)).fetchone()['n'],
        }
        # El cursor se cierra siempre, también al encontrarlo a la primera.
        #
        # Antes esto era un `for` sobre `conexion.execute(...)` con un `break`
        # dentro, y salir así deja la consulta **a medias**: para SQLite sigue
        # habiendo una lectura en curso, con su candado puesto, hasta que alguien
        # cierre la conexión. Cualquier cosa que necesitara un candado más fuerte
        # se quedaba esperando detrás, sin error y sin mensaje.
        aparece = False
        cursor = conexion.execute(
            'SELECT datos_json FROM horarios WHERE oficial=1 OR publicado=1')
        try:
            for fila in cursor:
                try:
                    datos = json.loads(fila['datos_json'] or '{}')
                except (TypeError, ValueError):
                    continue
                if any(int(f.get('empleado_id') or 0) == int(empleado_id)
                       for f in datos.get('horario') or []):
                    aparece = True
                    break
        finally:
            cursor.close()

    bloqueos = [motivo for motivo, cuantos in cuentas.items() if cuantos]
    if aparece:
        bloqueos.insert(0, 'aparece en un horario oficial o publicado')
    if bloqueos:
        raise ValueError(
            f'No se puede borrar a {persona["nombre"]} porque {"; ".join(bloqueos)}. '
            'Usa Retirar: así deja de entrar en los horarios nuevos y se conserva '
            'su rastro en los que ya se repartieron.')

    with transaccion() as conexion:
        conexion.execute('UPDATE empleados SET pareja_id=NULL WHERE pareja_id=?',
                         (int(empleado_id),))
        conexion.execute('DELETE FROM empleados WHERE id=?', (int(empleado_id),))
    return {
        'nombre': persona['nombre'], 'area': persona['area'],
        'mensaje': (f'Se eliminó el registro de {persona["nombre"]}. No tenía historial, '
                    'así que no se pierde nada.'),
    }
