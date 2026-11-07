"""Base de datos SQLite que simula el sistema de agendas de la IPS."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import config

ESQUEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sedes (
    id TEXT PRIMARY KEY,               -- código de habilitación REPS (dato real)
    nombre_reps TEXT NOT NULL,         -- nombre tal cual aparece en el REPS
    nombre TEXT NOT NULL,              -- nombre corto para decir en voz alta
    tipo TEXT NOT NULL,                -- UH = unidad hospitalaria, CS = centro de salud
    uh_referencia TEXT,                -- unidad hospitalaria más cercana (calculada con coordenadas reales)
    direccion TEXT,
    direccion_hablada TEXT,
    telefono TEXT,
    comuna TEXT,                       -- MEData (Alcaldía de Medellín)
    barrio TEXT,
    latitud REAL,
    longitud REAL
);

CREATE TABLE IF NOT EXISTS especialidades (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    disponible INTEGER NOT NULL,
    solo_unidad_hospitalaria INTEGER NOT NULL,
    requiere_orden INTEGER NOT NULL,
    duracion_min INTEGER NOT NULL,
    dias_espera_objetivo INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS profesionales (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    genero TEXT NOT NULL,              -- F / M
    especialidad TEXT NOT NULL REFERENCES especialidades(codigo),
    sede_id TEXT NOT NULL REFERENCES sedes(id)
);

CREATE TABLE IF NOT EXISTS pacientes (
    id INTEGER PRIMARY KEY,
    tipo_documento TEXT NOT NULL DEFAULT 'CC',
    documento TEXT NOT NULL UNIQUE,
    nombres TEXT NOT NULL,
    apellidos TEXT NOT NULL,
    sexo TEXT NOT NULL,
    fecha_nacimiento TEXT NOT NULL,
    telefono TEXT,
    eps TEXT NOT NULL,
    regimen TEXT NOT NULL,
    sede_id TEXT NOT NULL REFERENCES sedes(id)   -- sede donde está adscrito
);

CREATE TABLE IF NOT EXISTS ordenes (
    id INTEGER PRIMARY KEY,
    paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
    especialidad TEXT NOT NULL REFERENCES especialidades(codigo),
    fecha_emision TEXT NOT NULL,
    vigente_hasta TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activa'          -- activa | usada | vencida
);

CREATE TABLE IF NOT EXISTS cupos (
    id INTEGER PRIMARY KEY,
    profesional_id INTEGER NOT NULL REFERENCES profesionales(id),
    sede_id TEXT NOT NULL REFERENCES sedes(id),
    especialidad TEXT NOT NULL,
    inicio TEXT NOT NULL,                          -- ISO local, America/Bogota
    fin TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'libre'           -- libre | ocupado
);
CREATE INDEX IF NOT EXISTS ix_cupos_busqueda ON cupos(especialidad, estado, sede_id, inicio);

CREATE TABLE IF NOT EXISTS citas (
    id INTEGER PRIMARY KEY,
    paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
    cupo_id INTEGER NOT NULL REFERENCES cupos(id),
    especialidad TEXT NOT NULL,
    sede_id TEXT NOT NULL,
    profesional_id INTEGER NOT NULL,
    inicio TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'programada',     -- programada | cancelada | reprogramada | atendida
    canal TEXT NOT NULL,                           -- telegram | whatsapp | consola | call_center | sistema
    orden_id INTEGER REFERENCES ordenes(id),
    creada_en TEXT NOT NULL,
    modificada_en TEXT
);
CREATE INDEX IF NOT EXISTS ix_citas_paciente ON citas(paciente_id, estado, inicio);

CREATE TABLE IF NOT EXISTS canal_usuarios (
    canal TEXT NOT NULL,
    usuario_id TEXT NOT NULL,
    paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
    vinculado_en TEXT NOT NULL,
    PRIMARY KEY (canal, usuario_id)
);

CREATE TABLE IF NOT EXISTS eventos (               -- bitácora para medir el MVP
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    canal TEXT NOT NULL,
    usuario_id TEXT NOT NULL,
    paciente_id INTEGER,
    estado TEXT,
    intencion TEXT,
    fuente_nlu TEXT,
    es_voz INTEGER,
    texto_usuario TEXT,
    respuesta TEXT,
    resultado TEXT                                 -- cita_agendada | cita_cancelada | humano | urgencia | ...
);

CREATE TABLE IF NOT EXISTS metadatos (clave TEXT PRIMARY KEY, valor TEXT);
"""


def conectar(ruta: Path | str | None = None) -> sqlite3.Connection:
    ruta = Path(ruta or config.db_path)
    con = sqlite3.connect(ruta, check_same_thread=False, isolation_level=None)  # autocommit; transacciones explícitas
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def crear_esquema(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA)
