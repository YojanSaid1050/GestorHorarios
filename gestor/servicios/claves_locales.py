"""Recuerdo opcional en el Administrador de credenciales del usuario de Windows.

No escribe claves en SQLite, registros ni archivos de la aplicación. Cada carpeta
de datos tiene un ámbito distinto, para aislar pruebas y restauraciones paralelas.
"""
from __future__ import annotations

import ctypes
import hashlib
import sys
from ctypes import wintypes

from gestor import rutas

GENERICA = 1
PERSISTIR_EN_ESTE_EQUIPO = 2
NO_ENCONTRADA = 1168


class Credencial(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD), ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR), ('Comment', wintypes.LPWSTR),
        ('LastWritten', wintypes.FILETIME), ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)), ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
        ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR),
    ]


def _destino(usuario: str) -> str:
    if not isinstance(usuario, str) or not usuario or len(usuario) > 100:
        raise ValueError('La cuenta no es válida.')
    ambito = str(rutas.RAIZ_DATOS.resolve()).casefold() + '\0' + usuario.casefold()
    return 'GestorHorarios/' + hashlib.sha256(ambito.encode()).hexdigest()


def _sistema():
    if sys.platform != 'win32':
        raise OSError('Recordar contraseñas requiere Windows.')
    api = ctypes.WinDLL('advapi32', use_last_error=True)
    puntero = ctypes.POINTER(Credencial)
    api.CredWriteW.argtypes = [puntero, wintypes.DWORD]
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                            ctypes.POINTER(puntero)]
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    for nombre in ('CredWriteW', 'CredReadW', 'CredDeleteW'):
        getattr(api, nombre).restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return api


def guardar(usuario: str, password: str) -> dict:
    try:
        destino = _destino(usuario)
        crudo = password.encode('utf-16-le')
        if not crudo or len(crudo) > 2560:
            raise ValueError('La contraseña supera el tamaño admitido para recordarla.')
        memoria = (ctypes.c_ubyte * len(crudo)).from_buffer_copy(crudo)
        credencial = Credencial(Type=GENERICA, TargetName=destino,
                                CredentialBlobSize=len(crudo), CredentialBlob=memoria,
                                Persist=PERSISTIR_EN_ESTE_EQUIPO, UserName=usuario)
        if not _sistema().CredWriteW(ctypes.byref(credencial), 0):
            raise OSError('Windows no pudo guardar la contraseña.')
        return {'ok': True}
    except (OSError, ValueError, AttributeError, UnicodeError) as error:
        return {'ok': False, 'error': str(error)}


def leer(usuario: str) -> dict:
    try:
        destino = _destino(usuario)
        api = _sistema()
        credencial = ctypes.POINTER(Credencial)()
        if not api.CredReadW(destino, GENERICA, 0, ctypes.byref(credencial)):
            if ctypes.get_last_error() == NO_ENCONTRADA:
                return {'ok': True, 'recordada': False}
            raise OSError('Windows no pudo leer la contraseña recordada.')
        try:
            valor = credencial.contents
            password = ctypes.string_at(valor.CredentialBlob,
                                        valor.CredentialBlobSize).decode('utf-16-le')
            return {'ok': True, 'recordada': True, 'password': password}
        finally:
            api.CredFree(credencial)
    except (OSError, ValueError, UnicodeError) as error:
        return {'ok': False, 'recordada': False, 'error': str(error)}


def olvidar(usuario: str) -> dict:
    try:
        destino = _destino(usuario)
        if (not _sistema().CredDeleteW(destino, GENERICA, 0)
                and ctypes.get_last_error() != NO_ENCONTRADA):
            raise OSError('Windows no pudo borrar la contraseña recordada.')
        return {'ok': True}
    except (OSError, ValueError) as error:
        return {'ok': False, 'error': str(error)}
