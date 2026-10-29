"""Deep live checks for ordini.gruaro + admin diagnose."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:5000"


def login(user: str, pwd: str) -> tuple[requests.Session, requests.Response]:
    s = requests.Session()
    page = s.get(BASE + "/login", timeout=10)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert tok, "csrf missing"
    r = s.post(
        BASE + "/login",
        data={"username": user, "password": pwd, "csrf_token": tok.group(1)},
        allow_redirects=True,
        timeout=10,
    )
    return s, r


def main() -> None:
    s, r = login("admin", "Admin2026!!")
    print("admin_url", r.url)
    if "/login" in r.url and "credenzial" in r.text.lower():
        print("FAIL admin_login")
        sys.exit(1)
    print("PASS admin_login")
    if "/change-password" not in r.url:
        for name, cond in [
            ("admin_has_import", 'href="/import"' in r.text),
            ("admin_has_utenti", "/admin/utenti" in r.text),
            ("admin_has_impostazioni", "/admin/impostazioni" in r.text),
        ]:
            print(("PASS" if cond else "FAIL"), name)
        imp = s.get(BASE + "/admin/impostazioni", timeout=10)
        print(
            ("PASS" if imp.status_code == 200 and "csrf_token" in imp.text else "FAIL"),
            "admin_impostazioni_page",
        )
        # SMTP password must not be prefilled in clear
        pwd_prefill = bool(re.search(r'name="smtp_password"[^>]*value="[^"]+', imp.text))
        print(("PASS" if not pwd_prefill else "FAIL"), "smtp_password_not_prefilled")
    s.get(BASE + "/logout", timeout=10)

    s, r = login("ordini.gruaro", "OrdiniGruaro2026!")
    print("ordini_url", r.url)
    t = r.text
    checks = [
        ("has_gruaro", "Gruaro" in t),
        ("has_marghera", "Marghera" in t),
        ("has_villorba", "Villorba" in t),
        ("has_tutte_or_entrambe", "Tutte" in t or "Entrambe" in t),
        ("no_nuovo_href", 'href="/prodotti/nuovo"' not in t),
        ("no_import_href", 'href="/import"' not in t),
        ("has_invia_or_alert", "invia" in t.lower() or "alert" in t.lower()),
        ("dates_ddmmyyyy", bool(re.search(r"\d{2}/\d{2}/\d{4}", t))),
        ("csrf_in_forms", "csrf_token" in t),
    ]
    fails = 0
    for name, cond in checks:
        print(("PASS" if cond else "FAIL"), name)
        if not cond:
            fails += 1

    r2 = s.get(BASE + "/?filiale=all", timeout=10)
    print(
        "filiale_all",
        r2.status_code,
        "Marghera=" + str("Marghera" in r2.text),
        "Gruaro=" + str("Gruaro" in r2.text),
    )

    r3 = s.get(BASE + "/profilo-email", timeout=10)
    print(
        "profilo_email",
        r3.status_code,
        "ok=" + str(r3.status_code == 200 and "csrf_token" in r3.text),
    )

    for path in ["/admin/impostazioni", "/admin/utenti", "/import", "/prodotti/nuovo"]:
        rr = s.get(BASE + path, allow_redirects=False, timeout=10)
        blocked = rr.status_code in (302, 303, 403)
        print(("PASS" if blocked else "FAIL"), "denied", path, rr.status_code, rr.headers.get("Location"))
        if not blocked:
            fails += 1

    # click filiale chip simulation
    from app.database import list_filiali

    filiali = list_filiali()
    if filiali:
        fid = filiali[0]["id"]
        rr = s.get(f"{BASE}/?filiale={fid}", timeout=10)
        print("filiale_filter", fid, filiali[0]["nome"], rr.status_code, len(rr.text))

    if fails:
        print("DEEP_FAIL", fails)
        sys.exit(1)
    print("DEEP_OK")


if __name__ == "__main__":
    main()
