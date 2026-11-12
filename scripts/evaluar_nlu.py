"""Evalúa la comprensión (reglas y, si hay clave, LLM) contra frases etiquetadas de adultos mayores.

Uso:
    python scripts/evaluar_nlu.py                 # reglas, todas las frases
    python scripts/evaluar_nlu.py --split prueba  # solo el conjunto de prueba
    python scripts/evaluar_nlu.py --motor llm     # requiere LLM_API_KEY en .env
    python scripts/evaluar_nlu.py --errores       # muestra cada error
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from magnolia.nlu import reglas  # noqa: E402

HOY = date(2026, 11, 12)  # jueves; el lunes 16 es festivo
CAMPOS = ["especialidad", "fecha", "franja", "opcion", "documento"]


def _pred_campo(interp, campo: str) -> str:
    if campo == "fecha":
        return "asap" if interp.asap else (interp.fecha.isoformat() if interp.fecha else "")
    valor = getattr(interp, campo)
    return "" if valor is None else str(valor)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=["todas", "desarrollo", "prueba", "posterior", "entrevistas", "real"], default="todas")
    p.add_argument("--motor", choices=["reglas", "llm", "hibrido"], default="reglas")
    p.add_argument("--errores", action="store_true")
    p.add_argument("--csv", help="guardar resultados detallados en este CSV")
    args = p.parse_args()

    if args.motor == "reglas":
        motor = lambda frase, ctx: reglas.interpretar(frase, ctx, HOY)  # noqa: E731
    else:
        from magnolia.nlu import hibrido, llm
        if args.motor == "llm":
            motor = lambda frase, ctx: llm.interpretar(frase, ctx, HOY) or reglas.interpretar(frase, ctx, HOY)  # noqa: E731
        else:
            motor = lambda frase, ctx: hibrido.interpretar(frase, ctx, HOY)  # noqa: E731

    with open(RAIZ / "datos" / "pruebas" / "frases_adultos_mayores.csv", encoding="utf-8") as f:
        filas = [r for r in csv.DictReader(f) if args.split == "todas" or r["split"] == args.split]

    aciertos_int = 0
    aciertos_campo = Counter()
    total_campo = Counter()
    errores = []
    detalle = []
    for fila in filas:
        interp = motor(fila["frase"], fila["contexto"])
        ok_int = interp.intencion == fila["intencion"]
        aciertos_int += ok_int
        fallos = [] if ok_int else [f"intención: {interp.intencion} ≠ {fila['intencion']}"]
        for campo in CAMPOS:
            esperado, obtenido = fila[campo], _pred_campo(interp, campo)
            total_campo[campo] += 1
            if esperado == obtenido:
                aciertos_campo[campo] += 1
            else:
                fallos.append(f"{campo}: '{obtenido}' ≠ '{esperado}'")
        todo_ok = not fallos
        detalle.append({**fila, "pred_intencion": interp.intencion, "fuente": interp.fuente, "correcto": todo_ok})
        if fallos:
            errores.append((fila["id"], fila["contexto"], fila["frase"], fallos))

    n = len(filas)
    exactas = sum(1 for d in detalle if d["correcto"])
    print(f"Motor: {args.motor} | conjunto: {args.split} | frases: {n}")
    print(f"  Intención correcta:            {aciertos_int}/{n} = {aciertos_int / n:.1%}")
    for campo in CAMPOS:
        print(f"  {campo:<30} {aciertos_campo[campo]}/{total_campo[campo]} = {aciertos_campo[campo] / total_campo[campo]:.1%}")
    print(f"  Frase 100% correcta:           {exactas}/{n} = {exactas / n:.1%}")
    if args.errores:
        print("\nErrores:")
        for id_, ctx, frase, fallos in errores:
            print(f"  [{id_}] ({ctx}) «{frase}» -> {'; '.join(fallos)}")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(detalle[0].keys()))
            w.writeheader()
            w.writerows(detalle)


if __name__ == "__main__":
    main()
