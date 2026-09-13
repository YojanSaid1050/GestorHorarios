# -*- coding: utf-8 -*-
"""Publicar, cerrar semanas, ver las reglas, el historial y las copias.

Cerrar una semana es lo que permite volver a generar un mes sin que cambie lo
que la gente ya trabajó. Es una decisión, no un estado técnico: por eso se hace
a mano, semana a semana, y por eso no se puede cerrar una semana con solicitudes
pendientes dentro —quedarían sin poder aprobarse y sin poder aplicarse, y nadie
sabría por qué el horario no las recoge.
"""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel

from gestor import rutas
from gestor.datos import horarios
from gestor.datos.base import abierta, transaccion
from gestor.dominio import calendario
from gestor.dominio.catalogo import catalogo
from gestor.dominio.cobertura import AREAS
from gestor.servicios import acceso, historial, periodos, publicacion

router = APIRouter(prefix='/api/operacion', tags=['operacion'])


class Semana(BaseModel):
    anio: int
    mes: int
    lunes_semana: str
    bloqueada: bool


class Publicacion(BaseModel):
    confirmar_excepciones: bool = False


@router.get('/periodo/{anio}/{mes}')
def estado_del_periodo(anio: int, mes: int):
    """Qué hay hecho de ese mes y qué se puede hacer ahora."""
    from gestor.servicios import continuidad

    if not 1 <= int(mes) <= 12:
        raise ValueError('El mes tiene que estar entre 1 y 12.')
    guardadas = horarios.propuestas(anio, mes)
    elegido = next((p for p in guardadas if p['oficial']), None)
    falta = continuidad.falta_el_mes_anterior(mes, anio)
    viejo = periodos.estado(mes, anio)
    razones = viejo['razones']

    # Las áreas se enseñan siempre las tres, y las que no tienen nada pendiente
    # lo dicen. Enseñar solo las pendientes dejaba la pantalla en blanco cuando
    # todo estaba al día, que es justo cuando hay que poder verlo.
    por_area = {area: {'requiere_actualizacion': area in viejo['areas'],
                       'razones': viejo['areas'].get(area, [])}
                for area in AREAS}

    # Se calcularon opciones nuevas y nadie ha escogido: el mes no está
    # desactualizado, pero el horario que consulta la gente sigue siendo el
    # anterior. Sin este aviso, las novedades aprobadas no aparecían en ninguna
    # parte y el mes se veía «al día».
    sin_elegir = bool(guardadas) and elegido is None

    return {
        'ok': True,
        'periodo': f'{anio}-{mes:02d}',
        'anio': int(anio), 'mes': int(mes),
        'nombre': calendario.nombre_del_periodo(mes, anio),
        'propuestas': len(guardadas),
        'hay_oficial': elegido is not None,
        'publicado': bool(elegido and elegido['publicado']),
        'se_puede_generar': not falta,
        'aviso': falta,
        # Que esté desactualizado no impide nada: es información para que decida
        # una persona. El horario guardado sigue siendo el vigente hasta que
        # alguien vuelva a generarlo a propósito.
        'desactualizado': viejo['desactualizado'],
        'sucio': viejo['desactualizado'],
        'requiere_actualizacion': viejo['desactualizado'],
        'mostrar_aviso_pendiente': viejo['desactualizado'],
        'razones': razones,
        'origen_pendiente': _de_donde_viene(razones),
        'areas': por_area,
        'areas_desactualizadas': viejo['areas'],
        'alternativas_sin_elegir': sin_elegir,
        'opciones_en_espera': len(guardadas) if sin_elegir else 0,
    }


def _de_donde_viene(razones: list[dict]) -> str:
    """El origen del aviso, porque cada uno se arregla de otra manera.

    «Hay novedades por aplicar» se resuelve aplicándolas a las áreas afectadas;
    «este mes depende de otro que cambió» se resuelve volviendo a generarlo
    entero. Dar el mismo aviso para las dos cosas obligaba a adivinar cuál era.
    """
    origenes = [str(r.get('origen') or 'cambios') for r in razones]
    if not origenes:
        return ''
    if all(o == 'continuidad' for o in origenes):
        return 'continuidad'
    return next((o for o in origenes if o != 'continuidad'), 'cambios')


