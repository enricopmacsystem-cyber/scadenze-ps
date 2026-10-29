"""Test import Gruaro Showroom/Magazzino + date corrette."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import (
    init_db,
    list_prodotti,
    get_filiale_by_name,
    list_filiali,
)
from app.excel_import import import_excel, preview_excel, _extract_dates
from app.paths import ensure_dirs

BASE = Path(r"\\172.17.17.11\supporto-tecnico\Vari Excel\primo soccorso")


def main() -> None:
    dates = _extract_dates("15/12/2029 (3)    30/06/2027 (1)      01/12/2028 (1)")
    assert min(dates).isoformat() == "2027-06-30", dates
    print("OK date nearest", min(dates))

    ensure_dirs()
    init_db()
    nomi = [f["nome"] for f in list_filiali()]
    assert "Gruaro Showroom" in nomi and "Gruaro Magazzino" in nomi
    assert "Gruaro" not in nomi
    print("OK filiali", [n for n in nomi if "Gruaro" in n])

    path = BASE / "monitoraggio_scadenze_cassette.xlsx"
    prev = preview_excel(path)
    print("preview", prev)
    result = import_excel(path, filiale_nome="Gruaro Showroom", replace=True)
    print("import", result)
    assert "Showroom" in result["filiale"] and "Magazzino" in result["filiale"]
    assert result["importati"] == 36

    show = list_prodotti(get_filiale_by_name("Gruaro Showroom")["id"], "fissa")
    maga = list_prodotti(get_filiale_by_name("Gruaro Magazzino")["id"], "fissa")
    print(f"Showroom={len(show)} Magazzino={len(maga)}")
    assert len(show) == 18 and len(maga) == 18

    guanti_s = next(p for p in show if "GUANTI" in p["nome"].upper())
    guanti_m = next(p for p in maga if "GUANTI" in p["nome"].upper())
    print("GUANTI Showroom", guanti_s["scadenza"])
    print("GUANTI Magazzino", guanti_m["scadenza"])
    assert guanti_s["scadenza"] == "2027-04-01"
    assert guanti_m["scadenza"] == "2027-06-30"

    # file singoli
    r2 = import_excel(BASE / "CASSETTA SHOWROOM.xlsx", replace=True)
    print("showroom file", r2)
    assert r2["filiale"] == "Gruaro Showroom"
    assert get_filiale_by_name("Gruaro Magazzino") and len(
        list_prodotti(get_filiale_by_name("Gruaro Magazzino")["id"], "fissa")
    ) == 18  # non toccato dal replace showroom-only... wait replace deletes showroom only

    r3 = import_excel(BASE / "CASSETTA MAGAZZINO.xlsx", replace=True)
    print("magazzino file", r3)
    assert "Magazzino" in r3["filiale"]

    print("\nALL OK")


if __name__ == "__main__":
    main()
