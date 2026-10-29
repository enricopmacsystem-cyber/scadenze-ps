from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.paths import SETTINGS_PATH, ensure_dirs

DEFAULT_SETTINGS: dict[str, Any] = {
    "alert_days": 15,
    "smtp": {
        "host": "",
        "port": 587,
        "use_tls": True,
        "username": "",
        "password": "",
        "from_email": "",
        "from_name": "Scadenze PS",
    },
    "recipients": [],
    # Email responsabili cassetta per filiale (Soluzione A: ricevono solo i propri prodotti)
    "filiale_emails": {
        "Marghera": ["ivan.disanzo@macsystem.it"],
        "Gruaro Showroom": [
            "marco.fedrigo@macsystem.it",
            "valentina.visentin@macsystem.it",
        ],
        "Gruaro Magazzino": [
            "marco.fedrigo@macsystem.it",
            "valentina.visentin@macsystem.it",
        ],
        "Verona": ["roberto.bazzoni@macsystem.it"],
        "Villorba": ["gabriele.benetton@macsystem.it"],
        "Padova": ["marc.borgato@macsystem.it"],
        "Tavagnacco": ["andrea.collovigh@macsystem.it"],
        # Mirandola / Modena: in standby, nessuna email
    },
    "last_alert_sent": None,
    "last_alert_check": None,
    # False = nessun invio SMTP (alert solo in app). Attivare in go-live.
    "email_alerts_enabled": False,
}


def _app_secret() -> str:
    from app.security import app_secret_key

    return app_secret_key()


def load_settings() -> dict[str, Any]:
    ensure_dirs()
    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)
        return deepcopy(DEFAULT_SETTINGS)
    with SETTINGS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    merged = deepcopy(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in data.items() if k not in {"smtp", "filiale_emails"}})
    if "smtp" in data and isinstance(data["smtp"], dict):
        merged["smtp"].update(data["smtp"])
    # Merge filiale_emails: default + eventuali override salvati
    defaults_fe = deepcopy(DEFAULT_SETTINGS.get("filiale_emails") or {})
    saved_fe = data.get("filiale_emails") if isinstance(data.get("filiale_emails"), dict) else {}
    for nome, emails in defaults_fe.items():
        if nome not in saved_fe or not saved_fe[nome]:
            saved_fe[nome] = emails
    merged["filiale_emails"] = {
        str(k): sanitize_recipients(v if isinstance(v, list) else [v])
        for k, v in saved_fe.items()
    }
    # Migrazione: cifra password SMTP in chiaro residua (non lasciare fallire in silenzio)
    raw_pw = (merged.get("smtp") or {}).get("password") or ""
    if raw_pw and not str(raw_pw).startswith("enc:v1:"):
        from app.security import encrypt_secret

        merged["smtp"]["password"] = encrypt_secret(raw_pw, _app_secret())
        save_settings(merged)
    # Persisti filiale_emails se mancavano sul file
    if not isinstance(data.get("filiale_emails"), dict) or not data.get("filiale_emails"):
        save_settings(merged)
    return merged


def get_smtp_password_plain(settings: dict[str, Any] | None = None) -> str:
    s = settings or load_settings()
    stored = (s.get("smtp") or {}).get("password") or ""
    if not stored:
        return ""
    from app.security import decrypt_secret

    return decrypt_secret(str(stored), _app_secret())


def _is_placeholder_email(addr: str) -> bool:
    low = addr.strip().lower()
    return low.endswith("@example.com") or low.endswith("@example.org")


def sanitize_recipients(recipients: list[Any] | None) -> list[str]:
    """Rimuove vuoti e placeholder @example.*."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in recipients or []:
        addr = str(raw or "").strip()
        if not addr or _is_placeholder_email(addr):
            continue
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(addr)
    return out


def save_settings(settings: dict[str, Any]) -> None:
    ensure_dirs()
    settings = dict(settings)
    if "recipients" in settings:
        settings["recipients"] = sanitize_recipients(settings.get("recipients"))
    if "filiale_emails" in settings and isinstance(settings["filiale_emails"], dict):
        settings["filiale_emails"] = {
            str(k): sanitize_recipients(v if isinstance(v, list) else [v])
            for k, v in settings["filiale_emails"].items()
        }
    # Assicura cifratura password SMTP prima di scrivere su disco
    smtp = settings.get("smtp")
    if isinstance(smtp, dict):
        pw = smtp.get("password") or ""
        if pw and not str(pw).startswith("enc:v1:"):
            from app.security import encrypt_secret

            smtp = dict(smtp)
            smtp["password"] = encrypt_secret(str(pw), _app_secret())
            settings["smtp"] = smtp
    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
