"""Test import flessibile su Excel reali."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import init_db, list_prodotti, get_filiale_by_name
from app.excel_import import import_excel, preview_excel, _extract_dates
from app.paths import ensure_dirs

BASE = Path(r"\\172.17.17.11\supporto-tecnico\Vari Excel\primo soccorso")
FILES = [
    (BASE / "monitoraggio_scadenze_cassette.xlsx", "Gruaro"),
    (BASE / "CASSETTA SHOWROOM.xlsx", "Gruaro"),
    (BASE / "CASSETTA MAGAZZINO.xlsx", "Gruaro"),
]
marghera = Path(r"c:\Users\enrico.patres\Desktop\PRONTO SOCCORSO IVAN.xlsx")
if marghera.exists():
    FILES.append((marghera, "Marghera"))


def main() -> None:
    # unit check date bug
    dates = _extract_dates("01/04/2027 (2)\n10/12/2028 (1)\n15/12/2029 (2)")
    assert min(dates).isoformat() == "2027-04-01", dates
    print("OK date parse", dates)

    ensure_dirs()
    init_db()
    for path, filiale in FILES:
        print("\n" + "=" * 60)
        print("FILE", path.name)
        prev = preview_excel(path)
        print("preview", prev)
        result = import_excel(path, filiale_nome=filiale, replace=True)
        print("import", result)
        f = get_filiale_by_name(filiale)
        ps = list_prodotti(f["id"])
        guanti = next((p for p in ps if "GUANTI" in p["nome"].upper()), None)
        print(f"  DB {filiale}: {len(ps)} prodotti")
        if guanti:
            print(f"  GUANTI scad={guanti.get('scadenza')} non_scade={guanti.get('non_scade')}")
            year = int(str(guanti.get("scadenza") or "9999")[:4])
            assert year >= 2020, guanti
        visiera = next((p for p in ps if "VISIERA" in p["nome"].upper()), None)
        if visiera:
            print(f"  VISIERA non_scade={visiera.get('non_scade')} scad={visiera.get('scadenza')}")
            assert visiera.get("non_scade") in (1, True) or visiera.get("scadenza") is None


if __name__ == "__main__":
    main()
    print("\nALL OK")
