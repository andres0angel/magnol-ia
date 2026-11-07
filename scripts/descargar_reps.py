"""Descarga sedes del REPS (Registro Especial de Prestadores, Minsalud) desde datos.gov.co.

El repositorio ya trae las 54 sedes de Metrosalud en Medellín (corte REPS 12-mar-2026). Use este script
para actualizarlas o para simular otra IPS (cambie --prestador). Conjunto: c36g-9fc2 (76.821 sedes).

    python scripts/descargar_reps.py
    python scripts/descargar_reps.py --prestador "HOSPITAL PABLO TOBON" --municipio "MEDELLÍN" --salida datos/reales/otra_ips.csv

Si cambia de IPS, actualice también datos/catalogos/sedes_atributos.csv (nombre corto, tipo de sede y
unidad hospitalaria de referencia de cada sede).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
URL = "https://www.datos.gov.co/resource/c36g-9fc2.json"
COLUMNAS = {
    "codigohabilitacionsede": "codigo_habilitacion_sede", "nombresede": "nombre_sede", "direcci_nsede": "direccion_sede",
    "t_lefonosede": "telefono_sede", "municipiosededesc": "municipio", "nombreprestador": "prestador",
    "fecha_corte_reps": "fecha_corte_reps",
}


def consulta(prestador: str, municipio: str | None) -> dict:
    donde = f"upper(nombreprestador) like '%{prestador.upper().replace(chr(39), '')}%'"
    if municipio:
        donde += f" AND upper(municipiosededesc) = '{municipio.upper().replace(chr(39), '')}'"
    return {"$where": donde, "$select": ",".join(COLUMNAS), "$limit": 5000, "$order": "codigohabilitacionsede"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prestador", default="METROSALUD")
    ap.add_argument("--municipio", default="MEDELLÍN")
    ap.add_argument("--salida", default=str(RAIZ / "datos" / "reales" / "reps_sedes_metrosalud_medellin.csv"))
    args = ap.parse_args()
    try:
        r = httpx.get(URL, params=consulta(args.prestador, args.municipio), timeout=60)
        r.raise_for_status()
    except httpx.HTTPError as e:
        sys.exit(f"No se pudo descargar del portal de datos abiertos: {e}")
    filas = r.json()
    if not filas:
        sys.exit("La consulta no devolvió sedes. Revise el nombre del prestador y el municipio.")
    with open(args.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS.values())
        for fila in filas:
            valores = [fila.get(c, "") for c in COLUMNAS]
            valores[-1] = valores[-1].replace("Fecha corte REPS:", "").strip()
            w.writerow(valores)
    print(f"{len(filas)} sedes guardadas en {args.salida}")


if __name__ == "__main__":
    main()
