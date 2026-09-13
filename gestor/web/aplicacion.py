# -*- coding: utf-8 -*-
"""El servidor: qué se levanta al abrir la aplicación y en qué orden.

La aplicación es un servidor local con una ventana delante. Nada de esto sale a
internet salvo cuando alguien pulsa «comprobar si hay versión nueva».

Al arrancar se hacen tres cosas, y el orden importa:

1. **se prepara la base** —crearla si no existe, con su forma final;
2. **se siembra lo que falte** —personal, reglas y las dos programaciones base;
3. **se asegura que haya con quién entrar**, porque una aplicación instalada sin
   ninguna cuenta es una aplicación que no se puede abrir.

Si algo de eso falla, **la aplicación arranca igual** y lo dice en pantalla. Un
arranque que se niega a empezar deja a quien lo sufre sin ninguna información;
uno que abre y explica qué le falta se puede arreglar.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from gestor import rutas, version
from gestor.registro import obtener
from gestor.web import errores

#: Lo que no arrancó bien, para poder contarlo en `/api/salud` en vez de
#: perderlo en un registro que nadie va a abrir.
problemas_de_arranque: list[str] = []


def preparar_todo() -> None:
    from gestor.datos.base import preparar_base
    from gestor.servicios import siembra
    from gestor.servicios.acceso import asegurar_cuentas_iniciales

    problemas_de_arranque.clear()
    try:
        preparar_base()
    except Exception as exc:                                       # noqa: BLE001
        obtener().exception('no se pudo preparar la base de datos')
        problemas_de_arranque.append(
            f'No se pudo preparar la base de datos en {rutas.BASE_DE_DATOS}: {exc}')
        return

    try:
        resultado = siembra.sembrar()
        if resultado.faltan:
            problemas_de_arranque.append(
                'A esta instalación le faltan archivos que deberían venir dentro del '
                f'programa: {", ".join(resultado.faltan)}. Puedes dejarlos en '
                f'{rutas.RAIZ_DATOS / "datos_iniciales"} y volver a abrir la aplicación, '
                'o reinstalarla. No generes esos meses de nuevo: se perdería la '
                'programación que ya está vigente.')
    except Exception as exc:                                       # noqa: BLE001
        obtener().exception('no se pudo sembrar la instalación')
        problemas_de_arranque.append(f'No se pudieron cargar los datos iniciales: {exc}')

    try:
        asegurar_cuentas_iniciales()
    except Exception as exc:                                       # noqa: BLE001
        obtener().exception('no se pudieron asegurar las cuentas')
        problemas_de_arranque.append(f'No se pudieron preparar las cuentas: {exc}')


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    preparar_todo()
    yield


def crear_aplicacion() -> FastAPI:
    app = FastAPI(title=f'{version.NOMBRE} {version.VERSION}',
                  version=version.VERSION, lifespan=ciclo_de_vida)

    # La ventana carga desde el mismo servidor, así que esto solo hace falta
    # cuando alguien abre la aplicación en un navegador aparte para mirar algo.
    app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True,
                       allow_methods=['*'], allow_headers=['*'])

    errores.instalar(app)

    from gestor.web import (
        rutas_acceso,
        rutas_apariencia,
        rutas_configuracion,
        rutas_exportacion,
        rutas_horarios,
        rutas_novedades,
        rutas_operacion,
        rutas_personal,
        rutas_sistema,
    )
    for modulo in (rutas_sistema, rutas_acceso, rutas_personal, rutas_novedades,
                   rutas_horarios, rutas_configuracion, rutas_apariencia,
                   rutas_exportacion, rutas_operacion):
        app.include_router(modulo.router)

    from gestor.servicios.acceso import comprobar_permiso

    @app.middleware('http')
    async def guardar_la_puerta(peticion: Request, siguiente):
        respuesta = await comprobar_permiso(peticion, siguiente)
        camino = peticion.url.path
        # La pantalla se sirve desde aquí y se reemplaza entera en cada
        # actualización. Sin esto, tras actualizar se seguía viendo el diseño
        # anterior porque el navegador daba por bueno lo que ya tenía guardado.
        if camino == '/' or camino.endswith(('.js', '.css', '.html')):
            respuesta.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            respuesta.headers['Pragma'] = 'no-cache'
        return respuesta

    if rutas.PANTALLA.is_dir():
        app.mount('/', StaticFiles(directory=rutas.PANTALLA, html=True), name='pantalla')
    else:
        @app.get('/')
        def sin_pantalla():
            return JSONResponse(
                {'detail': f'No se encuentra la pantalla en {rutas.PANTALLA}.'},
                status_code=500)

    return app


app = crear_aplicacion()
