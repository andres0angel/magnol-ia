"""Une las fuentes REALES de las sedes de Metrosalud en un solo archivo georreferenciado.

Fuentes (todas en datos/reales/):
  - reps_sedes_metrosalud_medellin.csv     REPS de Minsalud: código de habilitación, nombre, dirección, teléfono
  - medata_centros_atencion_metrosalud.csv MEData (Alcaldía de Medellín): comuna, barrio, longitud y latitud
  - coordenadas_complementarias.csv        sedes que no están en MEData (UH Buenos Aires, de OpenStreetMap)
  - horarios_sedes_metrosalud.csv          Gobernación de Antioquia (REPS): horario de atención por día

Salidas:
  - datos/reales/sedes_metrosalud_georreferenciadas.csv
  - actualiza las columnas uh_referencia y nota de datos/catalogos/sedes_atributos.csv: cada centro de salud
    queda remitido a la unidad hospitalaria MÁS CERCANA en línea recta (antes era un supuesto por cercanía aproximada).

    python scripts/preparar_sedes.py
"""
from __future__ import annotations

import csv
import math
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REALES = RAIZ / "datos" / "reales"
CATALOGOS = RAIZ / "datos" / "catalogos"
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Nombres de MEData que no coinciden con el nombre corto del catálogo (verificado por dirección)
MEDATA_A_CODIGO = {
    "CS LA QUIEBRA": "050010217845",       # Centro de Salud Luis Javier García, Calle 48DD # 99EE-30
    "CS BELEN ALTAVISTA": "050010217812",  # Centro de Salud Altavista, Calle 18 # 105-15
    "CS LIMONAR": "050010217851",          # Centro de Salud El Limonar
    "CS EL SALVADOR": "050010217818",      # Centro de Salud Salvador, Carrera 36 # 40A-30
    "CS LAS MARGARITAS": "050010217850",   # Centro de Salud Margaritas
    "CS PABLO VI": "050010217834",         # Centro de Salud Pablo Sexto
    "CS CISAMF": "050010217863",           # Centro Integral de Servicios Ambulatorios para la Mujer y la Familia
}


def clave(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"^(uh|cs)\s+", "", t)
    t = re.sub(r"^(unidad hospitalaria|centro de salud)\s+(de\s+)?", "", t)
    return re.sub(r"[^a-z0-9]", "", t)


def nombre_propio(texto: str) -> str:
    menores = {"de", "del", "la", "las", "los", "y"}
    palabras = texto.lower().split()
    return " ".join(p if (i and p in menores) else p.capitalize() for i, p in enumerate(palabras))


def distancia_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def leer(nombre: str, carpeta: Path = REALES) -> list[dict]:
    with open(carpeta / nombre, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    reps = {r["codigo_habilitacion_sede"]: r for r in leer("reps_sedes_metrosalud_medellin.csv")}
    atributos = leer("sedes_atributos.csv", CATALOGOS)
    por_clave = {clave(a["nombre_corto"]): a["codigo_habilitacion_sede"] for a in atributos if a["nombre_corto"]}

    geo: dict[str, dict] = {}
    sin_par = []
    for m in leer("medata_centros_atencion_metrosalud.csv"):
        codigo = MEDATA_A_CODIGO.get(m["centro atención"]) or por_clave.get(clave(m["centro atención"]))
        if not codigo:
            sin_par.append(m["centro atención"])
            continue
        geo[codigo] = dict(comuna=nombre_propio(m["comuna"]), barrio=m["barrio"], latitud=float(m["Latitud"]),
                           longitud=float(m["Longitud"]), fuente_coordenadas="MEData (Alcaldía de Medellín), 2022")
    for c in leer("coordenadas_complementarias.csv"):
        geo[c["codigo_habilitacion_sede"]] = dict(comuna=nombre_propio(c["comuna"]), barrio=c["barrio"], latitud=float(c["Latitud"]),
                                                  longitud=float(c["Longitud"]), fuente_coordenadas=c["fuente"].split(",")[0])
    if sin_par:
        sys.exit(f"Centros de MEData sin código REPS: {sin_par}. Agréguelos a MEDATA_A_CODIGO.")
    horarios = {h["codigo_habilitacion_sede"]: h for h in leer("horarios_sedes_metrosalud.csv")}

    activas = [a for a in atributos if a["ofrece_citas"] == "1"]
    faltan = [a["codigo_habilitacion_sede"] for a in activas if a["codigo_habilitacion_sede"] not in geo]
    if faltan:
        sys.exit(f"Sedes que ofrecen citas sin coordenadas: {faltan}")

    uhs = [a["codigo_habilitacion_sede"] for a in activas if a["tipo"] == "UH"]
    filas = []
    for a in activas:
        cod = a["codigo_habilitacion_sede"]
        g = geo[cod]
        punto = (g["latitud"], g["longitud"])
        if a["tipo"] == "UH":
            uh, km = cod, 0.0
        else:
            uh, km = min(((u, distancia_km(punto, (geo[u]["latitud"], geo[u]["longitud"]))) for u in uhs), key=lambda x: x[1])
        a["uh_referencia"] = uh
        a["nota"] = "" if a["tipo"] == "UH" else f"UH más cercana en línea recta ({km:.1f} km), con coordenadas reales"
        h = horarios.get(cod, {})
        filas.append(dict(codigo_habilitacion_sede=cod, nombre_corto=a["nombre_corto"], tipo=a["tipo"],
                          nombre_reps=reps[cod]["nombre_sede"], direccion=reps[cod]["direccion_sede"],
                          comuna=g["comuna"], barrio=g["barrio"], latitud=g["latitud"], longitud=g["longitud"],
                          fuente_coordenadas=g["fuente_coordenadas"], uh_referencia=uh, distancia_uh_km=round(km, 2),
                          **{f"horario_{d}": h.get(f"horario_{d}", "Sin Dato") for d in DIAS}))

    salida = REALES / "sedes_metrosalud_georreferenciadas.csv"
    with open(salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    with open(CATALOGOS / "sedes_atributos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(atributos[0].keys()))
        w.writeheader()
        w.writerows(atributos)

    lejos = sorted((f for f in filas if f["tipo"] == "CS"), key=lambda f: -f["distancia_uh_km"])[:3]
    print(f"{len(filas)} sedes georreferenciadas en {salida.relative_to(RAIZ)}")
    print("Centros de salud más lejos de su unidad hospitalaria: "
          + "; ".join(f"{f['nombre_corto']} ({f['distancia_uh_km']} km)" for f in lejos))


if __name__ == "__main__":
    main()
