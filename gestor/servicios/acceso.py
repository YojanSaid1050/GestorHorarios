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
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from gestor.datos.base import abierta, transaccion

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
    """Crea las dos cuentas de fábrica. Nunca pisa una contraseña ya cambiada."""
    with transaccion() as conexion:
        for (usuario, nombre, contrasena), rol in (
                (ADMIN_INICIAL, 'admin'), (OPERADOR_INICIAL, 'operador')):
            existe = conexion.execute(
                'SELECT 1 FROM usuarios WHERE usuario=?', (usuario,)).fetchone()
            if existe:
                continue
            sal, resumen = _derivar(contrasena)
            conexion.execute(
                'INSERT INTO usuarios(usuario, nombre, rol, password_salt, password_hash) '
                'VALUES(?,?,?,?,?)', (usuario, nombre, rol, sal, resumen))


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

def entrar(usuario: str, contrasena: str) -> dict:
    with abierta() as conexion:
        fila = conexion.execute(
            'SELECT * FROM usuarios WHERE usuario=? AND activo=1',
            (str(usuario or '').strip().lower(),)).fetchone()
    # El mismo mensaje para «no existe» y para «la contraseña no es esa»: decir
    # cuál de las dos falló es decirle a quien lo intenta qué usuarios existen.
    if fila is None or not _coincide(str(contrasena or ''), fila['password_salt'],
                                     fila['password_hash']):
        raise HTTPException(401, 'El usuario o la contraseña no son correctos.')

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

    usuario = sesion_de(peticion.headers.get('X-Session-Token'))
    if usuario is None:
        return JSONResponse(status_code=401,
                            content={'detail': 'Inicia sesión para usar la aplicación.'})
    if not puede(usuario, peticion.method, camino):
        return JSONResponse(status_code=403, content={'detail': (
            'Tu perfil no tiene permiso para esto. Pídeselo a quien lleve la '
            'cuenta de administrador.')})
    peticion.state.usuario = usuario
    return await siguiente(peticion)


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
