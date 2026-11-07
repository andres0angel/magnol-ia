"""Exporta la bitácora de conversaciones (tabla eventos) a CSV, lista para revisar y etiquetar.

Cada fila es un turno: lo que dijo la persona, cómo lo entendió el bot y qué respondió. Las tres columnas
del final quedan vacías para que el equipo las llene al revisar las pruebas con usuarios:
  - intencion_correcta: la intención real (agendar, consultar, cancelar, cambiar, afirmar, negar, ...)
  - entendio_bien: si / no
  - comentario
Las frases mal entendidas se agregan después a datos/pruebas/frases_adultos_mayores.csv para medir y mejorar.

El identificador de Telegram o WhatsApp se reemplaza por un código anónimo (Ley 1581 de 2012).
"""
from __future__ import annotations

import csv
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

COLUMNAS = ["ts", "canal", "persona", "paciente_id", "estado", "intencion", "fuente_nlu", "es_voz",
            "texto_usuario", "respuesta", "resultado", "intencion_correcta", "entendio_bien", "comentario"]


def _anonimo(canal: str, usuario_id: str) -> str:
    return canal[:2] + "-" + hashlib.sha256(f"{canal}:{usuario_id}".encode()).hexdigest()[:8]


def contar(con: sqlite3.Connection) -> int:
    try:
        return con.execute("SELECT count(*) FROM eventos").fetchone()[0]
    except sqlite3.Error:
        return 0


def exportar(con: sqlite3.Connection, destino: Path | str, incluir_consola: bool = True) -> int:
    """Escribe la bitácora en destino (CSV UTF-8 con BOM para que Excel muestre bien las tildes)."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    filtro = "" if incluir_consola else "WHERE canal NOT IN ('consola', 'prueba')"
    filas = con.execute(f"SELECT * FROM eventos {filtro} ORDER BY canal, usuario_id, ts").fetchall()
    with open(destino, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS)
        for e in filas:
            w.writerow([e["ts"], e["canal"], _anonimo(e["canal"], e["usuario_id"]), e["paciente_id"], e["estado"],
                        e["intencion"], e["fuente_nlu"], e["es_voz"], e["texto_usuario"], e["respuesta"],
                        e["resultado"], "", "", ""])
    return len(filas)


def respaldar_si_hay(ruta_db: Path, carpeta: Path) -> Path | None:
    """Antes de borrar una base, guarda su bitácora si tiene conversaciones. Devuelve la ruta del respaldo."""
    if not ruta_db.exists():
        return None
    con = sqlite3.connect(ruta_db)
    con.row_factory = sqlite3.Row
    try:
        if contar(con) == 0:
            return None
        destino = carpeta / f"bitacora_{datetime.now():%Y%m%d_%H%M%S}.csv"
        exportar(con, destino)
        return destino
    finally:
        con.close()