@router.get('/desactualizados')
def meses_desactualizados():
    """Los meses que se armaron antes de algún cambio posterior.

    Se pregunta al entrar: es más útil ver de una vez que octubre y noviembre
    han quedado atrás que descubrirlo mes por mes.
    """
    return {'ok': True, 'meses': periodos.desactualizados()}


# ------------------------------------------------------------- las semanas

def _semanas_del_mes(anio: int, mes: int) -> list[dict]:
    with abierta() as conexion:
        cerradas = {str(f['lunes']) for f in conexion.execute(
            'SELECT lunes FROM semanas WHERE anio=? AND mes=? AND cerrada=1',
            (int(anio), int(mes)))}
    salida = []
    for inicio, fin in calendario.semanas(mes, anio):
        salida.append({
            'lunes': inicio.isoformat(),
            'lunes_semana': inicio.isoformat(),
            'domingo': fin.isoformat(),
            'bloqueada': inicio.isoformat() in cerradas,
            'cerrada': inicio.isoformat() in cerradas,
            'texto': f'{inicio.strftime("%d/%m")} al {fin.strftime("%d/%m")}',
        })
    return salida


@router.get('/semanas/{anio}/{mes}')
def ver_semanas(anio: int, mes: int):
    """Las semanas del mes y cuáles están cerradas."""
    if not 1 <= int(mes) <= 12:
        raise ValueError('El mes tiene que estar entre 1 y 12.')
    return {'ok': True, 'anio': int(anio), 'mes': int(mes),
            'semanas': _semanas_del_mes(anio, mes)}


@router.put('/semanas')
def cerrar_o_abrir_semana(semana: Semana):
    """Cerrar congela esa semana; abrirla la devuelve al reparto."""
    validas = {s['lunes'] for s in _semanas_del_mes(semana.anio, semana.mes)}
    if semana.lunes_semana not in validas:
        raise ValueError(
            f'La semana del {semana.lunes_semana} no pertenece a '
            f'{calendario.nombre_del_periodo(semana.mes, semana.anio)}.')

    if semana.bloqueada:
        domingo = (date.fromisoformat(semana.lunes_semana) + timedelta(days=6)).isoformat()
        with abierta() as conexion:
            pendientes = conexion.execute(
                "SELECT COUNT(*) n FROM solicitudes WHERE estado='pendiente' "
                'AND fecha_inicio<=? AND fecha_fin>=?',
                (domingo, semana.lunes_semana)).fetchone()['n']
        if pendientes:
            raise ValueError(
                f'No se puede cerrar la semana: hay {pendientes} solicitud(es) '
                'pendiente(s) que caen dentro. Resuélvelas primero.')

    with transaccion() as conexion:
        conexion.execute(
            'INSERT INTO semanas(anio, mes, lunes, cerrada) VALUES(?,?,?,?) '
            'ON CONFLICT(anio, mes, lunes) DO UPDATE SET cerrada=excluded.cerrada, '
            "actualizado_en=datetime('now')",
            (semana.anio, semana.mes, semana.lunes_semana,
             1 if semana.bloqueada else 0))
    historial.anotar('cerrar_semana' if semana.bloqueada else 'habilitar_semana',
                     'semana', semana.model_dump())
    return {'ok': True, 'mensaje': (
        f'La semana del {semana.lunes_semana} queda '
        + ('cerrada: se conservará tal cual al volver a generar el mes.'
           if semana.bloqueada else 'habilitada: vuelve a entrar en el reparto.'))}


# ---------------------------------------------------------- la publicación

@router.get('/publicacion/{horario_id}/resumen')
def resumen_de_publicacion(horario_id: int):
    return {'ok': True, **publicacion.resumen(horario_id)}


