"""Verifica setup DB, utenti, autenticazione e import."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import init_db, list_filiali, list_utenti, authenticate, prodotti_in_alert
from app.excel_import import import_excel

init_db()

print("filiali:", [dict(r)["nome"] for r in list_filiali()])

utenti = list_utenti()
print(f"{len(utenti)} utenti:")
for u in utenti:
    un = u["username"]
    ru = u["ruolo"]
    fn = u.get("filiale_nome") or "-"
    print(f"  {un:20s} ruolo={ru:25s} filiale={fn}")

admin = authenticate("admin", "admin")
print(f"login admin: {bool(admin)}")

gruaro_u = authenticate("gruaro", "gruaro")
print(f"login gruaro: {bool(gruaro_u)}, ruolo={gruaro_u['ruolo'] if gruaro_u else None}")

ordini = authenticate("ordini.gruaro", "ordini.gruaro")
print(f"login ordini.gruaro: {bool(ordini)}, ruolo={ordini['ruolo'] if ordini else None}")

res = import_excel(r"c:\Users\enrico.patres\Desktop\PRONTO SOCCORSO IVAN.xlsx", "Marghera")
print(f"import: {res['importati']} prodotti in {res['filiale']}")

print(f"alert 10gg: {len(prodotti_in_alert(10))}")
print(f"alert 60gg: {len(prodotti_in_alert(60))}")
print("ALL OK")
