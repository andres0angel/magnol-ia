"""Reparte pacientes de prueba entre varias personas para que no se pisen al probar el mismo bot.

Si dos personas usan la misma cédula, la cita que agenda una le aparece a la otra. Este script le da a cada
persona su propio juego de pacientes, uno por escenario, sacados de la base generada:

    python scripts/cedulas_prueba.py               # 5 personas
    python scripts/cedulas_prueba.py --personas 8 --markdown > cedulas.md

Las 3 cédulas de demostración (43527891, 8345678 y 32456789) quedan reservadas para la demo en clase.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from magnolia.catalogo import nombre as nombre_especialidad  # noqa: E402
from magnolia.config import config  # noqa: E402
from magnolia.db import conectar  # noqa: E402

DEMO = ("43527891", "8345678", "32456789")


def edad(nacimiento: str, hoy: date) -> int:
    n = date.fromisoformat(nacimiento)
    return hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))


def escenarios(con, hoy: date, ahora: str) -> dict[str, list]:
    base = ("SELECT p.*, s.nombre AS sede FROM pacientes p JOIN sedes s ON s.id = p.sede_id "
            f"WHERE p.documento NOT IN ({','.join('?' * len(DEMO))}) ")
    futuras = "(SELECT count(*) FROM citas c WHERE c.paciente_id = p.id AND c.estado = 'programada' AND c.inicio >= ?)"
    activas = "(SELECT count(*) FROM ordenes o WHERE o.paciente_id = p.id AND o.estado = 'activa' AND o.vigente_hasta >= ?)"
    desde_cero = con.execute(base + f"AND {futuras} = 0 AND {activas} = 0 ORDER BY p.id", (*DEMO, ahora, hoy.isoformat())).fetchall()
    con_cita = con.execute(base + f"AND {futuras} = 1 ORDER BY p.id", (*DEMO, ahora)).fetchall()
    con_orden = con.execute(base + f"AND {activas} >= 1 AND {futuras} = 0 ORDER BY p.id", (*DEMO, hoy.isoformat(), ahora)).fetchall()
    return {"desde_cero": desde_cero, "con_cita": con_cita, "con_orden": con_orden}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--personas", type=int, default=5)
    ap.add_argument("--markdown", action="store_true", help="tabla en Markdown para pegar en un documento")
    ap.add_argument("--db", default=str(config.db_path))
    args = ap.parse_args()
    if not Path(args.db).exists():
        sys.exit("No existe la base de datos. Genérela con: python scripts/generar_datos.py")
    con = conectar(args.db)
    hoy = config.hoy()
    ahora = datetime.combine(hoy, datetime.min.time()).isoformat(timespec="minutes")
    grupos = escenarios(con, hoy, ahora)
    paso = max(1, min(len(v) for v in grupos.values()) // max(args.personas, 1))

    filas = []
    for i in range(args.personas):
        for clave, lista in grupos.items():
            if i * paso >= len(lista):
                continue
            p = lista[i * paso]
            trato = "doña" if p["sexo"] == "F" else "don"
            if clave == "desde_cero":
                prueba = "Agendar desde cero (medicina general u odontología); pedir otro día o 'por la tarde'"
            elif clave == "con_cita":
                c = con.execute("SELECT especialidad, inicio FROM citas WHERE paciente_id=? AND estado='programada' "
                                "AND inicio>=? ORDER BY inicio", (p["id"], ahora)).fetchone()
                prueba = (f"Ya tiene cita de {nombre_especialidad(c['especialidad'])} el {c['inicio'][:10]}: "
                          "preguntar cuándo es, cambiarla y cancelarla")
            else:
                o = con.execute("SELECT especialidad FROM ordenes WHERE paciente_id=? AND estado='activa' ORDER BY id",
                                (p["id"],)).fetchone()
                prueba = f"Tiene orden de {nombre_especialidad(o['especialidad'])}: pedir esa cita con el especialista"
            filas.append((f"Persona {i + 1}", p["documento"], f"{trato} {p['nombres']} {p['apellidos']}",
                          edad(p["fecha_nacimiento"], hoy), p["sede"], prueba))

    if args.markdown:
        print("| Quién | Cédula | Paciente | Edad | Sede | Qué probar |")
        print("|---|---|---|---|---|---|")
        for f in filas:
            print("| " + " | ".join(str(x) for x in f) + " |")
        return
    actual = None
    for quien, doc, nombre, anios, sede, prueba in filas:
        if quien != actual:
            print(f"\n{quien}")
            actual = quien
        print(f"  {doc:>10}  {nombre} ({anios} años, {sede})\n              → {prueba}")
    print("\nReservadas para la demo en clase: 43527891 (doña María Ofelia), 8345678 (don José Aníbal), "
          "32456789 (doña Rosa Elena).")


if __name__ == "__main__":
    main()
