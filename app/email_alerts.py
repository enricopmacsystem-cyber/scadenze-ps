from __future__ import annotations

import smtplib
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app import database as db
from app.settings import load_settings, save_settings, sanitize_recipients

# Kill-switch: nessun SMTP finché non si riattiva esplicitamente il go-live.
# Anche se Impostazioni o codice vecchio in memoria tentano l'invio, send_email_to rifiuta.
EMAIL_SENDING_HARD_OFF = True


def email_sending_allowed(settings: dict[str, Any] | None = None) -> bool:
    if EMAIL_SENDING_HARD_OFF:
        return False
    s = settings or load_settings()
    return bool(s.get("email_alerts_enabled", False))


def _nome_prodotto(nome: Any, cassetta: Any) -> str:
    """Nome prodotto con indicazione della cassetta portatile (stessi nomi della fissa)."""
    text = str(nome or "?")
    return f"{text} [cassetta portatile]" if cassetta == "portatile" else text


def _fmt_stato(giorni_rimasti: int) -> str:
    if giorni_rimasti < 0:
        return f"SCADUTO da {-giorni_rimasti} gg"
    if giorni_rimasti == 0:
        return "SCADE OGGI"
    return f"scade tra {giorni_rimasti} gg"


def build_alert_body(
    prodotti: list[dict[str, Any]],
    posticipati: list[dict[str, Any]],
    giorni: int,
    *,
    destinatario_label: str | None = None,
) -> str:
    lines = [
        "Scadenze PS — Avviso cassette di pronto soccorso",
        "",
    ]
    if destinatario_label:
        lines.append(f"Destinatario: {destinatario_label}")
        lines.append("")
    lines.extend(
        [
            f"Prodotti scaduti o in scadenza entro {giorni} giorni:",
            "",
        ]
    )
    if not prodotti and not posticipati:
        lines.append("Nessun prodotto in alert.")
        return "\n".join(lines)

    posticipati_ids = {
        p["prodotto_id"] if "prodotto_id" in p else p.get("id") for p in posticipati
    }

    by_filiale: dict[str, list[dict]] = {}
    for p in prodotti:
        if p["id"] in posticipati_ids:
            continue
        by_filiale.setdefault(p["filiale"], []).append(p)

    if by_filiale:
        lines.append("═══ PRODOTTI DA ORDINARE / SOSTITUIRE ═══")
        lines.append("")
        for filiale, items in sorted(by_filiale.items()):
            lines.append(f"▶ {filiale}")
            for p in items:
                g = int(p.get("giorni_rimasti", 0))
                lines.append(
                    f"  - {_nome_prodotto(p['nome'], p.get('cassetta'))} — scadenza {p['scadenza']} ({_fmt_stato(g)}) "
                    f"— pezzi {p['pezzi_effettivi']}/{p['pezzi_previsti']}"
                )
            lines.append("")

    if posticipati:
        lines.append("═══ POSTICIPATI DAL MESE PRECEDENTE (ordine cumulativo) ═══")
        lines.append("")
        for p in posticipati:
            lines.append(
                f"  - [{p.get('filiale_nome', '?')}] {_nome_prodotto(p.get('prodotto_nome'), p.get('cassetta'))} "
                f"(posticipato da {p.get('posticipato_da', '?')})"
            )
        lines.append("")

    count = sum(len(v) for v in by_filiale.values()) + len(posticipati)
    lines.extend(
        [
            f"Totale: {count} prodotti segnalati.",
            "",
            "Procedere con la sostituzione / ordine dei prodotti segnalati.",
            "",
            f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        ]
    )
    return "\n".join(lines)


def collect_global_recipients(settings: dict[str, Any] | None = None) -> list[str]:
    """Silvia (Impostazioni) + eventuali email responsabile_ordini."""
    s = settings or load_settings()
    combined = list(s.get("recipients") or []) + db.emails_responsabili_ordini()
    return sanitize_recipients(combined)


