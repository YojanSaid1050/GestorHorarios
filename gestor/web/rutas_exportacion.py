# -*- coding: utf-8 -*-
"""Sacar el horario a Excel.

Son tres libros, cada uno para algo distinto, y la diferencia importa:

* **para trabajar** — el que se edita, con los controles vivos como fórmulas;
* **una semana** — de lunes a domingo, para imprimir y repartir;
* **completo** — el período con los comentarios de cada día y las hojas de
  consulta.

Los colores salen de la configuración de la aplicación, los mismos que pintan la
tabla en pantalla: quien mira el papel y quien mira la pantalla tienen que ver
lo mismo.

Hay **dos formas de guardar** y la aplicación elige sola. Con la ventana de
escritorio abierta se ofrece el «Guardar como» del sistema, para dejar el
archivo donde la persona quiera. Sin ella —en un navegador, o si el diálogo
falla— se guarda en la carpeta de exportaciones y se dice dónde quedó. Lo que
nunca pasa es que el Excel se pierda: si el diálogo se rompe a mitad, el archivo
ya está creado y se informa de su ruta.
"""
from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from gestor import rutas
from gestor.datos import horarios
from gestor.dominio import calendario
from gestor.registro import obtener
from gestor.servicios import historial, ventana
from gestor.servicios.excel import LIBROS, crear_excel

router = APIRouter(prefix='/api/exportacion', tags=['exportacion'])

#: Las peticiones de «Guardar como» en marcha. Viven en memoria a propósito: si
#: la aplicación se cierra mientras el diálogo está abierto, no queda nada que
#: limpiar ni ninguna fila huérfana en la base.
_solicitudes: dict[str, dict] = {}
_candado = threading.Lock()


class Peticion(BaseModel):
    nombre: Optional[str] = None
    horario_id: Optional[int] = None
    libro: str = 'trabajo'
    semana_inicio: Optional[str] = None


def _construir(anio: int, mes: int, peticion: Peticion) -> Path:
    """Genera el Excel del horario oficial del mes y devuelve dónde quedó."""
    if peticion.libro not in LIBROS:
        raise ValueError(f'Ese libro no existe. Los que hay son: {", ".join(LIBROS)}.')
    elegido = (horarios.obtener(int(peticion.horario_id))
               if peticion.horario_id else horarios.oficial(anio, mes))
    if elegido is None:
        raise ValueError(
            f'{calendario.nombre_del_periodo(mes, anio)} todavía no tiene horario '
            'oficial. Elige una de las propuestas antes de exportar.')
    if peticion.libro == 'semana' and not peticion.semana_inicio:
        raise ValueError('Elige qué semana quieres exportar.')

    # El horario que se pide por identificador tiene su propio mes, y no tenía
    # por qué ser el de la dirección. Se sobrescribía sin comparar: pedir el
    # horario de octubre desde la dirección de noviembre producía un Excel con
    # los turnos de octubre y «Noviembre 2026» impreso en la cabecera. Ese papel
    # se reparte, y quien lo recibe no tiene forma de saber cuál de las dos
    # cosas es la equivocada.
    if int(elegido['anio']) != int(anio) or int(elegido['mes']) != int(mes):
        suyo = calendario.nombre_del_periodo(int(elegido['mes']), int(elegido['anio']))
        raise ValueError(
            f'Esa programación es de {suyo} y se está pidiendo como '
            f'{calendario.nombre_del_periodo(mes, anio)}. Exporta cada mes desde '
            'su propia pantalla.')
    if peticion.semana_inicio:
        inicio, fin = calendario.rango(int(mes), int(anio))
        if not (inicio.isoformat() <= str(peticion.semana_inicio)[:10] <= fin.isoformat()):
            raise ValueError(
                f'La semana del {peticion.semana_inicio} no está dentro de '
                f'{calendario.nombre_del_periodo(mes, anio)}.')

    resultado = dict(elegido['datos'])
    resultado['mes'], resultado['anio'] = int(mes), int(anio)
    resultado['_export_libro'] = peticion.libro
    if peticion.semana_inicio:
        resultado['_export_week_start'] = peticion.semana_inicio
    # Un horario que todavía no se ha publicado sale marcado como borrador. Sin
    # esa marca, un papel impreso a media revisión es indistinguible del bueno.
    resultado['_es_borrador_export'] = not bool(elegido.get('publicado'))
    return crear_excel(resultado, peticion.libro)


def _renombrar(archivo: Path, nombre: Optional[str]) -> Path:
    """Deja el archivo con el nombre que se pidió, dentro de la misma carpeta.

    El nombre se limpia de carpetas: sin esto, escribir «..\\algo.xlsx» en la
    casilla del nombre sería una forma de escribir fuera de la carpeta de
    exportaciones.
    """
    limpio = Path(str(nombre or '')).name.strip()
    if not limpio or limpio == archivo.name:
        return archivo
    if not limpio.lower().endswith('.xlsx'):
        limpio += '.xlsx'
    destino = archivo.with_name(limpio)
    if destino != archivo:
        shutil.move(str(archivo), str(destino))
    return destino


@router.get('/libros')
def libros_disponibles():
    return {'ok': True, 'libros': [{'id': k, 'nombre': v} for k, v in LIBROS.items()]}


@router.get('/modo')
def como_se_guarda():
    """¿Hay «Guardar como» en este equipo, o se guarda en la carpeta?"""
    return {'ok': True, 'dialogo_nativo': ventana.hay_ventana(),
            'carpeta': str(rutas.EXPORTACIONES), 'ruta': str(rutas.EXPORTACIONES)}


