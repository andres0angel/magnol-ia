"""Métricas del MVP a partir de la bitácora de conversaciones (tabla eventos).

    python scripts/metricas.py
    python scripts/metricas.py --desde 2026-11-15 --csv metricas.csv

Indicadores pensados para validar la hipótesis de Magnol-IA con usuarios reales:
- tasa de éxito: de quienes intentaron agendar, cuántos terminaron con cita
- turnos y minutos hasta agendar (¿es más rápido que el call center?)
- % de turnos no entendidos y escalamientos a una persona
- % de mensajes por voz y cuánto resolvieron las reglas vs. el LLM
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from magnolia.config import config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(config.db_path))
    ap.add_argument("--desde", help="AAAA-MM-DD")
    ap.add_argument("--canal", help="telegram | whatsapp | consola")
    ap.add_argument("--csv")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    filtros, params = ["1=1"], []
    if args.desde:
        filtros.append("ts >= ?")
        params.append(args.desde)
    if args.canal:
        filtros.append("canal = ?")
        params.append(args.canal)
    eventos = con.execute(f"SELECT * FROM eventos WHERE {' AND '.join(filtros)} ORDER BY canal, usuario_id, ts", params).fetchall()
    if not eventos:
        print("Todavía no hay conversaciones registradas.")
        return

    # Una "sesión" = turnos del mismo usuario separados por menos de 30 minutos
    sesiones, actual, previo = [], [], None
    for e in eventos:
        ts = datetime.fromisoformat(e["ts"])
        if previo and (e["usuario_id"] != previo["usuario_id"] or e["canal"] != previo["canal"]
                       or (ts - datetime.fromisoformat(previo["ts"])).total_seconds() > 1800):
            sesiones.append(actual)
            actual = []
        actual.append(e)
        previo = e
    sesiones.append(actual)

    resultados = Counter(e["resultado"] for e in eventos if e["resultado"])
    intenciones = Counter(e["intencion"] for e in eventos)
    fuentes = Counter(e["fuente_nlu"] for e in eventos)
    con_agendar = [s for s in sesiones if any(e["intencion"] == "agendar" for e in s)]
    exitosas = [s for s in con_agendar if any(e["resultado"] == "cita_agendada" for e in s)]
    turnos_exito, minutos_exito = [], []
    for s in exitosas:
        idx = next(n for n, e in enumerate(s) if e["resultado"] == "cita_agendada")
        turnos_exito.append(idx + 1)
        minutos_exito.append((datetime.fromisoformat(s[idx]["ts"]) - datetime.fromisoformat(s[0]["ts"])).total_seconds() / 60)

    n = len(eventos)
    filas = [
        ("Sesiones", len(sesiones)),
        ("Personas distintas", len({(e["canal"], e["usuario_id"]) for e in eventos})),
        ("Turnos (mensajes de usuarios)", n),
        ("% de mensajes por voz", f"{100 * sum(e['es_voz'] or 0 for e in eventos) / n:.1f} %"),
        ("Citas agendadas", resultados["cita_agendada"]),
        ("Citas canceladas (cupos liberados)", resultados["cita_cancelada"]),
        ("Citas reprogramadas", resultados["cita_reprogramada"]),
        ("Tasa de éxito al agendar", f"{100 * len(exitosas) / len(con_agendar):.1f} %" if con_agendar else "—"),
        ("Turnos promedio hasta agendar", f"{statistics.mean(turnos_exito):.1f}" if turnos_exito else "—"),
        ("Minutos promedio hasta agendar", f"{statistics.mean(minutos_exito):.1f}" if minutos_exito else "—"),
        ("% turnos no entendidos", f"{100 * resultados['no_entendido'] / n:.1f} %"),
        ("Pidieron hablar con una persona", resultados["humano"]),
        ("Alertas de urgencia", resultados["urgencia"]),
        ("Sin cupos disponibles", resultados["sin_cupos"]),
        ("Comprensión por reglas / híbrido (LLM)", f"{fuentes['reglas']} / {fuentes['hibrido'] + fuentes['llm']}"),
    ]
    print("Métricas del MVP de Magnol-IA")
    for k, v in filas:
        print(f"  {k:<42} {v}")
    print("  Intenciones más frecuentes:", ", ".join(f"{k} ({v})" for k, v in intenciones.most_common(6)))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["indicador", "valor"])
            w.writerows(filas)


if __name__ == "__main__":
    main()
