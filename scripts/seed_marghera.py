#!/usr/bin/env python3
"""Importa i dati Marghera dal file Excel iniziale e prepara il database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import init_db
from app.excel_import import import_excel
from app.paths import ensure_dirs


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed database Scadenze PS")
    parser.add_argument(
        "excel",
        nargs="?",
        default=r"c:\Users\enrico.patres\Desktop\PRONTO SOCCORSO IVAN.xlsx",
        help="Percorso file Excel da importare",
    )
    args = parser.parse_args()
    ensure_dirs()
    init_db()
    result = import_excel(args.excel, filiale_nome="Marghera", replace=True)
    print(f"OK: {result['importati']} prodotti importati in {result['filiale']}")


if __name__ == "__main__":
    main()
