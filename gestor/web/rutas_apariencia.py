# -*- coding: utf-8 -*-
"""Cómo se ve: el modo, el tema y los colores del Excel.

Los colores no son decoración. La misma casilla se lee en pantalla y en el papel
que se reparte, y quien mira lo uno y quien mira lo otro tienen que ver lo
mismo. Por eso hay un solo juego de colores y no dos.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from gestor.servicios import apariencia, historial, marco

router = APIRouter(prefix='/api/configuracion', tags=['apariencia'])


class Modo(BaseModel):
    modo: str


class Tema(BaseModel):
    tema: str


class Paleta(BaseModel):
    paleta: str


class BarraDeVentana(BaseModel):
    propia: bool


@router.get('/modo-app')
def ver_modo():
    return {'ok': True, 'modo': apariencia.obtener_modo_app(),
            'modos': apariencia.MODOS_APP,
            'opciones': [{'id': clave, 'nombre': nombre}
                         for clave, nombre in apariencia.MODOS_APP.items()],
            'predeterminado': apariencia.DEFAULT_APP_MODE}


@router.put('/modo-app')
def poner_modo(modo: Modo):
    elegido = apariencia.guardar_modo_app(modo.modo)
    historial.anotar('cambiar_modo_app', 'configuracion', {'modo': elegido})
    return {'ok': True, 'modo': elegido, 'mensaje': (
        f'La aplicación se verá en modo {apariencia.MODOS_APP[elegido].lower()}.')}


@router.get('/tema-app')
def ver_tema():
    temas = apariencia.listar_temas_app()
    return {'ok': True, 'tema': apariencia.obtener_tema_app(),
            'temas': temas, 'opciones': temas}


@router.put('/tema-app')
def poner_tema(tema: Tema):
    resultado = apariencia.guardar_tema_app(tema.tema)
    historial.anotar('cambiar_tema_app', 'configuracion', {'tema': tema.tema})
    return {'ok': True, 'tema': resultado, 'mensaje': (
        f'La aplicación ahora usa el tema {resultado["nombre"]}.')}


@router.delete('/tema-app')
def volver_al_tema_de_siempre():
    resultado = apariencia.restablecer_tema_app()
    historial.anotar('restablecer_tema_app', 'configuracion', {'tema': resultado['id']})
    return {'ok': True, 'tema': resultado,
            'mensaje': 'Se restauró el color predeterminado de la aplicación.'}


@router.get('/colores-excel')
def ver_colores():
    """Los colores puestos, las paletas, y un aviso de los que no se cambian.

    El de la mañana se mantiene siempre en blanco a propósito, para que el turno
    más frecuente se lea igual en todas las paletas. Decirlo aquí evita la
    sorpresa de cambiarlo y ver que no cambia nada.
    """
    return {
        'ok': True,
        'colores': apariencia.obtener_colores_excel(),
        'por_defecto': dict(apariencia.DEFAULT_EXCEL_COLORS),
        'predeterminados': dict(apariencia.DEFAULT_EXCEL_COLORS),
        'paletas': apariencia.listar_paletas_excel(),
        'fijos': {'AM': ('La mañana se mantiene en blanco en todas las paletas, '
                         'para que el turno más frecuente se lea siempre igual.')},
    }


@router.put('/colores-excel')
def poner_colores(colores: dict[str, str]):
    """El cuerpo son los colores tal cual, sin envoltorio.

    Es como la pantalla lo envía desde siempre: `{"header": "#...", ...}`.
    """
    return {'ok': True, 'colores': apariencia.guardar_colores_excel(colores),
            'mensaje': 'Los colores del horario y del Excel quedaron guardados.'}


@router.delete('/colores-excel')
def volver_a_los_colores_de_siempre():
    return {'ok': True, 'colores': apariencia.restablecer_colores_excel(),
            'mensaje': 'Se restauraron todos los colores originales.'}


@router.delete('/colores-excel/{clave}')
def volver_un_color(clave: str):
    colores = apariencia.restablecer_color_excel(clave)
    return {'ok': True, 'clave': clave, 'colores': colores,
            'predeterminado': apariencia.DEFAULT_EXCEL_COLORS.get(clave),
            'mensaje': 'Se restauró el color original de este elemento.'}


@router.get('/colores-excel/paletas')
def ver_paletas():
    return {'ok': True, 'paletas': apariencia.listar_paletas_excel()}


@router.post('/colores-excel/paleta')
def aplicar_paleta(paleta: Paleta):
    resultado = apariencia.aplicar_paleta_excel(paleta.paleta)
    historial.anotar('aplicar_paleta_excel', 'configuracion', {'paleta': paleta.paleta})
    # Se devuelven también las fichas: «La mía» tiene que enseñar los colores
    # que acaban de quedar puestos, no los de antes.
    return {'ok': True, 'colores': resultado,
            'paletas': apariencia.listar_paletas_excel(),
            'mensaje': ('Se aplicó la paleta. Puedes seguir ajustando cualquier '
                        'color por separado.')}


@router.get('/barra-ventana')
def ver_barra_de_ventana():
    """Con qué barra de título se abre la ventana del programa.

    La pantalla no usa esto para decidir si pintar la barra —eso lo contesta la
    propia ventana, que sabe cómo se creó y contesta antes de iniciar sesión—,
    sino para enseñar el interruptor en Configuración como está.
    """
    return {'ok': True, 'propia': marco.barra_propia(),
            'aviso': 'El cambio se ve la próxima vez que abras la aplicación.'}


@router.put('/barra-ventana')
def poner_barra_de_ventana(barra: BarraDeVentana):
    """Cambiar de barra. Se nota al volver a abrir, no ahora.

    El marco de una ventana se decide al crearla y no se puede quitar ni poner
    con la ventana abierta, así que decirlo claro aquí evita la duda de haber
    pulsado y no ver nada.
    """
    propia = marco.poner_barra_propia(barra.propia)
    historial.anotar('cambiar_barra_ventana', 'configuracion', {'propia': propia})
    return {'ok': True, 'propia': propia, 'mensaje': (
        'Al abrir la aplicación de nuevo, la barra de título será la del '
        'programa.' if propia else
        'Al abrir la aplicación de nuevo, la barra de título será la de Windows, '
        'con sus botones de siempre.')}
