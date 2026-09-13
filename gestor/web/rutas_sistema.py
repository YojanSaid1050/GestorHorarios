# -*- coding: utf-8 -*-
"""Lo que la aplicación cuenta de sí misma: salud, versión y actualizaciones."""
from __future__ import annotations

from fastapi import APIRouter, Request

from gestor import rutas as rutas_app
from gestor import version
from gestor.servicios.acceso import exigir_contrasena_de_administrador
from gestor.servicios.actualizaciones import actualizaciones

router = APIRouter(prefix='/api', tags=['sistema'])


@router.get('/salud')
def salud():
    """¿Está viva, qué versión es y le falta algo para trabajar?

    Es lo primero que carga la pantalla y lo primero que se pregunta cuando
    alguien llama diciendo que «no funciona». Por eso incluye los problemas de
    arranque: si a la instalación le falta un archivo, se dice aquí en vez de
    dejar que el mes salga vacío y en silencio.
    """
    from gestor.web.aplicacion import problemas_de_arranque

    return {
        'ok': not problemas_de_arranque,
        'version': version.VERSION,
        'edicion': version.como_dict(),
        'problemas': list(problemas_de_arranque),
    }


@router.get('/configuracion/rutas')
def donde_esta_todo():
    """Dónde vive el programa y dónde viven los datos.

    Se enseña en pantalla a propósito. Es la diferencia que hace que actualizar
    no borre el trabajo, y la que hay que poder mirar cuando alguien pregunta
    dónde está la base de datos para copiarla.
    """
    return rutas_app.como_dict()


@router.get('/actualizaciones')
def hay_version_nueva(forzar: bool = False):
    """Inofensivo: pregunta y no descarga nada.

    Si no hay internet contesta igual, con el motivo escrito. Quien llame a esto
    no tiene que preocuparse de que falle.
    """
    return {'ok': True, **actualizaciones.consultar(forzar=forzar).como_dict()}


@router.post('/actualizaciones/descargar')
def descargar_version_nueva(peticion: Request):
    exigir_contrasena_de_administrador(peticion)
    return actualizaciones.descargar()


@router.post('/actualizaciones/instalar')
def instalar_version_nueva(peticion: Request):
    """Aplica lo descargado y reinicia. Esta llamada puede no llegar a contestar.

    Es lo esperado: el instalador cierra el proceso para cambiar la carpeta
    activa y lo vuelve a abrir. Por eso la pantalla avisa antes.
    """
    exigir_contrasena_de_administrador(peticion)
    return actualizaciones.instalar()
