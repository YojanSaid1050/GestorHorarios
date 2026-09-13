# -*- coding: utf-8 -*-
"""La base de datos: una sola forma, sin columnas muertas y sin migraciones.

Estas pruebas no comprueban que SQLite funcione. Comprueban las tres promesas
que hace `datos/esquema.py`, que son exactamente las tres que la versión
anterior no podía hacer:

1. la base tiene la misma forma en todas las instalaciones;
2. no hay columnas que ya no use nadie;
3. los códigos de turno que admite son los que existen hoy.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from gestor.datos import esquema
from gestor.dominio import codigos

RAIZ = Path(__file__).resolve().parents[1]


def test_la_base_se_crea_entera_de_una_vez(base):
    with base.abierta() as conexion:
        creadas = {r['name'] for r in conexion.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    assert creadas == set(esquema.tablas())


def test_crear_dos_veces_no_rompe_nada(base):
    """Arrancar la aplicación sobre una base que ya existe es lo normal."""
    with base.abierta() as conexion:
        esquema.crear(conexion)
        esquema.crear(conexion)
        assert base.version_del_esquema() == esquema.VERSION_ESQUEMA


def test_no_existe_ninguna_tabla_de_migraciones(base):
    """La promesa del archivo, comprobada.

    Una tabla de marcas de migración es lo que hacía que la forma de la base
    dependiera de desde qué versión venía cada usuario, y lo que permitió que
    una columna escrita por error sobreviviera incluso a «restablecer de
    fábrica».
    """
    assert 'migraciones' not in esquema.tablas()
    with base.abierta() as conexion:
        nombres = {r['name'] for r in conexion.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any('migrac' in n for n in nombres)


def test_no_hay_migraciones_escritas_en_el_codigo():
    fuentes = list((RAIZ / 'gestor').rglob('*.py'))
    sospechosas = []
    for archivo in fuentes:
        texto = archivo.read_text(encoding='utf-8')
        for numero, linea in enumerate(texto.splitlines(), 1):
            if re.search(r'\bALTER TABLE\b', linea, re.IGNORECASE):
                sospechosas.append(f'{archivo.name}:{numero}')
    assert not sospechosas, (
        'han vuelto las migraciones al vuelo: ' + ', '.join(sospechosas))


# --------------------------------------------------- ninguna columna muerta

def _columnas_declaradas() -> dict[str, set[str]]:
    salida = {}
    for bloque in re.finditer(
            r'CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);', esquema.ESQUEMA, re.S):
        tabla, cuerpo = bloque.group(1), bloque.group(2)
        columnas = set()
        for linea in cuerpo.splitlines():
            linea = linea.strip()
            if not linea or linea.startswith('--'):
                continue
            primera = linea.split()[0]
            palabra = primera.split('(')[0].upper()
            if palabra in {'PRIMARY', 'FOREIGN', 'UNIQUE', 'CHECK', 'CONSTRAINT'}:
                continue
            # Una restricción larga ocupa varias líneas; sus continuaciones no
            # empiezan por un nombre de columna válido.
            if not re.fullmatch(r'[a-z_][a-z0-9_]*', primera):
                continue
            columnas.add(primera)
        salida[tabla] = columnas
    return salida


def test_todas_las_tablas_declaran_columnas():
    declaradas = _columnas_declaradas()
    assert set(declaradas) == set(esquema.tablas())
    for tabla, columnas in declaradas.items():
        assert columnas, f'{tabla} no declara ninguna columna'


def test_ninguna_columna_se_queda_sin_usar():
    """La regla que impide que vuelva a acumularse deuda.

    En la versión anterior había columnas que ninguna consulta miraba: sobras de
    versiones anteriores que nadie se atrevía a quitar porque nadie sabía si
    seguían en uso. Aquí, una columna que no aparece en el código es un error de
    la prueba, y hay que decidir: se usa o se borra del esquema.

    Se comprueba contra el código de la aplicación, no contra las pruebas: una
    columna que solo usan las pruebas tampoco sirve para nada.
    """
    codigo = '\n'.join(a.read_text(encoding='utf-8')
                       for a in (RAIZ / 'gestor').rglob('*.py')
                       if a.name != 'esquema.py')
    sin_usar = []
    for tabla, columnas in _columnas_declaradas().items():
        for columna in columnas:
            if columna == 'id':
                continue
            if not re.search(rf'\b{re.escape(columna)}\b', codigo):
                sin_usar.append(f'{tabla}.{columna}')
    assert not sin_usar, (
        'columnas declaradas que no usa nadie; o se usan o se quitan:\n  '
        + '\n  '.join(sorted(sin_usar)))


# ------------------------------------------- los códigos vienen del dominio

def test_los_turnos_que_admite_la_base_son_los_que_existen_hoy():
    """Escritos a mano, las restricciones acababan admitiendo códigos difuntos.

    La base anterior seguía aceptando `ADM-G-AC` y `ADM-COM`, que ya no
    significaban nada. Aquí la lista se genera desde `dominio.codigos`, así que
    no puede descolgarse.
    """
    encontrado = re.search(r"turno\s+TEXT NOT NULL CHECK\(turno IN \(([^)]*)\)\)",
                           esquema.ESQUEMA)
    assert encontrado, 'no se encuentra la restricción de turnos'
    admitidos = {t.strip().strip("'") for t in encontrado.group(1).split(',')}
    assert admitidos == set(codigos.TODOS)


def test_las_areas_que_admite_la_base_son_las_del_dominio():
    from gestor.dominio.cobertura import AREAS
    for area in AREAS:
        assert f"'{area}'" in esquema.ESQUEMA


@pytest.mark.parametrize('turno', ['ADM-G-AC', 'ADM-COM'])
def test_los_codigos_difuntos_ya_no_se_admiten(turno):
    assert f"'{turno}'" not in esquema.ESQUEMA


# ------------------------------------------------------------- integridad

def test_las_claves_ajenas_estan_activas_en_cada_conexion(base):
    """SQLite las desactiva por defecto y es por conexión.

    Sin esto, borrar a una persona dejaba sus solicitudes apuntando a un
    identificador que ya no existe, y el fallo salía mucho después, al abrir la
    pantalla que las lista.
    """
    with base.abierta() as conexion:
        assert conexion.execute('PRAGMA foreign_keys').fetchone()[0] == 1


def test_borrar_a_una_persona_se_lleva_lo_suyo(base):
    with base.transaccion() as conexion:
        conexion.execute(
            "INSERT INTO empleados(nombre,area,tipo_turno) "
            "VALUES('Ana','gestion_social','rotativo')")
        eid = conexion.execute("SELECT id FROM empleados WHERE nombre='Ana'").fetchone()['id']
        conexion.execute(
            "INSERT INTO solicitudes(empleado_id,tipo,fecha_inicio,fecha_fin) "
            "VALUES(?,'vacaciones','2026-10-01','2026-10-05')", (eid,))

    with base.transaccion() as conexion:
        conexion.execute('DELETE FROM empleados WHERE id=?', (eid,))

    with base.abierta() as conexion:
        assert conexion.execute('SELECT COUNT(*) n FROM solicitudes').fetchone()['n'] == 0


def test_una_transaccion_a_medias_no_deja_nada_escrito(base):
    """Todo o nada. Media operación hecha es peor que ninguna."""
    with pytest.raises(RuntimeError), base.transaccion() as conexion:
        conexion.execute(
            "INSERT INTO empleados(nombre,area,tipo_turno) "
            "VALUES('Beto','gestion_social','rotativo')")
        raise RuntimeError('algo revienta a mitad')

    with base.abierta() as conexion:
        assert conexion.execute('SELECT COUNT(*) n FROM empleados').fetchone()['n'] == 0


def test_un_turno_inventado_se_rechaza(base):
    import sqlite3
    with base.transaccion() as conexion:
        conexion.execute(
            "INSERT INTO empleados(nombre,area,tipo_turno) "
            "VALUES('Cris','gestion_social','rotativo')")
    with pytest.raises(sqlite3.IntegrityError), base.transaccion() as conexion:
        eid = conexion.execute("SELECT id FROM empleados WHERE nombre='Cris'").fetchone()['id']
        conexion.execute(
            "INSERT INTO ajustes_manuales(empleado_id,fecha,turno) VALUES(?,?,?)",
            (eid, '2026-10-05', 'INVENTADO'))


# ------------------------------------------------------------- las rutas

def test_los_datos_no_viven_dentro_de_la_carpeta_del_programa(carpeta_de_datos):
    """La separación de la que depende que actualizar no borre el trabajo.

    Velopack reemplaza la carpeta del programa entera en cada actualización. Si
    la base viviera ahí debajo, cada versión nueva se llevaría por delante el
    trabajo de la oficina.
    """
    from gestor import rutas
    programa = Path(rutas.RAIZ_PROGRAMA).resolve()
    datos = Path(rutas.RAIZ_DATOS).resolve()
    assert programa not in datos.parents and programa != datos, (
        f'los datos ({datos}) están dentro del programa ({programa})')


def test_el_codigo_no_repite_la_version_a_mano():
    """El octavo sitio, que en la versión anterior siempre se descolgaba."""
    from gestor.version import VERSION
    sueltas = []
    for archivo in (RAIZ / 'gestor').rglob('*.py'):
        if archivo.name == 'version.py':
            continue
        arbol = ast.parse(archivo.read_text(encoding='utf-8'))
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)
                    and re.fullmatch(r'v?\d+\.\d+\.\d+', nodo.value, re.IGNORECASE)):
                sueltas.append(f'{archivo.name}:{nodo.lineno} → {nodo.value}')
    assert not sueltas, (
        f'la versión es {VERSION} y está escrita a mano en:\n  ' + '\n  '.join(sueltas))


# ------------------------------------------- el vocabulario que usa el motor

#: Los nombres que el motor conoce y que `motor.vocabulario` reexporta desde
#: `dominio.codigos`. La lista está aquí escrita a mano **a propósito**: es lo
#: que convierte «alguien quitó un reexporte» en un fallo inmediato.
REEXPORTES_DEL_MOTOR = (
    'ALL_CODES', 'WORK_CODES', 'NONWORK_CODES', 'OUT_OF_VIGENCY_CODE',
    'FATIGUE_ADMIN_CODES',
)


@pytest.mark.parametrize('nombre', REEXPORTES_DEL_MOTOR)
def test_el_motor_encuentra_los_codigos_con_sus_nombres_de_siempre(nombre):
    """El puente entre los nombres del motor y los del dominio.

    El motor los conoce en inglés y el dominio los llama en castellano. La
    traducción vive en un solo sitio, y es lo que permitió mover los códigos sin
    tocar una línea del motor.

    Esta prueba existe por un susto real: una limpieza automática de
    importaciones «sin usar» se llevó cuatro de estos nombres —no se usan en el
    archivo que los reexporta, se usan en otros diez— y el motor entero dejó de
    arrancar. Todas las pruebas que lo tocaban fallaron a la vez con un
    ImportError, que al menos es ruidoso; lo que no puede pasar es que se cuele.
    """
    from gestor.motor import vocabulario

    assert hasattr(vocabulario, nombre), (
        f'{nombre} ya no se reexporta: el motor no arranca sin él')


def test_los_codigos_reexportados_son_los_mismos_que_los_del_dominio():
    """No son una copia: son el mismo conjunto, con otro nombre."""
    from gestor.dominio import codigos
    from gestor.motor import vocabulario

    assert set(vocabulario.ALL_CODES) == set(codigos.TODOS)
    assert set(vocabulario.WORK_CODES) == set(codigos.TRABAJADOS)
    assert set(vocabulario.NONWORK_CODES) == set(codigos.NO_TRABAJADOS)
    assert vocabulario.OUT_OF_VIGENCY_CODE == codigos.FUERA_DE_VIGENCIA