def collect_alert_recipients(settings: dict[str, Any] | None = None) -> list[str]:
    """Tutti i destinatari possibili (globali + filiali) — per check SMTP."""
    s = settings or load_settings()
    all_addr = list(collect_global_recipients(s))
    fe = s.get("filiale_emails") or {}
    if isinstance(fe, dict):
        for emails in fe.values():
            if isinstance(emails, list):
                all_addr.extend(emails)
            elif emails:
                all_addr.append(str(emails))
    return sanitize_recipients(all_addr)


def emails_for_filiale(filiale_nome: str, settings: dict[str, Any] | None = None) -> list[str]:
    s = settings or load_settings()
    fe = s.get("filiale_emails") or {}
    if not isinstance(fe, dict):
        return []
    return sanitize_recipients(fe.get(filiale_nome) or [])


def smtp_config_ok(settings: dict[str, Any] | None = None) -> tuple[bool, str]:
    s = settings or load_settings()
    smtp = s.get("smtp") or {}
    missing = []
    if not smtp.get("host"):
        missing.append("host SMTP")
    if not smtp.get("from_email"):
        missing.append("mittente")
    if not (smtp.get("password") or "").strip():
        missing.append("password SMTP")
    if missing:
        return False, "Configurazione incompleta: " + ", ".join(missing)
    return True, "OK"


def smtp_ready(settings: dict[str, Any] | None = None) -> tuple[bool, str]:
    s = settings or load_settings()
    ok, msg = smtp_config_ok(s)
    if not ok:
        return ok, msg
    if not collect_alert_recipients(s):
        return False, "Configurazione incompleta: nessun destinatario (Silvia o filiali)"
    return True, "OK"


def send_email_to(
    recipients: list[str],
    subject: str,
    body: str,
    settings: dict[str, Any] | None = None,
    *,
    allow_while_hard_off: bool = False,
) -> None:
    from app.settings import get_smtp_password_plain

    s = settings or load_settings()
    if EMAIL_SENDING_HARD_OFF and not allow_while_hard_off:
        raise RuntimeError(
            "Invio email bloccato (go-live non attivo). Nessuna mail inviata."
        )
    if not allow_while_hard_off and not email_sending_allowed(s):
        raise RuntimeError(
            "Invio email bloccato (go-live non attivo). Nessuna mail inviata."
        )
    ok, msg = smtp_config_ok(s)
    if not ok:
        raise RuntimeError(msg)
    to_list = sanitize_recipients(recipients)
    if not to_list:
        raise RuntimeError("Nessun destinatario valido")

    smtp = s["smtp"]
    msg_root = MIMEMultipart()
    msg_root["From"] = f"{smtp.get('from_name') or 'Scadenze PS'} <{smtp['from_email']}>"
    msg_root["To"] = ", ".join(to_list)
    msg_root["Subject"] = subject
    msg_root.attach(MIMEText(body, "plain", "utf-8"))

    port = int(smtp.get("port") or 587)
    with smtplib.SMTP(smtp["host"], port, timeout=30) as server:
        if smtp.get("use_tls", True):
            server.starttls()
        user = (smtp.get("username") or "").strip()
        password = get_smtp_password_plain(s)
        if user:
            server.login(user, password)
        server.sendmail(smtp["from_email"], to_list, msg_root.as_string())


def send_email(subject: str, body: str, settings: dict[str, Any] | None = None) -> None:
    """Compat: invia ai destinatari globali (Silvia + responsabile ordini)."""
    s = settings or load_settings()
    send_email_to(collect_global_recipients(s), subject, body, s)