@router.post('/publicacion/{horario_id}')
def publicar_horario(horario_id: int, datos: Publicacion):
    resultado = publicacion.publicar(horario_id, datos.confirmar_excepciones)
    historial.anotar('publicar_horario', 'horario', {
        'horario_id': horario_id,
        'periodo': f'{resultado["anio"]}-{resultado["mes"]:02d}',
        'excepciones_confirmadas': datos.confirmar_excepciones})
    return {'ok': True, **resultado}


# --------------------------------------------------------------- las reglas

@router.get('/reglas')
def reglas_activas():
    """Las reglas que aplica la aplicación, explicadas para poder leerlas."""
    return {
        'ok': True,
        'reglas': catalogo(),
        'nota_horas': (
            'Las horas se enseñan como información del horario real. Una semana '
            'ordinaria suele sumar 42 h; una jornada administrativa puede sumar media '
            'hora más, y un festivo, un descanso compensatorio o una ausencia aprobada '
            'pueden bajarla. Esas diferencias no son un problema y nunca crean '
            'descansos por su cuenta.'),
    }


# ------------------------------------------------------ historial y copias

@router.get('/auditoria')
def ver_historial(limite: int = 300):
    registros = historial.listar(limite)
    return {'ok': True, 'historial': registros, 'items': registros}


@router.delete('/auditoria')
def vaciar_historial(peticion: Request):
    acceso.exigir_contrasena_de_administrador(peticion)
    borradas = historial.vaciar()
    return {'ok': True, 'borradas': borradas,
            'mensaje': f'Se borraron {borradas} registro(s) del historial.'}


@router.post('/backup')
def copia_de_seguridad(peticion: Request):
    """Una copia de la base, con la fecha en el nombre."""
    acceso.exigir_contrasena_de_administrador(peticion)
    rutas.preparar()
    destino = rutas.COPIAS / f'horarios_{datetime.now():%Y%m%d_%H%M%S}.db'
    with abierta() as conexion:
        import sqlite3
        copia = sqlite3.connect(destino)
        try:
            conexion.backup(copia)
        finally:
            copia.close()
    historial.anotar('crear_copia', 'sistema', {'archivo': str(destino)})
    return {'ok': True, 'archivo': str(destino), 'mensaje': (
        f'Copia guardada en {destino}.')}


#: Las tablas sin las cuales el archivo que llega no es una copia de este
#: programa. No se piden todas a propósito: una copia hecha con una versión algo
#: anterior puede no tener las últimas, y rechazarla por eso sería justo lo
#: contrario de lo que hace falta el día que alguien necesita restaurar.
TABLAS_IMPRESCINDIBLES = ('empleados', 'horarios', 'solicitudes')


