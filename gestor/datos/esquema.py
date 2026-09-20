# -*- coding: utf-8 -*-
"""La base de datos, en su forma final y de una sola vez.

**Aquí no hay migraciones, y eso es lo importante de este archivo.**

La aplicación anterior tenía once migraciones encadenadas: la base se creaba con
la forma de la primera versión y cada versión posterior le iba añadiendo
columnas y reescribiendo filas. Sonaba prudente y resultó ser el mecanismo por
el que una versión vieja seguía mandando meses después:

* una columna que una versión escribió por error —la exención de festivos de
  Atención al Ciudadano— sobrevivía a todo, incluso a «restablecer de fábrica»,
  porque restablecer borraba filas pero no la columna ni su valor;
* cada migración dejaba una marca en una tabla, y si la marca no se borraba, la
  siembra que dependía de ella no volvía a ejecutarse; así se quedó la
  aplicación sin el tope de jornadas seguidas después de un reinicio;
* nadie podía decir con certeza qué forma tenía la base de un usuario concreto,
  porque dependía de desde qué versión venía.

Como se empieza con datos limpios, no hace falta nada de eso. El esquema se
crea entero, con la forma que tiene hoy, y es idéntico en todas las
instalaciones. Si algún día hace falta cambiarlo, la respuesta es una versión
del esquema y una conversión explícita y probada, no una columna añadida al
vuelo.

Dos reglas que sostienen esto y que hay una prueba vigilando:

1. **Ninguna columna sin uso.** Toda columna declarada aquí tiene que aparecer
   en algún sitio del código que la lea o la escriba.
2. **Los códigos de turno vienen de `dominio.codigos`.** Las restricciones
   `CHECK` se generan a partir de esa lista y no se escriben a mano; si no,
   acaban admitiendo códigos que ya no existen, como pasó con `ADM-G-AC`.
"""
from __future__ import annotations

import sqlite3

from gestor.dominio import codigos
from gestor.dominio.cobertura import AREAS

VERSION_ESQUEMA = 1

_AREAS = ','.join(f"'{a}'" for a in AREAS)
_TURNOS = ','.join(f"'{c}'" for c in codigos.TODOS)
_ADMINISTRATIVOS = ','.join(
    f"'{c}'" for c in sorted(set(codigos.ADMINISTRATIVOS_POR_AREA.values())))

