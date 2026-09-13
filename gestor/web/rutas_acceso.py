# -*- coding: utf-8 -*-
"""Entrar, salir y administrar las cuentas.

Los nombres de los campos —`actual`, `nueva`, `nueva_password`— no son los que
se elegirían de cero: son los que la pantalla lleva enviando desde siempre. Se
respetan a propósito. Cambiarlos aquí obligaría a tocar la pantalla en catorce
sitios para no ganar nada, y ese es exactamente el tipo de cambio que dejó la
versión anterior llena de piezas que ya no encajaban entre sí.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from gestor.servicios import acceso, historial

router = APIRouter(prefix='/api/auth', tags=['acceso'])


class Credenciales(BaseModel):
    usuario: str
    password: str


class CuentaNueva(BaseModel):
    usuario: str
    nombre: str
    password: str
    rol: str = 'operador'


class ClavePropia(BaseModel):
    actual: str
    nueva: str


class ClaveDeOtro(BaseModel):
    nueva_password: str


class Estado(BaseModel):
    activo: bool


def _quien(peticion: Request) -> dict:
    usuario = getattr(peticion.state, 'usuario', None)
    if not usuario:
        raise HTTPException(401, 'Inicia sesión para usar la aplicación.')
    return usuario


def _ficha(usuario_id: int) -> dict:
    cuenta = next((u for u in acceso.listar_usuarios() if u['id'] == int(usuario_id)), None)
    if cuenta is None:
        raise ValueError('Esa cuenta ya no existe.')
    return cuenta


@router.get('/cuentas-login')
def cuentas_disponibles():
    return {'ok': True, 'cuentas': acceso.cuentas_para_entrar()}


@router.post('/login')
def entrar(credenciales: Credenciales):
    datos = acceso.entrar(credenciales.usuario, credenciales.password)
    historial.anotar('inicio_sesion', 'seguridad',
                     {'usuario': datos['usuario']['nombre']})
    return {'ok': True, **datos}


@router.post('/logout')
def salir(peticion: Request):
    acceso.salir(peticion.headers.get('X-Session-Token') or '')
    return {'ok': True, 'mensaje': 'Sesión cerrada.'}


@router.get('/session')
def quien_soy(peticion: Request):
    usuario = acceso.sesion_de(peticion.headers.get('X-Session-Token'))
    return {'ok': bool(usuario), 'usuario': usuario}


@router.put('/password')
def cambiar_mi_clave(datos: ClavePropia, peticion: Request):
    """Cambiar la propia contraseña exige escribir la actual.

    Es lo que evita que alguien que se encuentre un ordenador desbloqueado deje
    a su dueño fuera de su propia cuenta.
    """
    usuario = _quien(peticion)
    acceso.cambiar_contrasena(usuario['id'], datos.nueva, datos.actual)
    historial.anotar('cambiar_clave_propia', 'seguridad',
                     {'usuario': usuario['nombre']})
    return {'ok': True, 'usuario': usuario, 'mensaje': (
        'Tu contraseña quedó actualizada. Vuelve a entrar con la nueva.')}


@router.get('/usuarios')
def listar():
    return {'ok': True, 'usuarios': acceso.listar_usuarios()}


@router.post('/usuarios')
def crear(cuenta: CuentaNueva, peticion: Request):
    identificador = acceso.crear_usuario(cuenta.usuario, cuenta.nombre,
                                         cuenta.rol, cuenta.password)
    ficha = _ficha(identificador)
    historial.anotar('crear_usuario', 'seguridad', {
        'usuario': ficha['nombre'], 'por': _quien(peticion)['nombre']})
    return {'ok': True, 'id': identificador, 'usuario': ficha,
            'mensaje': f'La cuenta de {ficha["nombre"]} quedó creada.'}


@router.put('/usuarios/{usuario_id}/estado')
def activar_o_desactivar(usuario_id: int, estado: Estado, peticion: Request):
    acceso.cambiar_estado(usuario_id, estado.activo)
    ficha = _ficha(usuario_id)
    historial.anotar('estado_usuario', 'seguridad', {
        'usuario': ficha['nombre'], 'activo': ficha['activo'],
        'por': _quien(peticion)['nombre']})
    return {'ok': True, 'usuario': ficha, 'mensaje': (
        f'{ficha["nombre"]} queda {"activo" if ficha["activo"] else "desactivado"}.')}


@router.put('/usuarios/{usuario_id}/password')
def poner_clave(usuario_id: int, datos: ClaveDeOtro, peticion: Request):
    """El administrador puede poner una contraseña sin saber la anterior.

    Es para cuando alguien la olvida. Se anota en el historial, como todo lo que
    afecta a otra persona.
    """
    acceso.cambiar_contrasena(usuario_id, datos.nueva_password)
    ficha = _ficha(usuario_id)
    historial.anotar('cambiar_clave_usuario', 'seguridad', {
        'usuario': ficha['nombre'], 'por': _quien(peticion)['nombre']})
    return {'ok': True, 'usuario': ficha, 'mensaje': (
        f'La contraseña de {ficha["nombre"]} quedó actualizada.')}