def _group_by_filiale(prodotti: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for p in prodotti:
        nome = p.get("filiale") or "?"
        out.setdefault(nome, []).append(p)
    return out


def check_and_send_alerts(
    force: bool = False,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Soluzione A:
    - Silvia (recipients): elenco completo di tutti i prodotti in alert
    - Responsabili filiale: solo i prodotti della propria filiale

    Default (force=False): invia solo se ci sono prodotti *nuovi* in finestra
    (non ancora notificati per quella scadenza). Silvia riceve comunque il quadro completo.

    force=True (pulsante Invia): reinvia il quadro attuale a Silvia e a tutte le
    filiali con prodotti in alert.
    """
    settings = load_settings()
    giorni = int(settings.get("alert_days") or 15)
    tutti = db.prodotti_in_alert(giorni)
    nuovi = db.prodotti_alert_non_notificati(giorni)
    mese_corrente = date.today().strftime("%Y-%m")
    posticipati = (
        db.alert_posticipati_attivi(mese_corrente)
        if force and settings.get("posticipo_enabled")
        else []
    )

    global_to = collect_global_recipients(settings)
    result: dict[str, Any] = {
        "count": len(tutti),
        "new_count": len(nuovi),
        "sent": False,
        "message": "",
        "prodotti": tutti,
        "nuovi": nuovi,
        "posticipati": posticipati,
        "recipients": [],
        "emails_sent": 0,
    }

    if not email_sending_allowed(settings):
        result["message"] = (
            "Invio email disattivato (go-live non attivo). "
            "Gli alert restano visibili in app; nessuna mail verrà inviata."
        )
        return result

    trigger = tutti if force else nuovi
    if not trigger and not (force and posticipati):
        result["message"] = (
            "Nessun prodotto nuovo in scadenza da notificare."
            if not force
            else "Nessun prodotto in scadenza o scaduto."
        )
        return result

    ok, msg = smtp_config_ok(settings)
    if not ok:
        result["message"] = msg + ". Configura SMTP in Impostazioni."
        return result
    if not global_to and not collect_alert_recipients(settings):
        result["message"] = "Nessun destinatario configurato (Silvia / filiali)."
        return result

    if dry_run:
        result["message"] = (
            f"Dry-run: {len(nuovi)} nuovi / {len(tutti)} in alert; "
            f"Silvia={global_to}"
        )
        return result

    sent_to: list[str] = []
    emails_sent = 0
    errors: list[str] = []

    # 1) Silvia / globali: quadro completo
    if global_to:
        body_s = build_alert_body(
            tutti,
            posticipati,
            giorni,
            destinatario_label="Responsabile ordini materiali (quadro completo)",
        )
        subject_s = (
            f"[Scadenze PS] {len(tutti)} prodotti da sostituire — {mese_corrente}"
        )
        try:
            send_email_to(global_to, subject_s, body_s, settings)
            sent_to.extend(global_to)
            emails_sent += 1
        except Exception as exc:  # noqa: BLE001 — riportiamo in UI
            errors.append(f"Silvia: {exc}")

    # 2) Filiali: solo se hanno almeno un prodotto nel trigger (o force)
    by_all = _group_by_filiale(tutti)
    trigger_filiali = {p.get("filiale") for p in trigger if p.get("filiale")}

    # Raggruppa per stesso set di email (es. Gruaro Showroom+Magazzino → una sola mail)
    groups: dict[frozenset[str], dict[str, Any]] = {}
    for fname, items in by_all.items():
        addrs = emails_for_filiale(fname, settings)
        if not addrs:
            continue
        key = frozenset(a.lower() for a in addrs)
        group = groups.setdefault(
            key,
            {"emails": addrs, "filiali": set(), "prodotti": []},
        )
        group["filiali"].add(fname)
        group["prodotti"].extend(items)

    for group in groups.values():
        filiali_g: set[str] = group["filiali"]
        if not force and not (filiali_g & trigger_filiali):
            continue
        prodotti_f: list[dict[str, Any]] = group["prodotti"]
        addrs = group["emails"]
        label = " / ".join(sorted(filiali_g))
        body_f = build_alert_body(
            prodotti_f,
            [],
            giorni,
            destinatario_label=f"Responsabile filiale — {label}",
        )
        subject_f = f"[Scadenze PS] {len(prodotti_f)} prodotti in alert — {label}"
        try:
            send_email_to(addrs, subject_f, body_f, settings)
            sent_to.extend(addrs)
            emails_sent += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")

    # Marca come notificati i prodotti del trigger (nuovi, o tutti se force)
    if emails_sent > 0:
        db.marca_alert_notificati(tutti if force else nuovi)

    settings["last_alert_sent"] = datetime.now().isoformat(timespec="seconds")
    settings["last_alert_check"] = settings["last_alert_sent"]
    save_settings(settings)

    result["sent"] = emails_sent > 0
    result["emails_sent"] = emails_sent
    result["recipients"] = sanitize_recipients(sent_to)
    if errors:
        result["message"] = (
            f"Inviate {emails_sent} email; errori: " + "; ".join(errors)
        )
    elif emails_sent:
        result["message"] = (
            f"Inviate {emails_sent} email "
            f"({len(nuovi)} nuovi / {len(tutti)} in alert) a: "
            + ", ".join(result["recipients"])
        )
    else:
        result["message"] = "Nessuna email inviata."
    return result


def process_new_alert_notifications() -> dict[str, Any] | None:
    """
    Controlla prodotti entrati nella finestra di preavviso e invia le email (A).
    Chiamato a login / dopo import. Non reinvi a se non ci sono novità.
    """
    return check_and_send_alerts(force=False)


def maybe_auto_send_daily() -> dict[str, Any] | None:
    """Compat: ora processa solo i prodotti nuovi in finestra (non un digest giornaliero)."""
    return process_new_alert_notifications()


def notify_prodotto_esaurito(prodotto: dict[str, Any]) -> dict[str, Any]:
    """
    Mail di riordino immediata quando pezzi_effettivi arriva a 0.
    Destinatari: Silvia (globali) + responsabili della filiale.
    Rispetta EMAIL_SENDING_HARD_OFF / email_alerts_enabled (stesso go-live degli alert scadenza).
    """
    settings = load_settings()
    result: dict[str, Any] = {"sent": False, "message": "", "recipients": []}
    if not email_sending_allowed(settings):
        result["message"] = (
            "Prodotto esaurito registrato. Invio mail di riordino disattivato "
            "(go-live non attivo)."
        )
        return result

    ok, msg = smtp_config_ok(settings)
    if not ok:
        result["message"] = f"SMTP non pronto: {msg}"
        return result

    filiale = str(prodotto.get("filiale") or "?")
    nome = _nome_prodotto(prodotto.get("nome"), prodotto.get("cassetta"))
    previsti = prodotto.get("pezzi_previsti", 0)
    effettivi = prodotto.get("pezzi_effettivi", 0)
    scad = prodotto.get("scadenza") or "—"
    if prodotto.get("non_scade"):
        scad = "NON SCADE"

    body = "\n".join(
        [
            "Scadenze PS — RIORDINO IMMEDIATO (prodotto esaurito)",
            "",
            f"Filiale: {filiale}",
            f"Prodotto: {nome}",
            f"Pezzi: {effettivi}/{previsti} (ESAURITO)",
            f"Scadenza lotto attuale: {scad}",
            "",
            "Il prodotto risulta a quantità zero (consumato / non disponibile).",
            "Procedere con il riordino e la sostituzione in cassetta.",
            "",
            f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        ]
    )
    subject = f"[Scadenze PS] ESAURITO — {nome} ({filiale})"

    recipients = sanitize_recipients(
        collect_global_recipients(settings) + emails_for_filiale(filiale, settings)
    )
    if not recipients:
        result["message"] = "Nessun destinatario per il riordino esaurito."
        return result

    try:
        send_email_to(recipients, subject, body, settings)
        result["sent"] = True
        result["recipients"] = recipients
        result["message"] = f"Mail di riordino inviata a: {', '.join(recipients)}"
    except Exception as exc:  # noqa: BLE001
        result["message"] = f"Invio riordino fallito: {exc}"
    return result