ESQUEMA = f"""
PRAGMA foreign_keys = ON;

-- Quién trabaja aquí y cómo rota. ---------------------------------------
CREATE TABLE IF NOT EXISTS empleados (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre               TEXT NOT NULL UNIQUE,
    cargo                TEXT NOT NULL DEFAULT 'GUÍA SOCIAL',
    area                 TEXT NOT NULL CHECK(area IN ({_AREAS})),
    tipo_turno           TEXT NOT NULL CHECK(tipo_turno IN ('fijo','rotativo','administrativo')),
    turno_fijo           TEXT CHECK(turno_fijo IN ('AM','PM') OR turno_fijo IS NULL),
    descanso_fijo        INTEGER CHECK(descanso_fijo BETWEEN 0 AND 6 OR descanso_fijo IS NULL),
    -- Dos personas que se cubren entre sí: la aplicación evita ponerlas en el
    -- mismo turno para que siempre quede una de las dos disponible.
    pareja_id            INTEGER,
    inicio_rotacion      TEXT CHECK(inicio_rotacion IN ('AM','PM') OR inicio_rotacion IS NULL),
    fecha_ancla_rotacion TEXT,
    orden_rotacion       INTEGER NOT NULL DEFAULT 0,
    -- Queda fuera del reparto de domingos y festivos.
    exento_especiales    INTEGER NOT NULL DEFAULT 0 CHECK(exento_especiales IN (0,1)),
    es_nuevo             INTEGER NOT NULL DEFAULT 0 CHECK(es_nuevo IN (0,1)),
    -- Los días de la semana en los que esta persona cuenta para el mínimo del
    -- área. Vacío = todos, que es lo normal. Se guarda en positivo y no como
    -- excepciones: escrito al revés había que acordarse de invertirlo en cada
    -- sitio que lo mirase, y el sitio que se olvidó dejó un turno sin nadie.
    cobertura_dias_json  TEXT NOT NULL DEFAULT '',
    activo               INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0,1)),
    -- Desde cuándo forma parte de la plantilla y hasta cuándo. Antes de su alta
    -- y después de su retiro, esa persona no cuenta para nada: ni suma al
    -- mínimo del área ni se le reprocha no descansar. Sin estas dos fechas, dar
    -- de alta a alguien en septiembre lo metía también en agosto.
    alta_desde           TEXT NOT NULL DEFAULT '2026-08-01',
    retirado_desde       TEXT,
    -- Con qué nombre venía esta persona en la plantilla inicial, si vino de
    -- ahí. Es lo que permite reconocerla después de un cambio de nombre: la
    -- siembra corre en cada arranque y usaba el nombre como identidad, así que
    -- corregir una tilde hacía reaparecer a la persona anterior al día
    -- siguiente, duplicada y sin pareja.
    origen_siembra       TEXT,
    FOREIGN KEY(pareja_id) REFERENCES empleados(id) ON DELETE SET NULL
);

-- Cómo estaba configurada una persona en una fecha dada. Sin esto, cambiar
-- hoy el turno de alguien reescribía meses ya publicados.
CREATE TABLE IF NOT EXISTS empleados_historial (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    empleado_id   INTEGER NOT NULL,
    vigente_desde TEXT NOT NULL,
    datos_json    TEXT NOT NULL,
    -- Qué personas cambiaron juntas. Dos de una pareja de PC cambian a la vez y
    -- en turnos contrarios, así que deshacer una sin la otra las deja a las dos
    -- en el mismo turno. Antes se buscaba a la pareja **de hoy** con la misma
    -- fecha: si la pareja había cambiado desde entonces, se deshacía el cambio
    -- de alguien que nunca estuvo en él.
    grupo         TEXT,
    creado_en     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(empleado_id) REFERENCES empleados(id) ON DELETE CASCADE
);

-- Novedades que pide una persona y alguien aprueba o rechaza.
--
-- El tipo NO es el código de turno que acabará en la casilla. Una solicitud de
-- vacaciones acaba escribiendo VAC, pero una de «cambio de turno ese día» no
-- escribe ningún código nuevo: cambia el que ya tenía. Confundir las dos cosas
-- —que es lo que pasa al reutilizar la lista de códigos aquí— deja fuera la
-- mitad de las novedades que la oficina pide de verdad.
CREATE TABLE IF NOT EXISTS solicitudes (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    empleado_id           INTEGER NOT NULL,
    tipo                  TEXT NOT NULL CHECK(tipo IN (
                              'descanso','vacaciones','incapacidad','permiso',
                              'capacitacion','turno_dia','turno_semanas',
                              'cambio_pareja','cambio_persona')),
    fecha_inicio          TEXT NOT NULL,
    fecha_fin             TEXT NOT NULL,
    -- Una novedad recurrente sin final: «los martes libra», hasta nuevo aviso.
    sin_fecha_fin         INTEGER NOT NULL DEFAULT 0 CHECK(sin_fecha_fin IN (0,1)),
    modo_periodo          TEXT NOT NULL DEFAULT 'rango'
                          CHECK(modo_periodo IN ('rango','semanal')),
    dia_semana_recurrente INTEGER CHECK(dia_semana_recurrente BETWEEN 0 AND 6
                                        OR dia_semana_recurrente IS NULL),
    -- Qué se hace con el turno que deja libre: nada, o lo cubre otra persona.
    modo_cobertura        TEXT NOT NULL DEFAULT 'sin_cubrir'
                          CHECK(modo_cobertura IN ('sin_cubrir','reemplazar')),
    reemplazo_empleado_id INTEGER,
    intercambio_empleado_id INTEGER,
    turno_solicitado      TEXT CHECK(turno_solicitado IN ('AM','PM') OR turno_solicitado IS NULL),
    dia_descanso_solicitado INTEGER CHECK(dia_descanso_solicitado BETWEEN 0 AND 6
                                          OR dia_descanso_solicitado IS NULL),
    -- De cuándo a cuándo dura una capacitación. La pantalla pedía las dos horas
    -- desde el principio y no había dónde guardarlas: se tiraban al llegar, y
    -- luego el motor intentaba leerlas igualmente y se llevaba el mes por
    -- delante. Vacías significan «una jornada entera», que es lo que hace
    -- falta saber para el horario.
    hora_inicio           TEXT,
    hora_fin              TEXT,
    -- Cancelada no es rechazada: rechazar es «no te lo concedo», cancelar es
    -- «se concedió y luego no hizo falta». En el historial se leen distinto.
    estado                TEXT NOT NULL DEFAULT 'pendiente'
                          CHECK(estado IN ('pendiente','aprobada','rechazada','cancelada')),
    observacion           TEXT NOT NULL DEFAULT '',
    creado_en             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resuelto_en           TEXT,
    FOREIGN KEY(empleado_id) REFERENCES empleados(id) ON DELETE CASCADE,
    FOREIGN KEY(reemplazo_empleado_id) REFERENCES empleados(id) ON DELETE SET NULL,
    FOREIGN KEY(intercambio_empleado_id) REFERENCES empleados(id) ON DELETE SET NULL
);

-- Lo que decide la coordinación: descansos extra, jornadas administrativas,
-- actividades y excepciones de turno.
CREATE TABLE IF NOT EXISTS asignaciones (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    empleado_id            INTEGER NOT NULL,
    tipo                   TEXT NOT NULL CHECK(tipo IN (
                               'descanso_extra','asignacion_administrativa',
                               'actividad','excepcion_turno')),
    fechas_json            TEXT NOT NULL DEFAULT '[]',
    recurrente_indefinido  INTEGER NOT NULL DEFAULT 0 CHECK(recurrente_indefinido IN (0,1)),
    dias_semana_json       TEXT NOT NULL DEFAULT '[]',
    horario_administrativo TEXT CHECK(horario_administrativo IN
                               ('OPERATIVO','AM','PM',{_ADMINISTRATIVOS})
                               OR horario_administrativo IS NULL),
    turno_excepcion        TEXT CHECK(turno_excepcion IN ('AM','PM') OR turno_excepcion IS NULL),
    -- Cuando alguien pasa a jornada administrativa, si además hay que liberar
    -- la cobertura que tenía y que otra persona la garantice.
    libera_cobertura       INTEGER NOT NULL DEFAULT 0 CHECK(libera_cobertura IN (0,1)),
    reemplazo_empleado_id  INTEGER,
    descripcion            TEXT NOT NULL DEFAULT '',
    -- Desde cuándo rige. Para una asignación con fechas es la primera; para una
    -- que se repite sin final —«los domingos trabaja en AM»— es lo único que
    -- dice a partir de qué mes empieza a contar.
    vigente_desde          TEXT,
    -- Cancelar no borra: la asignación existió y tiene que poder leerse en el
    -- historial. Lo que hace es dejar de aplicarse.
    estado                 TEXT NOT NULL DEFAULT 'activo'
                           CHECK(estado IN ('activo','cancelado')),
    -- Una asignación puesta a varias personas de una vez. El grupo se guarda
    -- en cada fila y no en una tabla aparte a propósito: así una de ellas se
    -- puede cancelar sola sin desmontar el grupo, y el grupo entero se puede
    -- cancelar de una vez buscando por este identificador.
    grupo_id               TEXT,
    grupo_alcance          TEXT CHECK(grupo_alcance IN ('area','todos') OR grupo_alcance IS NULL),
    grupo_area             TEXT CHECK(grupo_area IN ({_AREAS}) OR grupo_area IS NULL),
    grupo_etiqueta         TEXT,
    creado_en              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(empleado_id) REFERENCES empleados(id) ON DELETE CASCADE,
    FOREIGN KEY(reemplazo_empleado_id) REFERENCES empleados(id) ON DELETE SET NULL
);

-- Los horarios generados: las cinco propuestas de cada mes y cuál es la
-- oficial. `fuente` distingue lo que calculó el motor de lo que llegó
-- transcrito de un Excel real.
CREATE TABLE IF NOT EXISTS horarios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    anio         INTEGER NOT NULL,
    mes          INTEGER NOT NULL CHECK(mes BETWEEN 1 AND 12),
    datos_json   TEXT NOT NULL,
    valido       INTEGER NOT NULL CHECK(valido IN (0,1)),
    errores_json TEXT NOT NULL DEFAULT '[]',
    grupo_id     TEXT,
    alternativa  INTEGER NOT NULL DEFAULT 1,
    oficial      INTEGER NOT NULL DEFAULT 0 CHECK(oficial IN (0,1)),
    publicado    INTEGER NOT NULL DEFAULT 0 CHECK(publicado IN (0,1)),
    fuente       TEXT NOT NULL DEFAULT 'generado',
    creado_en    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    publicado_en TEXT
);

-- Cambios hechos a mano sobre una casilla concreta, que se vuelven a aplicar
-- cada vez que se regenera el mes. Se borran al reiniciar la programación:
-- que sobrevivieran era lo que hacía reaparecer el mes «reiniciado» igual.
CREATE TABLE IF NOT EXISTS ajustes_manuales (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    empleado_id   INTEGER NOT NULL,
    fecha         TEXT NOT NULL,
    turno         TEXT NOT NULL CHECK(turno IN ({_TURNOS})),
    forzado       INTEGER NOT NULL DEFAULT 0 CHECK(forzado IN (0,1)),
    justificacion TEXT NOT NULL DEFAULT '',
    reglas_json   TEXT NOT NULL DEFAULT '[]',
    activo        INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0,1)),
    creado_en     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(empleado_id, fecha),
    FOREIGN KEY(empleado_id) REFERENCES empleados(id) ON DELETE CASCADE
);

-- Semanas ya pasadas que se cierran para que no se recalculen.
CREATE TABLE IF NOT EXISTS semanas (
    anio          INTEGER NOT NULL,
    mes           INTEGER NOT NULL CHECK(mes BETWEEN 1 AND 12),
    lunes         TEXT NOT NULL,
    cerrada       INTEGER NOT NULL DEFAULT 0 CHECK(cerrada IN (0,1)),
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(anio, mes, lunes)
);

-- Qué meses y qué áreas han quedado desactualizados por un cambio.
CREATE TABLE IF NOT EXISTS periodos (
    anio           INTEGER NOT NULL,
    mes            INTEGER NOT NULL CHECK(mes BETWEEN 1 AND 12),
    sucio          INTEGER NOT NULL DEFAULT 0 CHECK(sucio IN (0,1)),
    razones_json   TEXT NOT NULL DEFAULT '[]',
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(anio, mes)
);

CREATE TABLE IF NOT EXISTS periodos_area (
    anio           INTEGER NOT NULL,
    mes            INTEGER NOT NULL CHECK(mes BETWEEN 1 AND 12),
    area           TEXT NOT NULL CHECK(area IN ({_AREAS})),
    sucio          INTEGER NOT NULL DEFAULT 0 CHECK(sucio IN (0,1)),
    razones_json   TEXT NOT NULL DEFAULT '[]',
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(anio, mes, area)
);

-- Cuánta gente pide cada área, desde cuándo. Editable desde la aplicación.
CREATE TABLE IF NOT EXISTS reglas_cobertura (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    area          TEXT NOT NULL CHECK(area IN ({_AREAS})),
    vigente_desde TEXT NOT NULL,
    am_minimo     INTEGER NOT NULL DEFAULT 0,
    pm_minimo     INTEGER NOT NULL DEFAULT 0,
    minimo_area   INTEGER NOT NULL DEFAULT 0,
    am_objetivo   INTEGER,
    pm_objetivo   INTEGER,
    am_maximo     INTEGER,
    pm_maximo     INTEGER,
    nota          TEXT NOT NULL DEFAULT '',
    creado_en     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(area, vigente_desde)
);

-- El tope de jornadas seguidas, también con fecha de vigencia.
CREATE TABLE IF NOT EXISTS reglas_operacion (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    vigente_desde         TEXT NOT NULL UNIQUE,
    max_dias_consecutivos INTEGER NOT NULL,
    nota                  TEXT NOT NULL DEFAULT '',
    creado_en             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Festivos movidos de fecha por la oficina.
CREATE TABLE IF NOT EXISTS festivos_ajustes (
    fecha_original TEXT PRIMARY KEY,
    fecha_nueva    TEXT NOT NULL,
    nombre         TEXT NOT NULL,
    creado_en      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS configuracion (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

-- Quién hizo qué. Es lo único que permite reconstruir por qué un mes salió así.
CREATE TABLE IF NOT EXISTS historial (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    accion       TEXT NOT NULL,
    entidad      TEXT NOT NULL,
    actor        TEXT NOT NULL DEFAULT '',
    detalle_json TEXT NOT NULL DEFAULT '{{}}',
    creado_en    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usuarios (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario               TEXT NOT NULL UNIQUE,
    nombre                TEXT NOT NULL,
    rol                   TEXT NOT NULL CHECK(rol IN ('admin','operador')),
    password_salt         TEXT,
    password_hash         TEXT,
    activo                INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0,1)),
    requiere_cambio_clave INTEGER NOT NULL DEFAULT 0 CHECK(requiere_cambio_clave IN (0,1)),
    creado_en             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sesiones (
    token       TEXT PRIMARY KEY,
    usuario_id  INTEGER NOT NULL,
    creado_en   TEXT NOT NULL,
    expira_en   TEXT NOT NULL,
    FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_empleados_area      ON empleados(area, activo);
CREATE INDEX IF NOT EXISTS idx_solicitudes_persona ON solicitudes(empleado_id, estado);
CREATE INDEX IF NOT EXISTS idx_solicitudes_fechas  ON solicitudes(fecha_inicio, fecha_fin);
CREATE INDEX IF NOT EXISTS idx_asignaciones_persona ON asignaciones(empleado_id);
CREATE INDEX IF NOT EXISTS idx_horarios_periodo    ON horarios(anio, mes);
CREATE INDEX IF NOT EXISTS idx_horarios_grupo      ON horarios(grupo_id);
CREATE INDEX IF NOT EXISTS idx_horarios_oficial    ON horarios(anio, mes, oficial);
CREATE INDEX IF NOT EXISTS idx_ajustes_fecha       ON ajustes_manuales(fecha, activo);
CREATE INDEX IF NOT EXISTS idx_asignaciones_grupo  ON asignaciones(grupo_id);
CREATE INDEX IF NOT EXISTS idx_historial_fecha     ON historial(creado_en DESC);
CREATE INDEX IF NOT EXISTS idx_periodos_sucio      ON periodos(sucio, anio, mes);
CREATE INDEX IF NOT EXISTS idx_historial_persona
    ON empleados_historial(empleado_id, vigente_desde);
"""