@router.get('/carpeta')
def donde_van():
    rutas.preparar()
    return {'ok': True, 'ruta': str(rutas.EXPORTACIONES),
            'carpeta': str(rutas.EXPORTACIONES),
            'archivos': sorted((p.name for p in rutas.EXPORTACIONES.glob('*.xlsx')),
                               reverse=True)[:50]}


@router.post('/exportar/{anio}/{mes}')
def exportar(anio: int, mes: int, peticion: Peticion):
    """Genera el Excel y lo deja en la carpeta de exportaciones."""
    archivo = _renombrar(_construir(anio, mes, peticion), peticion.nombre)
    historial.anotar('exportar_excel', 'horario',
                     {'periodo': f'{anio}-{mes:02d}', 'libro': peticion.libro,
                      'archivo': archivo.name})
    return {'ok': True, 'archivo': archivo.name, 'nombre': archivo.name,
            'ruta': str(archivo), 'carpeta': str(archivo.parent),
            'mensaje': f'{archivo.name} se guardó en {archivo.parent}.'}


# ------------------------------------------------------- «Guardar como»

@router.post('/dialogo/{anio}/{mes}')
def pedir_ubicacion(anio: int, mes: int, peticion: Peticion,
                    tareas: BackgroundTasks):
    """Prepara el archivo y abre el «Guardar como» sin bloquear la pantalla.

    El Excel se crea **antes** de abrir el diálogo. Es al revés de lo intuitivo
    y es a propósito: si algo falla al generarlo, se dice enseguida y no después
    de que alguien haya elegido carpeta y nombre para nada.
    """
    if not ventana.hay_ventana():
        raise ValueError(
            'Este equipo no tiene el diálogo nativo de guardado disponible. '
            'El archivo se guardará en la carpeta de exportaciones.')
    archivo = _construir(anio, mes, peticion)
    identificador = uuid.uuid4().hex
    sugerido = Path(str(peticion.nombre or archivo.name)).name or archivo.name
    with _candado:
        _solicitudes[identificador] = {'estado': 'dialogo', 'origen': str(archivo)}
    tareas.add_task(_pedir_y_mover, identificador, archivo, sugerido)
    return {'ok': True, 'request_id': identificador, 'estado': 'dialogo'}


def _pedir_y_mover(identificador: str, archivo: Path, sugerido: str) -> None:
    def anotar(**datos):
        with _candado:
            _solicitudes[identificador] = {**_solicitudes.get(identificador, {}), **datos}

    try:
        destino = ventana.guardar_como(sugerido, str(rutas.EXPORTACIONES))
    except Exception as exc:                                       # noqa: BLE001
        # El archivo ya existe: que el diálogo falle no puede perderlo.
        obtener().exception('falló el diálogo de guardado')
        anotar(estado='completado', fallback=True, ruta=str(archivo),
               nombre=archivo.name, carpeta=str(archivo.parent), mensaje=str(exc))
        return
    if not destino:
        anotar(estado='cancelado', mensaje='No se guardó ningún archivo.')
        return
    try:
        final = Path(destino)
        if not final.suffix:
            final = final.with_suffix('.xlsx')
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(archivo), str(final))
    except Exception as exc:                                       # noqa: BLE001
        obtener().exception('no se pudo mover el Excel al destino elegido')
        anotar(estado='completado', fallback=True, ruta=str(archivo),
               nombre=archivo.name, carpeta=str(archivo.parent), mensaje=str(exc))
        return
    anotar(estado='completado', fallback=False, ruta=str(final),
           nombre=final.name, carpeta=str(final.parent))
    historial.anotar('exportar_excel', 'horario', {'archivo': final.name})


@router.get('/estado/{identificador}')
def estado_de_la_exportacion(identificador: str):
    with _candado:
        solicitud = _solicitudes.get(identificador)
    if solicitud is None:
        raise ValueError('Esa exportación ya no está en curso.')
    if solicitud.get('estado') in ('completado', 'cancelado', 'error'):
        with _candado:
            _solicitudes.pop(identificador, None)
    return {'ok': True, **solicitud}


# --------------------------------------------------------------- abrir

class Ruta(BaseModel):
    ruta: str


@router.post('/abrir-archivo')
def abrir_archivo(destino: Ruta):
    """Abre el Excel recién guardado. Si no se puede, se dice dónde está."""
    if ventana.abrir_en_el_sistema(destino.ruta):
        return {'ok': True, 'ruta': destino.ruta}
    return {'ok': False, 'ruta': destino.ruta, 'mensaje': (
        f'No se pudo abrir el archivo desde aquí. Está en {destino.ruta}.')}


@router.post('/abrir-carpeta')
def abrir_carpeta():
    rutas.preparar()
    if ventana.abrir_en_el_sistema(rutas.EXPORTACIONES):
        return {'ok': True, 'ruta': str(rutas.EXPORTACIONES)}
    return {'ok': False, 'ruta': str(rutas.EXPORTACIONES), 'mensaje': (
        f'No se pudo abrir la carpeta desde aquí. Está en {rutas.EXPORTACIONES}.')}


@router.get('/descargar/{nombre}')
def descargar(nombre: str):
    """Entrega un archivo ya exportado.

    Solo de la carpeta de exportaciones, y comprobándolo de verdad: sin esto,
    un nombre con «..» dentro sería una forma de pedirle al programa cualquier
    archivo del disco.
    """
    destino = (rutas.EXPORTACIONES / nombre).resolve()
    if rutas.EXPORTACIONES.resolve() not in destino.parents or not destino.is_file():
        raise ValueError(f'No se encuentra «{nombre}» entre los archivos exportados.')
    return FileResponse(destino, filename=destino.name)
