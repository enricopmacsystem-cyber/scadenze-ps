"""Verifica routing alert Soluzione A (dry-run, senza invio SMTP)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import init_db, prodotti_alert_non_notificati, prodotti_in_alert
from app.email_alerts import (
    check_and_send_alerts,
    collect_global_recipients,
    emails_for_filiale,
    smtp_ready,
)
from app.settings import load_settings


def main() -> None:
    init_db()
    s = load_settings()
    print("alert_days", s.get("alert_days"))
    print("global", collect_global_recipients(s))
    fe = s.get("filiale_emails") or {}
    for nome in sorted(fe):
        print("filiale", nome, emails_for_filiale(nome, s))
    giorni = int(s.get("alert_days") or 15)
    tutti = prodotti_in_alert(giorni)
    nuovi = prodotti_alert_non_notificati(giorni)
    print("in_alert", len(tutti), "non_notificati", len(nuovi))
    print("smtp_ready", smtp_ready(s))
    dry = check_and_send_alerts(force=False, dry_run=True)
    print("dry", dry.get("message"), "new", dry.get("new_count"), "count", dry.get("count"))
    assert "Marghera" in fe
    assert "ivan.disanzo@macsystem.it" in (fe.get("Marghera") or [])
    assert emails_for_filiale("Gruaro Showroom", s) == emails_for_filiale(
        "Gruaro Magazzino", s
    )
    print("ALERT_ROUTING_OK")


if __name__ == "__main__":
    main()