def _columnas_que_faltan(conexion: sqlite3.Connection) -> None:
    """Columnas añadidas después, para una base que ya existe.

    `CREATE TABLE IF NOT EXISTS` no toca una tabla que ya está, así que una base
    de la oficina se quedaría sin las columnas nuevas y seguiría fallando igual.
    Se añaden de una en una y solo si faltan: no se reescribe ni se borra nada.
    """
    faltantes = {
        'solicitudes': (('hora_inicio', 'TEXT'), ('hora_fin', 'TEXT')),
        'empleados_historial': (('grupo', 'TEXT'),),
        'empleados': (('origen_siembra', 'TEXT'),),
    }
    for tabla, columnas in faltantes.items():
        puestas = {fila[1] for fila in
                   conexion.execute(f'PRAGMA table_info({tabla})').fetchall()}
        for nombre, tipo in columnas:
            if nombre not in puestas:
                conexion.execute(f'ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}')


def crear(conexion: sqlite3.Connection) -> None:
    """Deja la base con su forma definitiva. Se puede llamar siempre."""
    conexion.executescript(ESQUEMA)
    _columnas_que_faltan(conexion)
    conexion.execute(
        'INSERT OR REPLACE INTO configuracion(clave, valor) VALUES(?, ?)',
        ('version_esquema', str(VERSION_ESQUEMA)))
    conexion.commit()


def tablas() -> tuple[str, ...]:
    """Los nombres de las tablas que declara este esquema."""
    import re
    return tuple(re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', ESQUEMA))


def columnas_de(conexion: sqlite3.Connection, tabla: str) -> tuple[str, ...]:
    return tuple(str(f['name']) for f in
                 conexion.execute(f'PRAGMA table_info({tabla})').fetchall())
