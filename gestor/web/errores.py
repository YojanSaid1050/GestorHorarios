# -*- coding: utf-8 -*-
"""Que un error se lea en castellano y diga qué hacer.

Sin esto, un dato mal escrito llega a la pantalla como «Field required» o
«Input should be a valid integer»: en inglés, con el nombre técnico del campo y
sin decir qué hay que corregir. La persona que lo ve no ha hecho nada raro —se
dejó una fecha sin poner— y se encuentra con un mensaje de programador.

Y algo más importante: **un error inesperado se registra entero y se cuenta a
medias**. Entero en el archivo de registro, para poder averiguar qué pasó; a
medias en la pantalla, porque un volcado de Python no ayuda a nadie y además
enseña rutas y nombres internos.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from gestor.registro import obtener

NOMBRES = {
    'empleado_id': 'la persona',
    'fecha_inicio': 'la fecha de inicio',
    'fecha_fin': 'la fecha de fin',
    'tipo': 'el tipo',
    'mes': 'el mes',
    'anio': 'el año',
    'turno': 'el turno',
    'area': 'el área',
    'nombre': 'el nombre',
    'usuario': 'el usuario',
    'password': 'la contraseña',
    'vigente_desde': 'la fecha desde la que rige',
}

TRADUCCIONES = {
    'missing': 'falta {campo}',
    'int_parsing': '{campo} tiene que ser un número entero',
    'float_parsing': '{campo} tiene que ser un número',
    'date_parsing': '{campo} no es una fecha válida',
    'date_from_datetime_parsing': '{campo} no es una fecha válida',
    'string_too_short': '{campo} está vacío',
    'literal_error': '{campo} no admite ese valor',
    'enum': '{campo} no admite ese valor',
    'value_error': '{campo} no es válido',
    'greater_than_equal': '{campo} es demasiado pequeño',
    'less_than_equal': '{campo} es demasiado grande',
}


def _nombre_de(ubicacion) -> str:
    for trozo in reversed(list(ubicacion)):
        if isinstance(trozo, str) and trozo not in ('body', 'query', 'path'):
            return NOMBRES.get(trozo, f'«{trozo}»')
    return 'un dato'


def en_castellano(errores) -> str:
    frases = []
    for error in errores:
        plantilla = TRADUCCIONES.get(str(error.get('type')), '{campo} no es válido')
        frases.append(plantilla.format(campo=_nombre_de(error.get('loc') or ())))
    if not frases:
        return 'Falta algún dato del formulario.'
    unicas = list(dict.fromkeys(frases))
    if len(unicas) == 1:
        return unicas[0].capitalize() + '.'
    return 'Revisa el formulario: ' + ', '.join(unicas) + '.'


def instalar(app: FastAPI) -> None:

    @app.exception_handler(RequestValidationError)
    async def formulario_incompleto(_peticion: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={'detail': en_castellano(error.errors())})

    @app.exception_handler(ValueError)
    async def dato_imposible(_peticion: Request, error: ValueError):
        # Los servicios lanzan `ValueError` con el texto ya escrito para quien
        # lo va a leer. Llega tal cual: es la forma de que la explicación viva
        # junto a la regla que la produce y no en la ruta.
        return JSONResponse(status_code=400, content={'detail': str(error)})

    @app.exception_handler(Exception)
    async def algo_inesperado(peticion: Request, error: Exception):
        obtener().exception('error inesperado en %s %s', peticion.method, peticion.url.path)
        return JSONResponse(status_code=500, content={'detail': (
            'Algo salió mal por dentro y no se pudo completar la operación. '
            'Queda anotado en el registro de la aplicación, dentro de la carpeta '
            'de datos, por si hace falta averiguar qué pasó.')})
