# -*- coding: utf-8 -*-
"""Dejar una instalación nueva lista para trabajar.

Una aplicación recién instalada no puede arrancar en blanco: sin personal no hay
horario que generar, y sin el mes anterior no hay continuidad con la que empezar
el siguiente. Por eso viajan dentro del programa tres archivos —la plantilla de
personal y las dos programaciones ya publicadas, agosto y septiembre de 2026— y
al arrancar por primera vez se cargan.

Dos cosas que aquí se hacen a propósito:

* **Si falta un archivo, se dice y no se arranca en blanco.** La versión
  anterior se compiló una vez sin la base de septiembre: la aplicación abría con
  ese mes vacío y en silencio, y quien lo viera podía pensar que había que
  generarlo de nuevo, perdiendo el horario que la oficina ya estaba trabajando.
* **La siembra no pisa nada.** Se ejecuta en cada arranque y solo escribe lo que
  falta, así que abrir la aplicación cien veces no duplica a nadie.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from gestor import rutas
from gestor.datos.base import abierta, transaccion
from gestor.dominio import calendario
from gestor.registro import obtener
from gestor.servicios import reglas_cobertura, reglas_operacion

PLANTILLA = 'empleados_iniciales.csv'
BASES = ('base_agosto_2026.json', 'base_septiembre_2026.json')


@dataclass
class Resultado:
    personas: int = 0
    bases: tuple[str, ...] = ()
    faltan: tuple[str, ...] = ()

    @property
    def completa(self) -> bool:
        return not self.faltan


def _archivos_que_faltan() -> list[str]:
    return [n for n in (PLANTILLA, *BASES) if not rutas.dato_inicial(n).exists()]


def _leer_plantilla(ruta: Path) -> list[dict]:
    # `utf-8-sig`: el CSV viene de Excel y trae la marca de orden de bytes al
    # principio. Sin esto, la primera columna se llamaba «﻿nombre» y nadie
    # encontraba el nombre de la primera persona.
    with ruta.open('r', encoding='utf-8-sig', newline='') as archivo:
        return list(csv.DictReader(archivo))


def _entero(valor):
    texto = str(valor or '').strip()
    return int(texto) if texto else None


def sembrar_personal() -> int:
    """Carga la plantilla inicial. No toca a quien ya esté."""
    from gestor.datos import personal

    ruta = rutas.dato_inicial(PLANTILLA)
    if not ruta.exists():
        return 0
    filas = _leer_plantilla(ruta)

    creadas = 0
    parejas: list[tuple[str, str]] = []
    for fila in filas:
        nombre = (fila.get('nombre') or '').strip()
        if not nombre or personal.por_nombre(nombre):
            continue
        personal.crear({
            'nombre': nombre,
            'cargo': (fila.get('cargo') or '').strip() or 'GUÍA SOCIAL',
            'area': (fila.get('area') or '').strip(),
            'tipo_turno': (fila.get('tipo_turno') or '').strip(),
            'turno_fijo': (fila.get('turno_fijo') or '').strip() or None,
            'descanso_fijo': _entero(fila.get('descanso_fijo')),
            'inicio_rotacion': (fila.get('inicio_rotacion') or '').strip() or None,
            'fecha_ancla_rotacion': (fila.get('fecha_ancla_rotacion') or '').strip() or None,
            'orden_rotacion': _entero(fila.get('orden_rotacion')) or 0,
            'exento_especiales': str(fila.get('exento_especiales') or '0').strip() == '1',
            'alta_desde': (fila.get('alta_desde') or '').strip() or '2026-08-01',
            'retirado_desde': (fila.get('retirado_desde') or '').strip() or None,
            'activo': not (fila.get('retirado_desde') or '').strip(),
        })
        creadas += 1
        companera = (fila.get('pareja_nombre') or '').strip()
        if companera:
            parejas.append((nombre, companera))

    # Las parejas se unen al final, cuando ya existen las dos personas, y
    # siempre por los dos lados. Una pareja escrita en un solo sentido es una
    # pareja que el motor ve desde una punta y no desde la otra.
    for uno, otro in parejas:
        a, b = personal.por_nombre(uno), personal.por_nombre(otro)
        if a and b and a.get('pareja_id') != b['id']:
            personal.emparejar(a['id'], b['id'])
    return creadas


def _dia_de_la_base(fecha: str, turno: str, archivo: str, calendario_del_periodo: dict) -> dict:
    """Una casilla transcrita, con su día del calendario ya puesto.

    Lo que viene del Excel es solo «esta persona, este día, este turno». Lo
    demás —el nombre del día, si es festivo, a qué semana pertenece— es del
    calendario y se calcula, nunca se transcribe: transcribirlo sería otra
    copia del calendario que se puede descolgar.
    """
    origen = archivo.replace('.json', '')
    return {
        **calendario_del_periodo.get(fecha, {'fecha': fecha}),
        'turno': turno,
        'turno_original': turno,
        'origen': origen,
        'bloqueado': True,
        'vigente': True,
        'observacion': 'Transcrito del horario que la oficina ya trabajó',
    }


def _cargar_base(nombre: str) -> bool:
    """Deja publicado un mes que llega ya hecho, transcrito del Excel real."""
    from gestor.datos import personal

    ruta = rutas.dato_inicial(nombre)
    if not ruta.exists():
        return False
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    periodo = datos.get('periodo') or {}
    anio, mes = int(periodo['anio']), int(periodo['mes'])

    with abierta() as conexion:
        ya_esta = conexion.execute(
            'SELECT 1 FROM horarios WHERE anio=? AND mes=? AND fuente=? LIMIT 1',
            (anio, mes, nombre.replace('.json', ''))).fetchone()
    if ya_esta:
        return True

    # El archivo trae fecha y turno, y nada más. Todo lo que la pantalla
    # necesita para pintar la cuadrícula —qué día de la semana es, si es
    # festivo, si pertenece a otro mes— se calcula aquí a partir de la fecha.
    # Sin esto la cabecera de agosto y septiembre salía diciendo «undefined» en
    # cada columna, y ni los fines de semana ni los festivos se distinguían: la
    # transcripción era correcta y aun así el mes se veía roto.
    calendario_del_periodo = {d['fecha']: d for d in calendario.dias_del_periodo(mes, anio)}

    por_nombre = {p['nombre']: p for p in personal.listar(incluir_retirados=True)}
    filas = []
    for persona in datos.get('empleados', ()):
        ficha = por_nombre.get(persona['nombre'])
        if ficha is None:
            obtener().warning('la base %s nombra a «%s», que no está en la plantilla',
                              nombre, persona['nombre'])
            continue
        filas.append({
            'empleado_id': ficha['id'],
            'nombre': ficha['nombre'],
            'area': ficha['area'],
            'tipo_turno': ficha['tipo_turno'],
            'turno_base': ficha.get('turno_fijo'),
            'cobertura_dias': ficha.get('cobertura_dias'),
            # La pareja viaja con la fila: la revisión de publicación mira si
            # dos personas emparejadas coinciden de turno, y sin este dato no
            # podía comprobarlo en los meses base.
            'pareja_id': ficha.get('pareja_id'),
            'dias': [_dia_de_la_base(f, t, nombre, calendario_del_periodo)
                     for f, t in sorted((persona.get('turnos') or {}).items())],
        })

    # Las horas, los domingos y los festivos trabajados se calculan con la misma
    # función que usa el motor, no con una cuenta aparte. Un mes transcrito se
    # lee en la misma pantalla que los demás, y sin esto salía con todas las
    # columnas de horas a cero, como si nadie hubiera trabajado.
    try:
        from gestor.motor.orquestacion import estadisticas
        stats = estadisticas(filas)
    except Exception:                                              # noqa: BLE001
        obtener().exception('no se pudieron calcular las estadísticas de %s', nombre)
        stats = []

    with transaccion() as conexion:
        conexion.execute(
            'INSERT INTO horarios(anio, mes, datos_json, valido, errores_json, '
            'grupo_id, alternativa, oficial, publicado, fuente) '
            "VALUES(?,?,?,?,'[]',?,1,1,1,?)",
            (anio, mes, json.dumps(
                {'mes': mes, 'anio': anio, 'valido': True, 'errores': [],
                 'advertencias': [], 'estadisticas': stats, 'horario': filas},
                ensure_ascii=False, default=str), 1,
             f'base-{anio}-{mes:02d}', nombre.replace('.json', '')))
    return True


def sembrar(completa: bool = True) -> Resultado:
    """Deja la instalación lista. Se puede llamar en cada arranque."""
    faltan = tuple(_archivos_que_faltan())
    if faltan:
        obtener().error('faltan archivos iniciales dentro del programa: %s', ', '.join(faltan))

    with transaccion() as conexion:
        reglas_cobertura.sembrar_de_fabrica(conexion)
        reglas_operacion.sembrar_regla_inicial(conexion)

    personas = sembrar_personal() if completa else 0
    bases = tuple(n for n in BASES if _cargar_base(n)) if completa else ()
    return Resultado(personas=personas, bases=bases, faltan=faltan)


def restablecer_de_fabrica() -> dict:
    """Deja la aplicación como recién instalada.

    Se vacía **todo** lo que es trabajo del usuario y se vuelve a sembrar. Las
    reglas de cobertura y el tope de jornadas entran en el vaciado a propósito:
    en la versión anterior no lo hacían, así que una regla editada sobrevivía a
    «volver a cero», y con ella sobrevivió durante versiones la exención de
    festivos que dejaba un área sin cobertura.
    """
    tablas = (
        'sesiones', 'usuarios', 'historial', 'ajustes_manuales', 'semanas',
        'periodos_area', 'periodos', 'horarios', 'asignaciones', 'solicitudes',
        'empleados_historial', 'empleados', 'festivos_ajustes', 'configuracion',
        'reglas_cobertura', 'reglas_operacion',
    )
    with transaccion() as conexion:
        for tabla in tablas:
            conexion.execute(f'DELETE FROM {tabla}')
        conexion.execute(
            "DELETE FROM sqlite_sequence WHERE name IN "
            "('empleados','horarios','solicitudes','asignaciones','historial')")
    reglas_cobertura.olvidar_lo_leido()
    reglas_operacion.invalidar_cache()

    from gestor.datos import esquema
    with abierta() as conexion:
        esquema.crear(conexion)

    resultado = sembrar(completa=True)
    return {
        'ok': True,
        'personas': resultado.personas,
        'bases': list(resultado.bases),
        'mensaje': ('La aplicación volvió a su estado inicial: el personal de fábrica, '
                    'las reglas de cobertura, el tope de jornadas seguidas y las dos '
                    'programaciones base de agosto y septiembre de 2026.'),
    }