def _es_una_copia_de_este_programa(ruta) -> str:
    """¿Ese archivo es una base de datos de esta aplicación? Devuelve el motivo.

    Cadena vacía si lo es. Se comprueba **antes** de tocar nada, y esa es toda
    la idea: restaurar sobrescribe la base entera, así que un archivo
    equivocado —una foto, un Excel, la copia de otro programa— destruiría el
    trabajo de la oficina y contestaría «restaurada correctamente».
    """
    try:
        conexion = sqlite3.connect(f'file:{ruta}?mode=ro', uri=True)
    except sqlite3.Error:
        return 'no se pudo abrir como base de datos'
    try:
        nombres = {f[0] for f in conexion.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError:
        return 'no es una base de datos SQLite'
    finally:
        conexion.close()
    faltan = [x for x in TABLAS_IMPRESCINDIBLES if x not in nombres]
    if faltan:
        return 'le faltan las tablas ' + ', '.join(faltan)
    return ''


def _copiar_base(origen, destino) -> None:
    """Copiar una base de SQLite **con SQLite**, no con el sistema de archivos.

    La base trabaja en modo WAL, y eso significa que lo escrito hace un momento
    puede estar todavía en `horarios.db-wal` y no dentro de `horarios.db`. Copiar
    el archivo suelto, que es lo que se hacía, produce una copia a la que le
    faltan las últimas operaciones —justo las que interesan— y lo hace en
    silencio: el archivo existe, pesa lo suyo y abre bien.

    `Connection.backup` copia la base entera tal y como está, WAL incluido.
    """
    con_origen = sqlite3.connect(origen)
    try:
        con_destino = sqlite3.connect(destino)
        try:
            con_origen.backup(con_destino)
        finally:
            con_destino.close()
    finally:
        con_origen.close()


def _restaurar_encima(candidata) -> None:
    """Volcar la copia elegida dentro de la base de trabajo.

    También con SQLite y no con el sistema de archivos, y aquí importa el doble:

    * al lado de `horarios.db` viven `-wal` y `-shm`. Sustituyendo solo el
      archivo principal, esos dos se quedan con el contenido de **la base
      anterior** y SQLite los aplica encima de la recién restaurada. Lo que
      queda no es ni lo uno ni lo otro;
    * en Windows no se puede sobrescribir un archivo que alguien tiene abierto.
      Copiando por encima, restaurar fallaba o se quedaba esperando a un
      candado, que es como llegar al peor día con un problema más.

    Volcando con `backup` no se toca ningún archivo por fuera: es la propia
    SQLite la que reemplaza el contenido, en una operación y con los candados
    que hagan falta.
    """
    origen = sqlite3.connect(f'file:{candidata}?mode=ro', uri=True)
    try:
        with abierta() as destino:
            origen.backup(destino)
    finally:
        origen.close()


@router.post('/restore')
async def restaurar(peticion: Request, archivo: UploadFile = File(...)):
    """Vuelve a una copia. Antes guarda otra de lo que hay ahora.

    Restaurar no se deshace, así que lo que hay ahora se guarda primero: si la
    copia elegida no era la que se creía, todavía se puede volver.

    El archivo **llega subido**, no se busca por su nombre en la carpeta de
    copias. Estaba declarado como un `str`, que en FastAPI significa «un dato en
    la dirección», mientras la pantalla mandaba el archivo de verdad: esto
    contestaba «Falta “archivo”» siempre y **restaurar una copia no funcionó
    nunca**. Que llegue subido es además lo que hace falta: el día que se
    necesita, la copia buena suele estar en un USB o en otro equipo, no en la
    carpeta de una instalación que a lo mejor ya no arranca.
    """
    acceso.exigir_contrasena_de_administrador(peticion)
    contenido = await archivo.read()
    if not contenido:
        raise ValueError('El archivo que subiste está vacío.')

    rutas.preparar()
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as temporal:
        temporal.write(contenido)
        candidata = temporal.name
    try:
        problema = _es_una_copia_de_este_programa(candidata)
        if problema:
            raise ValueError(
                f'«{archivo.filename}» no es una copia de seguridad de este '
                f'programa: {problema}. No se ha tocado nada. Busca un archivo '
                'de los que crea el propio programa, que terminan en .db.')
        antes = rutas.COPIAS / f'antes_de_restaurar_{datetime.now():%Y%m%d_%H%M%S}.db'
        _copiar_base(rutas.BASE_DE_DATOS, antes)
        _restaurar_encima(candidata)
    finally:
        Path(candidata).unlink(missing_ok=True)

    historial.anotar('restaurar_copia', 'sistema',
                     {'archivo': archivo.filename, 'respaldo': str(antes)})
    return {'ok': True, 'mensaje': (
        f'Se restauró la copia {archivo.filename}. Lo que había antes quedó '
        f'guardado en {antes.name}, por si hiciera falta volver. Vuelve a entrar '
        'con tu contraseña: las sesiones abiertas también estaban en la copia.')}


@router.get('/copias')
def listar_copias():
    rutas.preparar()
    return {'ok': True, 'copias': sorted(
        (p.name for p in rutas.COPIAS.glob('*.db')), reverse=True)}
