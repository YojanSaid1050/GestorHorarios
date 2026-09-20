# -*- coding: utf-8 -*-
"""Quién entra y qué puede hacer.

Dos perfiles, y la diferencia entre ellos es de responsabilidad, no de
confianza: el **operador** lleva la operación diaria entera —personal,
novedades, horarios, publicar— y el **administrador** además puede tocar lo que
afecta a la propia instalación: las cuentas, las copias de seguridad, restaurar
y volver a fábrica.

Tres decisiones que conviene ver escritas:

* **Las contraseñas se guardan derivadas, nunca en claro**, con PBKDF2 y una sal
  distinta por persona. Aunque alguien se lleve el archivo de la base, no se
  lleva las contraseñas.
* **No hay puerta trasera para las pruebas.** La versión anterior tenía una
  variable de entorno que saltaba el acceso; viajaba compilada dentro del
  ejecutable, y ponerla era tan fácil como editar un acceso directo. Con ella,
  cualquiera entraba como administrador y el historial dejaba de significar
  nada. Aquí las pruebas entran como entra todo el mundo.
* **Vaciar el historial es cosa del administrador.** Estaba fuera de la lista y
  era el agujero más incómodo: el operador podía borrar de la única pantalla
  donde se mira el registro de lo que acababa de hacer.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from gestor.datos.base import abierta, transaccion
from gestor.servicios import historial

ADMIN_INICIAL = ('admin', 'Administrador', 'xYojanSaidx1050')
OPERADOR_INICIAL = ('katerine', 'Katerine Manzanares', 'Kate2026*')

HORAS_DE_SESION = 12
VUELTAS = 240_000
LONGITUD_MINIMA = 8

#: Lo que solo puede hacer el administrador. Todo lo demás lo puede hacer quien
#: lleva la operación: si el operador tuviera que pedir permiso para trabajar,
#: acabaría usando la cuenta del administrador para todo y no habría perfiles.
SOLO_ADMINISTRADOR = (
    ('POST', '/api/configuracion/reiniciar-fabrica'),
    ('POST', '/api/operacion/backup'),
    ('POST', '/api/operacion/restore'),
    ('GET', '/api/auth/usuarios'),
    ('POST', '/api/auth/usuarios'),
    ('PUT', '/api/auth/usuarios/'),
    ('DELETE', '/api/operacion/auditoria'),
    ('POST', '/api/actualizaciones/descargar'),
    ('POST', '/api/actualizaciones/instalar'),
)

#: Direcciones que se pueden pedir sin haber entrado. Son las justas para poder
#: enseñar la pantalla de acceso y decir qué versión hay puesta.
SIN_SESION = (
    '/api/salud', '/api/auth/login', '/api/auth/cuentas-login', '/api/auth/session',
)

#: Direcciones que se pueden **leer** sin haber entrado, y solo leer.
#:
#: Son pura apariencia: con qué color y en claro o en oscuro se pinta la
#: aplicación. No dicen nada de la oficina y hacen falta **antes** de entrar,
#: porque la pantalla de acceso se pinta con ellas.
#:
#: Sin esto contestaban 401 y la pantalla de acceso se quedaba sin los colores
#: del tema. En oscuro eso la dejaba con el fondo transparente y la aplicación
#: entera se veía por debajo, borrosa pero legible, sin haber entrado nadie.
#:
#: Solo de lectura, y por eso van aparte: cambiarlos sigue pidiendo sesión.
SIN_SESION_AL_LEER = (
    '/api/configuracion/modo-app', '/api/configuracion/tema-app',
)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _texto(momento: datetime) -> str:
    return momento.replace(microsecond=0).isoformat()


def validar_contrasena(contrasena) -> str:
    texto = '' if contrasena is None else str(contrasena)
    if not texto.strip():
        raise ValueError('Escribe una contraseña.')
    if len(texto) < LONGITUD_MINIMA:
        raise ValueError(
            f'La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres. '
            f'La escrita tiene {len(texto)}.')
    return texto


def _derivar(contrasena: str, sal_hex: Optional[str] = None) -> tuple[str, str]:
    sal = bytes.fromhex(sal_hex) if sal_hex else secrets.token_bytes(16)
    resumen = hashlib.pbkdf2_hmac('sha256', contrasena.encode('utf-8'), sal, VUELTAS)
    return sal.hex(), resumen.hex()


def _coincide(contrasena: str, sal_hex: Optional[str], esperado: Optional[str]) -> bool:
    if not sal_hex or not esperado:
        return False
    _sal, calculado = _derivar(contrasena, sal_hex)
    # Comparación en tiempo constante: comparar con `==` filtra, por lo que
    # tarda, cuántos caracteres iniciales acertó quien lo intenta.
    return hmac.compare_digest(calculado, esperado)


# ------------------------------------------------------------- las cuentas

def asegurar_cuentas_iniciales() -> None:
    """Crea las dos cuentas de fábrica. Nunca pisa una contraseña ya cambiada.

    Nacen **marcadas para cambiar la contraseña**, y hasta que alguien la
    cambie esa cuenta no puede hacer otra cosa.

    Las dos contraseñas de fábrica están escritas aquí arriba, y «aquí arriba»
    es dentro del programa que se instala en la oficina: quien abra el
    ejecutable las lee. Mientras nadie las cambie, cualquiera que llegue a ese
    equipo entra como administrador y puede autorizar un borrado de los que no
    tienen vuelta atrás.

    La marca existía en la tabla desde el principio, viajaba dentro de la
    sesión, y no la ponía nadie ni la miraba nadie. Aquí se pone; en
    `comprobar_permiso` se mira.
    """
    with transaccion() as conexion:
        for (usuario, nombre, contrasena), rol in (
                (ADMIN_INICIAL, 'admin'), (OPERADOR_INICIAL, 'operador')):
            existe = conexion.execute(
                'SELECT 1 FROM usuarios WHERE usuario=?', (usuario,)).fetchone()
            if existe:
                continue
            sal, resumen = _derivar(contrasena)
            conexion.execute(
                'INSERT INTO usuarios(usuario, nombre, rol, password_salt, '
                'password_hash, requiere_cambio_clave) VALUES(?,?,?,?,?,1)',
                (usuario, nombre, rol, sal, resumen))


def marcar_las_claves_de_fabrica_que_siguen_puestas() -> int:
    """Para las instalaciones que ya existen, que es donde está el problema.

    Marcar solo las cuentas nuevas no arregla nada en la oficina, que lleva
    meses funcionando con las dos contraseñas de fábrica porque nunca se le pidió
    otra cosa.

    Se comprueba una a una contra la contraseña conocida. A quien ya la cambió
    no se le toca: su resumen no coincide y se la deja en paz. Devuelve cuántas
    se marcaron, que en un arranque normal es cero.
    """
    marcadas = 0
    with transaccion() as conexion:
        for usuario, _nombre, contrasena in (ADMIN_INICIAL, OPERADOR_INICIAL):
            fila = conexion.execute(
                'SELECT id, password_salt, password_hash, requiere_cambio_clave '
                'FROM usuarios WHERE usuario=?', (usuario,)).fetchone()
            if fila is None or fila['requiere_cambio_clave']:
                continue
            if not _coincide(contrasena, fila['password_salt'], fila['password_hash']):
                continue
            conexion.execute(
                'UPDATE usuarios SET requiere_cambio_clave=1 WHERE id=?',
                (int(fila['id']),))
            marcadas += 1
    return marcadas


def cuentas_para_entrar() -> list[dict]:
    """Los nombres que se ofrecen en la pantalla de acceso.

    Se enseñan los usuarios y no una casilla en blanco porque son tres personas
    en una oficina, no un servicio público: escribir el usuario mal era el
    motivo más común de «no me deja entrar».
    """
    with abierta() as conexion:
        filas = conexion.execute(
            'SELECT usuario, nombre, rol FROM usuarios WHERE activo=1 '
            "ORDER BY CASE rol WHEN 'admin' THEN 0 ELSE 1 END, nombre").fetchall()
    return [dict(f) for f in filas]


def listar_usuarios() -> list[dict]:
    with abierta() as conexion:
        filas = conexion.execute(
            'SELECT id, usuario, nombre, rol, activo, requiere_cambio_clave, creado_en '
            'FROM usuarios ORDER BY nombre').fetchall()
    return [{**dict(f), 'activo': bool(f['activo']),
             'requiere_cambio_clave': bool(f['requiere_cambio_clave'])} for f in filas]


def crear_usuario(usuario: str, nombre: str, rol: str, contrasena: str) -> int:
    if rol not in ('admin', 'operador'):
        raise ValueError('El perfil tiene que ser administrador u operador.')
    usuario = str(usuario or '').strip().lower()
    if not usuario:
        raise ValueError('Escribe un nombre de usuario.')
    sal, resumen = _derivar(validar_contrasena(contrasena))
    with transaccion() as conexion:
        if conexion.execute('SELECT 1 FROM usuarios WHERE usuario=?', (usuario,)).fetchone():
            raise ValueError(f'Ya hay una cuenta con el usuario «{usuario}».')
        cursor = conexion.execute(
            'INSERT INTO usuarios(usuario, nombre, rol, password_salt, password_hash) '
            'VALUES(?,?,?,?,?)', (usuario, str(nombre or usuario).strip(), rol, sal, resumen))
        return int(cursor.lastrowid)


def cambiar_estado(usuario_id: int, activo: bool) -> None:
    """Desactiva o reactiva una cuenta. Nunca deja la instalación sin administrador."""
    with transaccion() as conexion:
        fila = conexion.execute(
            'SELECT rol FROM usuarios WHERE id=?', (int(usuario_id),)).fetchone()
        if fila is None:
            raise ValueError('Esa cuenta ya no existe.')
        if not activo and fila['rol'] == 'admin':
            quedan = conexion.execute(
                "SELECT COUNT(*) n FROM usuarios WHERE rol='admin' AND activo=1 AND id<>?",
                (int(usuario_id),)).fetchone()['n']
            if not quedan:
                raise ValueError(
                    'Es la única cuenta de administrador activa. Si se desactiva, nadie '
                    'podría volver a entrar a la configuración.')
        conexion.execute(
            "UPDATE usuarios SET activo=?, actualizado_en=datetime('now') WHERE id=?",
            (1 if activo else 0, int(usuario_id)))


def cambiar_contrasena(usuario_id: int, nueva: str, actual: Optional[str] = None) -> None:
    with transaccion() as conexion:
        fila = conexion.execute(
            'SELECT * FROM usuarios WHERE id=?', (int(usuario_id),)).fetchone()
        if fila is None:
            raise ValueError('Esa cuenta ya no existe.')
        if actual is not None and not _coincide(actual, fila['password_salt'],
                                                fila['password_hash']):
            raise ValueError('La contraseña actual no es correcta.')
        sal, resumen = _derivar(validar_contrasena(nueva))
        conexion.execute(
            'UPDATE usuarios SET password_salt=?, password_hash=?, '
            "requiere_cambio_clave=0, actualizado_en=datetime('now') WHERE id=?",
            (sal, resumen, int(usuario_id)))
        conexion.execute('DELETE FROM sesiones WHERE usuario_id=?', (int(usuario_id),))


# -------------------------------------------------------------- la sesión

#: Cuántos intentos fallidos seguidos se admiten antes de hacer esperar, y
#: cuánto se espera. Son tres personas en una oficina, no un servicio público:
#: el objetivo no es parar un ataque distribuido, es que probar contraseñas a
#: mano deje de ser gratis.
INTENTOS_ANTES_DE_ESPERAR = 5
SEGUNDOS_DE_ESPERA = 30

#: Por usuario, los fallos seguidos y cuándo fue el último. En memoria y no en
#: la base a propósito: esto se olvida al reiniciar, que es justo lo que se
#: quiere —nadie debe quedarse fuera de su propio programa por un contador que
#: sobrevivió a un apagón— y no ensucia las copias de seguridad.
_fallos_seguidos: dict[str, tuple[int, float]] = {}


def _cuanto_hay_que_esperar(usuario: str) -> int:
    """Segundos que faltan, o cero si se puede intentar ya."""
    cuantos, ultimo = _fallos_seguidos.get(usuario, (0, 0.0))
    if cuantos < INTENTOS_ANTES_DE_ESPERAR:
        return 0
    faltan = SEGUNDOS_DE_ESPERA - (time.monotonic() - ultimo)
    return max(0, int(faltan) + 1) if faltan > 0 else 0


def _apuntar_el_fallo(usuario: str) -> None:
    """Un fallo más para esa cuenta, y la hora en que fue."""
    cuantos, _ = _fallos_seguidos.get(usuario, (0, 0.0))
    _fallos_seguidos[usuario] = (cuantos + 1, time.monotonic())


def olvidar_los_fallos(usuario: str = '') -> None:
    """Borra la cuenta de intentos: de una persona, o de todas.

    La usa el administrador cuando alguien se ha quedado esperando y hay prisa,
    y la usan las pruebas para no arrastrar de una a otra un contador que vive
    en memoria y no en la base.
    """
    nombre = str(usuario or '').strip().lower()
    if nombre:
        _fallos_seguidos.pop(nombre, None)
    else:
        _fallos_seguidos.clear()


def entrar(usuario: str, contrasena: str) -> dict:
    nombre = str(usuario or '').strip().lower()
    espera = _cuanto_hay_que_esperar(nombre)
    if espera:
        raise HTTPException(429, (
            f'Demasiados intentos seguidos. Espera {espera} segundos y vuelve a '
            'probar. Si no recuerdas la contraseña, quien lleve la cuenta de '
            'administrador puede ponerte una nueva.'))
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM usuarios WHERE usuario=? AND activo=1',
            (nombre,)).fetchone()
    # El mismo mensaje para «no existe» y para «la contraseña no es esa»: decir
    # cuál de las dos falló es decirle a quien lo intenta qué usuarios existen.
    if fila is None or not _coincide(str(contrasena or ''), fila['password_salt'],
                                     fila['password_hash']):
        _apuntar_el_fallo(nombre)
        raise HTTPException(401, 'El usuario o la contraseña no son correctos.')
    _fallos_seguidos.pop(nombre, None)

    ficha = secrets.token_urlsafe(32)
    with transaccion() as conexion:
        conexion.execute(
            'INSERT INTO sesiones(token, usuario_id, creado_en, expira_en) VALUES(?,?,?,?)',
            (ficha, int(fila['id']), _texto(_ahora()),
             _texto(_ahora() + timedelta(hours=HORAS_DE_SESION))))
    return {'token': ficha, 'usuario': _publico(fila)}


def salir(ficha: str) -> None:
    with transaccion() as conexion:
        conexion.execute('DELETE FROM sesiones WHERE token=?', (str(ficha or ''),))


def _publico(fila) -> dict:
    return {'id': int(fila['id']), 'usuario': fila['usuario'], 'nombre': fila['nombre'],
            'rol': fila['rol'], 'requiere_cambio_clave': bool(fila['requiere_cambio_clave'])}


def sesion_de(ficha: Optional[str]) -> Optional[dict]:
    if not ficha:
        return None
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT u.*, s.expira_en FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id '
            'WHERE s.token=? AND u.activo=1', (str(ficha),)).fetchone()
    if fila is None:
        return None
    if str(fila['expira_en']) < _texto(_ahora()):
        with transaccion() as conexion:
            conexion.execute('DELETE FROM sesiones WHERE token=?', (str(ficha),))
        return None
    return _publico(fila)


def limpiar_sesiones_caducadas() -> int:
    with transaccion() as conexion:
        cursor = conexion.execute('DELETE FROM sesiones WHERE expira_en < ?',
                                  (_texto(_ahora()),))
        return int(cursor.rowcount or 0)


# ------------------------------------------------------------ los permisos

#: Lo único que puede hacer una cuenta que todavía tiene la contraseña de
#: fábrica: cambiarla, mirar quién es, y salir.
#:
#: Lo demás se le niega, incluido leer. Una contraseña que viene escrita dentro
#: del programa no es una contraseña: es una puerta abierta, y la plantilla de
#: la oficina está detrás.
MIENTRAS_NO_CAMBIE_LA_CLAVE = (
    ('PUT', '/api/auth/password'),
    ('GET', '/api/auth/session'),
    ('POST', '/api/auth/logout'),
)


def puede(usuario: dict, metodo: str, camino: str) -> bool:
    if usuario.get('rol') == 'admin':
        return True
    for metodo_vetado, prefijo in SOLO_ADMINISTRADOR:
        if metodo == metodo_vetado and camino.startswith(prefijo):
            return False
    return True


async def comprobar_permiso(peticion: Request, siguiente):
    """Deja pasar, o contesta por qué no. Se aplica a todo lo que sea `/api/`."""
    camino = peticion.url.path
    if not camino.startswith('/api/') or camino in SIN_SESION:
        return await siguiente(peticion)
    if peticion.method == 'GET' and camino in SIN_SESION_AL_LEER:
        return await siguiente(peticion)

    usuario = sesion_de(peticion.headers.get('X-Session-Token'))
    if usuario is None:
        return JSONResponse(status_code=401,
                            content={'detail': 'Inicia sesión para usar la aplicación.'})
    # Con la contraseña de fábrica todavía puesta, esta cuenta no hace nada más
    # que cambiarla. La marca estaba en la tabla desde el principio y viajaba
    # dentro de la sesión; lo que faltaba era esto, mirarla.
    if usuario.get('requiere_cambio_clave') and (
            peticion.method, camino) not in MIENTRAS_NO_CAMBIE_LA_CLAVE:
        return JSONResponse(status_code=403, content={'detail': (
            'Esta cuenta todavía tiene la contraseña con la que vino el '
            'programa, y esa contraseña está escrita dentro del instalador: la '
            'puede leer cualquiera que lo abra. Cámbiala en Configuración → Mi '
            'contraseña y el resto de la aplicación se desbloquea.')})

    if not puede(usuario, peticion.method, camino):
        return JSONResponse(status_code=403, content={'detail': (
            'Tu perfil no tiene permiso para esto. Pídeselo a quien lleve la '
            'cuenta de administrador.')})
    peticion.state.usuario = usuario
    # Y queda apuntado quién es, para que el historial lo sepa sin tener que
    # arrastrar el nombre por quince funciones.
    #
    # `historial.actor_actual` existía desde el principio, su comentario decía
    # «se pone al entrar por la web», y no lo ponía nadie: todas las anotaciones
    # que no fueran de la pantalla de acceso se guardaban con el autor en
    # blanco. El registro contaba qué pasó y no quién lo hizo, que es justo la
    # mitad por la que se consulta.
    marca = historial.actor_actual.set(_como_actor(usuario))
    try:
        return await siguiente(peticion)
    finally:
        # Se restablece siempre: el contexto se hereda entre tareas, y dejarlo
        # puesto atribuiría a esta persona lo que hiciera la siguiente petición
        # que reutilizara el contexto.
        historial.actor_actual.reset(marca)


def _como_actor(usuario: dict) -> str:
    """Quién, tal y como se lee en el registro: nombre, cuenta y perfil."""
    nombre = str(usuario.get('nombre') or '').strip()
    cuenta = str(usuario.get('usuario') or '').strip()
    rol = str(usuario.get('rol') or '').strip()
    etiqueta = f'{nombre} ({cuenta})' if nombre and cuenta else (nombre or cuenta or '')
    return f'{etiqueta} · {rol}' if etiqueta and rol else etiqueta


def exigir_contrasena_de_administrador(peticion: Request) -> None:
    """Vuelve a pedir la contraseña para lo que no tiene vuelta atrás.

    Restaurar una copia o volver a fábrica no se deshacen. Que la sesión esté
    abierta no basta: el ordenador pudo quedarse sin bloquear, y el coste de
    escribir la contraseña otra vez es cero comparado con el de perder el
    trabajo de tres meses.
    """
    usuario = getattr(peticion.state, 'usuario', None)
    if not usuario:
        raise HTTPException(401, 'Inicia sesión para usar la aplicación.')
    escrita = peticion.headers.get('X-Admin-Password') or ''
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM usuarios WHERE id=?', (int(usuario['id']),)).fetchone()
    if fila is None or not _coincide(escrita, fila['password_salt'], fila['password_hash']):
        raise HTTPException(401, 'La contraseña no es correcta.')


def exigir_contrasena_propia(peticion: Request) -> None:
    """Igual, pero para lo que puede hacer también el operador."""
    usuario = getattr(peticion.state, 'usuario', None)
    if not usuario:
        raise HTTPException(401, 'Inicia sesión para usar la aplicación.')
    escrita = peticion.headers.get('X-User-Password') or ''
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM usuarios WHERE id=?', (int(usuario['id']),)).fetchone()
    if fila is None or not _coincide(escrita, fila['password_salt'], fila['password_hash']):
        raise HTTPException(401, 'La contraseña no es correcta.')
