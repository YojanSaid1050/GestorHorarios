# -*- coding: utf-8 -*-
"""Las reglas y los ajustes: cobertura, jornadas seguidas, festivos y reinicios.

Todo lo que se toca aquí lleva **fecha de vigencia**, y no es un detalle: un
cambio de política no puede alterar un mes ya oficializado. Si en noviembre se
decide que Comunicaciones pasa a 2 de mañana, octubre se sigue midiendo con la
regla con la que se hizo. Lo único que ocurre es que los meses ya generados
quedan marcados, para que una persona decida cuándo rehacerlos.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from gestor.datos import personal
from gestor.dominio import calendario
from gestor.dominio import festivos as festivos_dom
from gestor.dominio.cobertura import AREAS, NOMBRES_AREA, ReglaCobertura
from gestor.servicios import (
    acceso,
    historial,
    periodos,
    reglas_cobertura,
    reglas_operacion,
    reinicios,
    siembra,
)

router = APIRouter(prefix='/api/configuracion', tags=['configuracion'])


class ReglaDeCobertura(BaseModel):
    """Lo que envía la tarjeta de reparto.

    `minimo_total` es como la pantalla llama al mínimo del área desde siempre.
    `exigir_desde_rotativos` se admite y se ignora: fue una idea que llegó a la
    base pero que ninguna cuenta llegó a usar, y rechazar la petición por
    seguir enviándola solo impediría guardar el reparto.
    """
    area: str
    vigente_desde: str
    am_minimo: int = 0
    pm_minimo: int = 0
    minimo_total: Optional[int] = None
    minimo_area: Optional[int] = None
    am_objetivo: Optional[int] = None
    pm_objetivo: Optional[int] = None
    am_maximo: Optional[int] = None
    pm_maximo: Optional[int] = None
    exigir_desde_rotativos: Optional[int] = None
    nota: str = ''


class ReglaDeOperacion(BaseModel):
    vigente_desde: str
    max_dias_consecutivos: int
    nota: str = ''


class FestivoMovido(BaseModel):
    fecha_original: str
    fecha_nueva: str
    nombre: str = ''


class DesdeElMes(BaseModel):
    mes: int
    anio: int


# --------------------------------------------------- reparto de cada área

def _operativos(area: str) -> int:
    """Cuánta gente rota de verdad en el área ahora mismo.

    El tope de las casillas no está escrito en ningún sitio: es la plantilla que
    hay hoy. Así se mueve solo cuando entra o sale personal, en vez de quedarse
    en un número que alguien puso una vez.
    """
    return sum(1 for p in personal.listar()
               if p.get('area') == area and p.get('tipo_turno') != 'administrativo')


@router.get('/reglas-cobertura')
def ver_reglas_cobertura():
    areas = []
    for area in AREAS:
        historial_area = reglas_cobertura.con_identificador(area)
        vigente = historial_area[-1] if historial_area else None
        operativos = _operativos(area)
        aviso, nivel = '', 'informativo'
        if vigente:
            pedido = max(int(vigente['am_minimo']) + int(vigente['pm_minimo']),
                         int(vigente['minimo_area'] or 0))
            if operativos and pedido >= operativos:
                # La válvula: un mínimo no puede exigir al área entera, porque
                # entonces nadie podría descansar nunca.
                aviso = (f'{NOMBRES_AREA.get(area, area)} tiene {operativos} persona(s) en '
                         f'turnos y el mínimo pide {pedido}. La aplicación exigirá como '
                         f'mucho {max(operativos - 1, 0)}: si no, nadie podría descansar.')
                nivel = 'aviso'
        areas.append({
            'area': area,
            'nombre': NOMBRES_AREA.get(area, area),
            'vigente': vigente,
            'historial': historial_area,
            'personal_operativo': operativos,
            'maximo': max(operativos, 1),
            'aviso': aviso,
            'aviso_nivel': nivel,
        })
    return {'ok': True, 'areas': areas,
            'nombres': {a: reglas_cobertura.descripcion_minimos_regla(a) for a in AREAS}}


@router.put('/reglas-cobertura')
def guardar_regla_cobertura(regla: ReglaDeCobertura):
    datos = regla.model_dump()
    if datos['area'] not in AREAS:
        raise ValueError(f'El área tiene que ser una de: {", ".join(AREAS)}.')
    minimo_area = datos.pop('minimo_total', None)
    if minimo_area is None:
        minimo_area = datos.get('minimo_area')
    datos['minimo_area'] = int(minimo_area or 0)
    datos.pop('exigir_desde_rotativos', None)
    for clave in ('am_minimo', 'pm_minimo', 'minimo_area'):
        if int(datos.get(clave) or 0) < 0:
            raise ValueError('Un mínimo no puede ser negativo.')
    reglas_cobertura.guardar(ReglaCobertura(**datos))
    historial.anotar('guardar_regla_cobertura', 'configuracion', datos)
    aviso = periodos.avisar_desde(
        datos['vigente_desde'],
        f'cambió la cobertura pedida en {NOMBRES_AREA.get(datos["area"], datos["area"])}',
        datos['area'], origen='reglas')
    return {'ok': True, 'mensaje': (
        f'Reparto de {NOMBRES_AREA.get(datos["area"], datos["area"])} guardado desde el '
        f'{datos["vigente_desde"]}.' + aviso)}


@router.delete('/reglas-cobertura/{regla_id}')
def borrar_regla_cobertura(regla_id: int):
    quitada = reglas_cobertura.borrar_por_id(regla_id)
    historial.anotar('borrar_regla_cobertura', 'configuracion', quitada)
    aviso = periodos.avisar_desde(
        quitada['vigente_desde'], 'se quitó una regla de cobertura', quitada['area'],
        origen='reglas')
    return {'ok': True, 'mensaje': (
        f'Se quitó el reparto del {quitada["vigente_desde"]}. Los meses ya generados con '
        'él conservan su programación.' + aviso)}


# ------------------------------------------------- máximo de días seguidos

@router.get('/reglas-operacion')
def ver_reglas_operacion():
    return {'ok': True,
            'reglas': reglas_operacion.historial(),
            'historial': reglas_operacion.historial(),
            'vigente': reglas_operacion.regla().como_dict(),
            'minimo': reglas_operacion.MINIMO_DIAS,
            'maximo': reglas_operacion.MAXIMO_DIAS}


@router.put('/reglas-operacion')
def guardar_regla_operacion(regla: ReglaDeOperacion):
    resultado = reglas_operacion.guardar(
        regla.vigente_desde, regla.max_dias_consecutivos, regla.nota)
    historial.anotar('guardar_regla_operacion', 'configuracion', regla.model_dump())
    # Sin área: el máximo de jornadas seguidas vale para toda la oficina.
    aviso = periodos.avisar_desde(
        regla.vigente_desde, 'cambió el máximo de jornadas seguidas', origen='reglas')
    return {'ok': True, 'regla': resultado, 'mensaje': (
        f'Desde el {regla.vigente_desde}, el máximo es de '
        f'{regla.max_dias_consecutivos} jornadas seguidas.' + aviso)}


@router.delete('/reglas-operacion/{regla_id}')
def borrar_regla_operacion(regla_id: int):
    previas = {int(r['id']): r for r in reglas_operacion.historial() if r.get('id')}
    quitada = previas.get(int(regla_id))
    if not reglas_operacion.eliminar(regla_id):
        raise ValueError('Esa regla ya no existe.')
    historial.anotar('borrar_regla_operacion', 'configuracion', {'id': regla_id})
    aviso = (periodos.avisar_desde(quitada['vigente_desde'],
                                   'se quitó un máximo de jornadas seguidas',
                                   origen='reglas')
             if quitada else '')
    return {'ok': True, 'mensaje': 'Se quitó ese máximo.' + aviso}


# ------------------------------------------------------------- festivos

def _festivos_del_anio(anio: int) -> dict:
    from gestor.datos.base import abierta
    with abierta() as conexion:
        ajustes = [dict(f) for f in conexion.execute(
            'SELECT fecha_original, fecha_nueva, nombre FROM festivos_ajustes '
            'WHERE substr(fecha_original,1,4)=? ORDER BY fecha_original',
            (f'{int(anio):04d}',))]
    base = festivos_dom.del_anio(anio)
    por_original = {a['fecha_original']: a for a in ajustes}
    return {'ok': True, 'anio': int(anio), 'festivos': [{
        'fecha_original': fecha.isoformat(),
        'fecha': por_original.get(fecha.isoformat(), {}).get(
            'fecha_nueva', fecha.isoformat()),
        'fecha_efectiva': por_original.get(fecha.isoformat(), {}).get(
            'fecha_nueva', fecha.isoformat()),
        'nombre': por_original.get(fecha.isoformat(), {}).get('nombre', nombre),
        'modificado': fecha.isoformat() in por_original,
    } for fecha, nombre in base.items()]}


@router.get('/festivos')
def ver_festivos(anio: int = 2026):
    return _festivos_del_anio(anio)


@router.get('/festivos/{anio}')
def ver_festivos_del_anio(anio: int):
    return _festivos_del_anio(anio)


@router.put('/festivos')
def mover_festivo(festivo: FestivoMovido):
    from gestor.datos.base import transaccion
    with transaccion() as conexion:
        conexion.execute(
            'INSERT OR REPLACE INTO festivos_ajustes(fecha_original, fecha_nueva, nombre) '
            'VALUES(?,?,?)',
            (festivo.fecha_original, festivo.fecha_nueva,
             festivo.nombre or 'Festivo ajustado'))
    historial.anotar('mover_festivo', 'configuracion', festivo.model_dump())
    # Los dos días importan: el que deja de ser festivo y el que pasa a serlo.
    aviso = periodos.avisar([festivo.fecha_original, festivo.fecha_nueva],
                            'se movió un festivo', origen='reglas')
    return {'ok': True, 'mensaje': (
        f'El festivo del {festivo.fecha_original} pasa al {festivo.fecha_nueva}.' + aviso)}


@router.delete('/festivos/{fecha_original}')
def devolver_festivo(fecha_original: str):
    from gestor.datos.base import transaccion
    with transaccion() as conexion:
        # Se mira antes de borrar: al deshacer el traslado cambian los dos días,
        # el que recupera el festivo y el que lo pierde.
        fila = conexion.execute(
            'SELECT fecha_nueva FROM festivos_ajustes WHERE fecha_original=?',
            (fecha_original,)).fetchone()
        conexion.execute('DELETE FROM festivos_ajustes WHERE fecha_original=?',
                         (fecha_original,))
    historial.anotar('restaurar_festivo', 'configuracion', {'fecha': fecha_original})
    aviso = periodos.avisar(
        [fecha_original, fila['fecha_nueva'] if fila else None],
        'se devolvió un festivo a su fecha', origen='reglas')
    return {'ok': True, 'mensaje': (
        f'El festivo vuelve a su fecha, el {fecha_original}.' + aviso)}


@router.get('/calendario/{anio}/{mes}')
def ver_calendario(anio: int, mes: int):
    return {'ok': True, 'dias': calendario.dias_del_periodo(mes, anio),
            'nombre': calendario.nombre_del_periodo(mes, anio)}


# ------------------------------------------------------------- reinicios

@router.post('/reiniciar-programacion')
def reiniciar_programacion(desde: DesdeElMes, peticion: Request):
    acceso.exigir_contrasena_propia(peticion)
    resultado = reinicios.reiniciar_programacion(desde.mes, desde.anio)
    historial.anotar('reiniciar_programacion', 'configuracion', resultado)
    return resultado


@router.post('/reiniciar-fabrica')
def reiniciar_fabrica(peticion: Request):
    acceso.exigir_contrasena_de_administrador(peticion)
    resultado = siembra.restablecer_de_fabrica()
    from gestor.servicios.acceso import asegurar_cuentas_iniciales
    asegurar_cuentas_iniciales()
    return resultado
