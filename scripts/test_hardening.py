"""Smoke test hardening."""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import authenticate, get_prodotto, init_db, list_prodotti, list_utenti, update_utente
from app.email_alerts import collect_alert_recipients, smtp_ready
from app.settings import get_smtp_password_plain, load_settings
from app.webapp import _validate_excel_upload, create_app


class _FakeUpload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self.stream = io.BytesIO(data)


def main() -> None:
    init_db()
    for u in list_utenti():
        email = (u.get("email") or "")
        if u["username"] == "ordini.gruaro" and email.endswith("@example.com"):
            update_utente(u["id"], email=None)
            print("cleared placeholder email")

    s = load_settings()
    plain = get_smtp_password_plain(s)
    stored = str((s.get("smtp") or {}).get("password") or "")
    print("smtp_encrypted", stored.startswith("enc:v1:"))
    print("smtp_plain_len", len(plain))
    print("recipients", collect_alert_recipients(s))
    print("smtp_ready", smtp_ready(s))

    u = authenticate("villorba", "Villorba2026!")
    assert u, "villorba auth failed"
    print("villorba_auth", True, "hash_prefix", u["password_hash"][:18])
    u2 = authenticate("gruaro", "Gruaro2026!")
    assert u2, "gruaro auth failed"
    print("gruaro_auth", True, "hash_prefix", u2["password_hash"][:18])
    # secondo login deve già essere scrypt (rehash avvenuto)
    u3 = authenticate("gruaro", "Gruaro2026!")
    assert u3 and u3["password_hash"].startswith("scrypt:")
    print("gruaro_rehash_ok")

    # Upload validation
    _, err_bad = _validate_excel_upload(_FakeUpload("malware.exe", b"MZ\x90\x00"))
    assert err_bad
    _, err_txt = _validate_excel_upload(_FakeUpload("note.xlsx", b"not-a-zip"))
    assert err_txt
    ok_name, err_ok = _validate_excel_upload(_FakeUpload("ok.xlsx", b"PK\x03\x04dummy"))
    assert ok_name == "ok.xlsx" and err_ok is None
    print("upload_validation_ok")

    app = create_app()
    client = app.test_client()
    page = client.get("/login")
    assert b"csrf_token" in page.data
    match = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)
    assert match
    bad = client.post(
        "/login",
        data={"username": "gruaro", "password": "Gruaro2026!", "csrf_token": "bad"},
        follow_redirects=True,
    )
    assert b"CSRF" in bad.data or b"Sessione" in bad.data or b"scaduta" in bad.data
    print("csrf_reject_ok")

    page = client.get("/login")
    match = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)
    assert match
    token = match.group(1).decode()
    ok = client.post(
        "/login",
        data={"username": "gruaro", "password": "Gruaro2026!", "csrf_token": token},
        follow_redirects=False,
    )
    print("gruaro_login", ok.status_code, ok.headers.get("Location"))
    assert ok.status_code in {302, 303}

    # AuthZ smoke: filiale non può aprire modifica di prodotto di altra filiale
    other = None
    for p in list_prodotti():
        if "Gruaro" not in (p.get("filiale") or ""):
            other = p
            break
    if other:
        denied = client.get(f"/prodotti/{other['id']}/modifica", follow_redirects=False)
        assert denied.status_code in {302, 303}
        print("filiale_edit_denied_other", other["filiale"])
    else:
        print("filiale_edit_denied_skip_no_other")

    sample = next(iter(list_prodotti()), None)
    if sample:
        got = get_prodotto(sample["id"])
        assert got and got["id"] == sample["id"]
        print("get_prodotto_ok")

    print("ALL_SMOKE_OK")


if __name__ == "__main__":
    main()
