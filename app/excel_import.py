from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app import database as db

# Sinonimi intestazioni colonne (normalizzati: lower, senza accenti/punteggiatura)
HEADER_MAP = {
    "prodotto": {
        "prodotto", "nome", "articolo", "contenuto", "descrizione",
        "contenuto cassetta", "materiale", "voce",
    },
    "previsti": {
        "pezzi previsti", "previsti", "qta prevista", "quantita prevista",
        "qty prevista", "n previsti", "pezzi teorici",
    },
    "effettivi": {
        "pezzi effettivi", "effettivi", "qta effettiva", "quantita effettiva",
        "qty effettiva", "n effettivi", "pezzi reali", "giacenza",
    },
    "scadenza": {
        "scadenza", "scadenze", "data scadenza", "scadenza originale",
        "scad.", "exp", "expiry",
    },
    "scadenza_vicina": {
        "scadenza piu vicina", "scadenza più vicina", "scadenza prossima",
        "prima scadenza", "scadenza min", "nearest",
    },
    "sede": {"sede", "cassetta", "ubicazione", "luogo", "reparto"},
    "filiale": {"filiale", "branch", "sede filiale"},
    "verifica": {
        "controllato", "verifica", "ultima verifica", "data controllo",
        "data aggiornamento", "aggiornato",
    },
    "stato": {"stato", "status", "alert"},
}

NON_SCADE_MARKERS = {
    "NON SCADE", "N/A", "-", "NESSUNA", "NESSUNA SCADENZA",
    "NO SCADENZA", "SENZA SCADENZA",
}


def _norm(text: Any) -> str:
    if text is None:
        return ""
    s = str(text).strip().lower()
    s = (
        s.replace("à", "a").replace("è", "e").replace("é", "e")
        .replace("ì", "i").replace("ò", "o").replace("ù", "u")
    )
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_non_scade(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (datetime, date)):
        return False
    text = str(value).strip().upper()
    if not text:
        return False
    if text in NON_SCADE_MARKERS:
        return True
    if re.fullmatch(r"[/\\_\-\s.]+", text):
        return True
    if "NESSUNA SCADENZA" in text:
        return True
    return False


