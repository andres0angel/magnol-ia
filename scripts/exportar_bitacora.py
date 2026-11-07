"""Exporta las conversaciones de las pruebas a un CSV para revisarlas y etiquetarlas en Excel o Google Sheets.

    python scripts/exportar_bitacora.py                       # datos/bitacoras/bitacora_AAAAMMDD_HHMM.csv
    python scripts/exportar_bitacora.py --salida pruebas.csv --sin-consola

Las columnas intencion_correcta, entendio_bien y comentario quedan vacías para llenarlas al revisar.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from magnolia.bitacora import exportar  # noqa: E402
from magnolia.config import config  # noqa: E402
from magnolia.db import conectar  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(config.db_path))
    ap.add_argument("--salida", default=str(RAIZ / "datos" / "bitacoras" / f"bitacora_{datetime.now():%Y%m%d_%H%M}.csv"))
    ap.add_argument("--sin-consola", action="store_true", help="excluir pruebas hechas en la consola o el cuaderno")
    args = ap.parse_args()
    if not Path(args.db).exists():
        sys.exit("No existe la base de datos. Genérela con: python scripts/generar_datos.py")
    n = exportar(conectar(args.db), args.salida, incluir_consola=not args.sin_consola)
    print(f"{n} turnos exportados a {args.salida}" if n else "Todavía no hay conversaciones registradas.")


if __name__ == "__main__":
    main()