def _parse_qty(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", ".")
    # quantità tipo "5 (" oppure "5\n" — evita di sommare i ml (500)
    nums = re.findall(r"(?:^|[\n;])\s*(\d+)\s*(?:\(|$|[^\d])", "\n" + text)
    if nums:
        return sum(int(n) for n in nums)
    m = re.search(r"\d+", text)
    return int(m.group()) if m else 0


def _parse_one_date(token: str) -> date | None:
    token = token.strip()
    if not token:
        return None
    for fmt in (
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%Y-%m-%d", "%Y/%m/%d",
        "%d/%m/%y", "%d-%m-%y",
        "%m/%Y", "%m-%Y", "%Y/%m", "%Y-%m",
        "%m/%y",
    ):
        try:
            dt = datetime.strptime(token, fmt)
            if fmt in {"%m/%Y", "%m-%Y", "%Y/%m", "%Y-%m", "%m/%y"}:
                return date(dt.year, dt.month, 1)
            return dt.date()
        except ValueError:
            continue
    # 08-29 o 09-25 (MM-YY)
    m = re.fullmatch(r"(\d{1,2})[-/](\d{2})", token)
    if m:
        mo, yy = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return date(2000 + yy, mo, 1)
    return None


def _extract_dates(value: Any) -> list[date]:
    if value is None or value == "":
        return []
    if isinstance(value, datetime):
        return [value.date()]
    if isinstance(value, date):
        return [value]
    if _is_non_scade(value):
        return []
    text = str(value)
    if text.startswith("#"):  # #VALUE! Excel errors
        return []
    found: list[date] = []
    # Prima le date lunghe, poi si rimuovono dal testo:
    # evita che "01/04/2027" generi anche il falso "01/04" → gen 2004
    long_patterns = [
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
        r"\b\d{1,2}[/-]\d{4}\b",
        r"\b\d{4}[/-]\d{1,2}\b",
    ]
    remaining = text
    for pat in long_patterns:
        for m in re.finditer(pat, remaining):
            d = _parse_one_date(m.group())
            if d:
                found.append(d)
        remaining = re.sub(pat, " ", remaining)
    for m in re.finditer(r"\b\d{1,2}[/-]\d{2}\b", remaining):
        d = _parse_one_date(m.group())
        if d:
            found.append(d)
    if not found:
        cleaned = re.sub(r"\(.*?\)", " ", text)
        cleaned = re.sub(r"[^\d/\-.]", " ", cleaned).strip()
        for part in re.split(r"[\s,;]+", cleaned):
            if part:
                d = _parse_one_date(part)
                if d:
                    found.append(d)
    return found


def _best_scadenza(*values: Any) -> tuple[date | None, bool]:
    """Ritorna (data più vicina, non_scade)."""
    non = any(_is_non_scade(v) for v in values if v is not None and v != "")
    dates: list[date] = []
    for v in values:
        dates.extend(_extract_dates(v))
    if dates:
        return min(dates), False
    if non:
        return None, True
    # stringhe vuote / solo errori
    meaningful = [v for v in values if v is not None and str(v).strip() and not str(v).startswith("#")]
    if not meaningful:
        return None, True
    return None, False


def _filiale_from_text(*texts: Any) -> str | None:
    blob = " ".join(str(t) for t in texts if t).upper()
    # Cassette Gruaro prima del match generico "GRUARO"
    if "SHOWROOM" in blob:
        return "Gruaro Showroom"
    if "MAGAZZINO" in blob or "MAGA" in blob:
        return "Gruaro Magazzino"
    for nome in db.FILIALI:
        if nome.upper() in blob:
            return nome
    if "GRUARO" in blob:
        return "Gruaro Showroom"
    return None


def _match_header_role(cell: Any) -> str | None:
    n = _norm(cell)
    if not n:
        return None
    # titolo lungo tipo "contenuto cassetta di pronto soccorso..."
    if n.startswith("contenuto cassetta") or "pronto soccorso" in n and "pezzi" not in n:
        return "prodotto"
    for role, synonyms in HEADER_MAP.items():
        if n in synonyms:
            return role
        for syn in synonyms:
            if syn in n or n in syn:
                return role
    return None


def _detect_header(ws) -> tuple[int, dict[str, int]] | None:
    """Trova riga intestazione e mappa ruolo -> indice colonna (1-based)."""
    max_scan = min(20, ws.max_row or 1)
    max_col = min(20, ws.max_column or 1)
    best: tuple[int, dict[str, int], int] | None = None
    for r in range(1, max_scan + 1):
        mapping: dict[str, int] = {}
        for c in range(1, max_col + 1):
            role = _match_header_role(ws.cell(r, c).value)
            if role and role not in mapping:
                mapping[role] = c
        score = len(mapping)
        # serve almeno prodotto + qualcosa
        if "prodotto" in mapping and score >= 2:
            if best is None or score > best[2]:
                best = (r, mapping, score)
    if best:
        return best[0], best[1]
    return None


def _sheet_looks_useful(ws) -> bool:
    detected = _detect_header(ws)
    return detected is not None


def _parse_sheet(ws, default_filiale: str | None) -> list[dict[str, Any]]:
    detected = _detect_header(ws)
    if not detected:
        return []
    header_row, cols = detected
    rows: list[dict[str, Any]] = []

    # verifica da header cell extras
    verifica = None
    max_col = min(20, ws.max_column or 1)
    for c in range(1, max_col + 1):
        val = ws.cell(header_row, c).value
        if val and "aggiornamento" in _norm(val):
            dates = _extract_dates(val)
            if dates:
                verifica = dates[0].isoformat()

    for r in range(header_row + 1, (ws.max_row or 0) + 1):
        nome_raw = ws.cell(r, cols["prodotto"]).value if "prodotto" in cols else None
        if not nome_raw or not str(nome_raw).strip():
            continue
        nome = str(nome_raw).strip()
        # salta righe che sono ancora intestazioni ripetute
        if _match_header_role(nome) == "prodotto" and _norm(nome) in HEADER_MAP["prodotto"]:
            continue
        if _norm(nome).startswith("contenuto cassetta"):
            continue

        previsti = _parse_qty(ws.cell(r, cols["previsti"]).value) if "previsti" in cols else 0
        effettivi = _parse_qty(ws.cell(r, cols["effettivi"]).value) if "effettivi" in cols else previsti

        vicina = ws.cell(r, cols["scadenza_vicina"]).value if "scadenza_vicina" in cols else None
        originale = ws.cell(r, cols["scadenza"]).value if "scadenza" in cols else None
        stato = ws.cell(r, cols["stato"]).value if "stato" in cols else None

        # Preferisci le date scritte in SCADENZA/ORIGINALE (giorno reale);
        # la colonna "più vicina" Excel spesso arrotonda al 1° del mese.
        scad_vals: list[Any] = []
        if originale not in (None, ""):
            scad_vals.append(originale)
        if vicina not in (None, ""):
            scad_vals.append(vicina)
        if stato and "nessuna scadenza" in _norm(stato):
            scad_vals.append("NESSUNA SCADENZA")
        scad, non_scade = _best_scadenza(*scad_vals)
        # Se originale ha date parsabili, usa il minimo di quelle (ignora formula)
        orig_dates = _extract_dates(originale)
        if orig_dates:
            scad, non_scade = min(orig_dates), False

        row_verifica = verifica
        if "verifica" in cols:
            vdates = _extract_dates(ws.cell(r, cols["verifica"]).value)
            if vdates:
                row_verifica = vdates[0].isoformat()

        note_parts = []
        if "sede" in cols:
            sede = ws.cell(r, cols["sede"]).value
            if sede:
                note_parts.append(f"Sede: {sede}")

        filiale_row = None
        if "filiale" in cols:
            filiale_row = _filiale_from_text(ws.cell(r, cols["filiale"]).value)
        if "sede" in cols and not filiale_row:
            filiale_row = _filiale_from_text(ws.cell(r, cols["sede"]).value)
        filiale_row = filiale_row or default_filiale

        rows.append(
            {
                "nome": nome,
                "pezzi_previsti": previsti,
                "pezzi_effettivi": effettivi,
                "scadenza": scad.isoformat() if scad else None,
                "non_scade": bool(non_scade) and scad is None,
                "ultima_verifica": row_verifica,
                "note": " | ".join(note_parts) if note_parts else None,
                "filiale_nome": filiale_row,
            }
        )
    return rows


def preview_excel(path: str | Path) -> dict[str, Any]:
    """Anteprima: fogli rilevati e conteggio prodotti senza scrivere sul DB."""
    path = Path(path)
    wb = load_workbook(path, data_only=True)
    useful: list[tuple[str, Any, dict[str, int]]] = []
    for name in wb.sheetnames:
        ws = wb[name]
        detected = _detect_header(ws)
        if not detected:
            continue
        useful.append((name, ws, detected[1]))
    prefer_monitoraggio = any("sede" in cols for _, _, cols in useful)
    sheets_info = []
    total = 0
    for name, ws, cols in useful:
        if prefer_monitoraggio and "sede" not in cols:
            continue
        rows = _parse_sheet(ws, None)
        sheets_info.append({"nome": name, "prodotti": len(rows)})
        total += len(rows)
    return {"file": path.name, "fogli": sheets_info, "totale": total}


def import_excel(
    path: str | Path,
    filiale_nome: str | None = None,
    replace: bool = True,
) -> dict[str, Any]:
    """
    Importa prodotti da Excel con layout variabili.
    Supporta:
    - formato classico (titolo + pezzi + scadenza)
    - monitoraggio con SEDE/PRODOTTO/SCADENZA PIU VICINA
    - più fogli nello stesso file
    """
    path = Path(path)
    wb = load_workbook(path, data_only=True)

    # Filiale di default: parametro UI, altrimenti titolo/foglio/nome file
    guessed = filiale_nome
    if not guessed:
        guessed = _filiale_from_text(path.name, *wb.sheetnames)
    if not guessed and wb.active:
        title = wb.active.cell(1, 1).value
        guessed = _filiale_from_text(title)

    # Se esiste un foglio "monitoraggio" con colonna SEDE, usalo da solo
    # (evita doppioni con fogli dettaglio tipo SHOWROOM / MAGA nello stesso file)
    useful: list[tuple[str, Any, dict[str, int]]] = []
    for name in wb.sheetnames:
        ws = wb[name]
        detected = _detect_header(ws)
        if not detected:
            continue
        useful.append((name, ws, detected[1]))

    prefer_monitoraggio = any("sede" in cols for _, _, cols in useful)
    sheets_to_parse = [
        (name, ws)
        for name, ws, cols in useful
        if (not prefer_monitoraggio) or ("sede" in cols)
    ]

    all_rows: list[dict[str, Any]] = []
    fogli_usati: list[str] = []
    for name, ws in sheets_to_parse:
        sheet_default = _filiale_from_text(name) or guessed
        parsed = _parse_sheet(ws, sheet_default)
        if parsed:
            fogli_usati.append(name)
            all_rows.extend(parsed)

    if not all_rows:
        raise ValueError(
            "Nessun prodotto riconosciuto nel file. "
            "Verifica che ci siano colonne tipo Prodotto / Pezzi / Scadenza."
        )

    # Raggruppa per filiale
    by_filiale: dict[str, list[dict[str, Any]]] = {}
    for row in all_rows:
        f = row.pop("filiale_nome", None) or guessed
        if not f:
            raise ValueError(
                "Impossibile rilevare la filiale. Selezionala manualmente prima dell'import."
            )
        by_filiale.setdefault(f, []).append(row)

    importati = 0
    filiali_toccate: list[str] = []
    for fname, items in by_filiale.items():
        filiale = db.get_filiale_by_name(fname)
        if not filiale:
            raise ValueError(f"Filiale sconosciuta nel file: {fname}")
        if replace:
            with db.connect() as conn:
                # L'Excel descrive la cassetta fissa: la portatile non va toccata
                conn.execute(
                    "DELETE FROM prodotti WHERE filiale_id = ? AND cassetta = 'fissa'",
                    (filiale["id"],),
                )
        for item in items:
            # se non_scade e senza data ok; se ha data forza non_scade=False
            if item.get("scadenza"):
                item["non_scade"] = False
            db.add_prodotto(filiale_id=filiale["id"], **item)
            importati += 1
        filiali_toccate.append(fname)

    return {
        "filiale": ", ".join(filiali_toccate),
        "importati": importati,
        "fogli": fogli_usati,
        "verifica": None,
    }
