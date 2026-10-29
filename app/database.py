from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterator

from app.paths import DB_PATH, ensure_dirs
from app.security import hash_password, verify_password

FILIALI = [
    "Tavagnacco",
    "Verona",
    "Padova",
    "Marghera",
    "Gruaro Showroom",
    "Gruaro Magazzino",
    "Villorba",
    "Mirandola",
]

RUOLI = ("admin", "filiale", "responsabile_ordini")

CASSETTE = ("fissa", "portatile")

# Dotazione standard della cassetta PS portatile (nome, pezzi previsti).
# Le scadenze vengono inserite dalle filiali.
CONTENUTO_PORTATILE = [
    ("Guanti sterili monouso (paia)", 2),
    ("Soluzione cutanea iodopovidone 10% iodio — flacone 125 ml", 1),
    ("Soluzione fisiologica (sodio cloruro 0,9%) — flacone 250 ml", 1),
    ("Compresse di garza sterile 10x10 in buste singole", 3),
    ("Compressa di garza sterile 18x40 in busta singola", 1),
    ("Pinzetta da medicazione sterile monouso", 1),
    ("Cotone idrofilo (confezione)", 1),
    ("Cerotti di varie misure pronti all'uso (confezione)", 1),
    ("Rotolo di cerotto alto 2,5 cm", 1),
    ("Rotolo di benda orlata alta 10 cm", 1),
    ("Forbici (paio)", 1),
    ("Laccio emostatico", 1),
    ("Ghiaccio pronto uso (confezione)", 1),
    ("Sacchetto monouso per raccolta rifiuti sanitari", 1),
]


def _hash_password(password: str) -> str:
    """Compat: usa hashing moderno (scrypt)."""
    return hash_password(password)


def _parse_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text or text.upper() in {"NON SCADE", "N/A", "-", "NESSUNA"}:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Data non valida: {value!r}")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Connessione SQLite sul NAS: timeout lungo per accessi concorrenti leggeri."""
    ensure_dirs()
    # timeout=30: attende se un altro PC sta scrivendo sullo stesso file NAS
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    # WAL non è affidabile su condivisioni SMB/NAS (shared memory / locking).
    # DELETE (default) è la scelta corretta per DB su \\server\share.
    conn.execute("PRAGMA journal_mode = DELETE")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
#  Schema & init
# ---------------------------------------------------------------------------

def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS filiali (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS utenti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                nome_completo TEXT NOT NULL DEFAULT '',
                ruolo TEXT NOT NULL DEFAULT 'filiale',
                filiale_id INTEGER,
                email TEXT,
                attivo INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (filiale_id) REFERENCES filiali(id)
            );

            CREATE TABLE IF NOT EXISTS prodotti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filiale_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                pezzi_previsti INTEGER NOT NULL DEFAULT 0,
                pezzi_effettivi INTEGER NOT NULL DEFAULT 0,
                scadenza TEXT,
                non_scade INTEGER NOT NULL DEFAULT 0,
                ultima_verifica TEXT,
                note TEXT,
                cassetta TEXT NOT NULL DEFAULT 'fissa',
                FOREIGN KEY (filiale_id) REFERENCES filiali(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS app_meta (
                chiave TEXT PRIMARY KEY,
                valore TEXT
            );

            CREATE TABLE IF NOT EXISTS alert_posticipati (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prodotto_id INTEGER NOT NULL,
                posticipato_da TEXT NOT NULL,
                posticipato_a TEXT NOT NULL,
                creato_il TEXT NOT NULL,
                utente_id INTEGER,
                note TEXT,
                FOREIGN KEY (prodotto_id) REFERENCES prodotti(id) ON DELETE CASCADE,
                FOREIGN KEY (utente_id) REFERENCES utenti(id)
            );

            CREATE TABLE IF NOT EXISTS alert_notifiche (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prodotto_id INTEGER NOT NULL,
                scadenza TEXT NOT NULL,
                inviato_il TEXT NOT NULL,
                UNIQUE (prodotto_id, scadenza),
                FOREIGN KEY (prodotto_id) REFERENCES prodotti(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_prodotti_filiale
                ON prodotti(filiale_id);
            CREATE INDEX IF NOT EXISTS idx_prodotti_scadenza
                ON prodotti(scadenza);
            CREATE INDEX IF NOT EXISTS idx_alert_posticipati_prodotto
                ON alert_posticipati(prodotto_id);
            CREATE INDEX IF NOT EXISTS idx_alert_notifiche_prodotto
                ON alert_notifiche(prodotto_id);
            """
        )
        for nome in FILIALI:
            conn.execute(
                "INSERT OR IGNORE INTO filiali (nome) VALUES (?)",
                (nome,),
            )
        _migrate_gruaro_cassette(conn)
        # Migrazione colonna must_change_password su DB già esistenti
        cols = [r[1] for r in conn.execute("PRAGMA table_info(utenti)").fetchall()]
        if "must_change_password" not in cols:
            conn.execute(
                "ALTER TABLE utenti ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 1"
            )
        # Tabella alert_notifiche su DB già esistenti
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_notifiche (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prodotto_id INTEGER NOT NULL,
                scadenza TEXT NOT NULL,
                inviato_il TEXT NOT NULL,
                UNIQUE (prodotto_id, scadenza),
                FOREIGN KEY (prodotto_id) REFERENCES prodotti(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alert_notifiche_prodotto "
            "ON alert_notifiche(prodotto_id)"
        )
        # Colonna cassetta (fissa / portatile) su DB già esistenti
        cols = [r[1] for r in conn.execute("PRAGMA table_info(prodotti)").fetchall()]
        if "cassetta" not in cols:
            conn.execute(
                "ALTER TABLE prodotti ADD COLUMN cassetta TEXT NOT NULL DEFAULT 'fissa'"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_prodotti_cassetta ON prodotti(filiale_id, cassetta)"
        )
        existing = conn.execute("SELECT COUNT(*) AS c FROM utenti").fetchone()["c"]
        if existing == 0:
            _seed_default_users(conn)
        _sync_utenti_email_filiali(conn)
        _seed_cassetta_portatile(conn)


def _seed_cassetta_portatile(conn: sqlite3.Connection) -> None:
    """Crea una sola volta la cassetta portatile di ogni filiale (senza scadenze).

    Il marcatore in app_meta evita di ricrearla se una filiale ne elimina i
    prodotti, e con più PC avviati insieme solo il primo esegue l'inserimento.
    """
    cur = conn.execute(
        "INSERT OR IGNORE INTO app_meta (chiave, valore) VALUES ('seed_cassetta_portatile', ?)",
        (datetime.now().isoformat(timespec="seconds"),),
    )
    if cur.rowcount != 1:
        return
    for f in conn.execute("SELECT id FROM filiali").fetchall():
        for nome, pezzi in CONTENUTO_PORTATILE:
            conn.execute(
                """
                INSERT INTO prodotti (
                    filiale_id, nome, pezzi_previsti, pezzi_effettivi,
                    scadenza, non_scade, cassetta
                ) VALUES (?, ?, ?, ?, NULL, 0, 'portatile')
                """,
                (f["id"], nome, pezzi, pezzi),
            )


def _migrate_gruaro_cassette(conn: sqlite3.Connection) -> None:
    """Separa la vecchia filiale Gruaro in Showroom e Magazzino."""
    old = conn.execute("SELECT id FROM filiali WHERE nome = 'Gruaro'").fetchone()
    show = conn.execute(
        "SELECT id FROM filiali WHERE nome = 'Gruaro Showroom'"
    ).fetchone()
    maga = conn.execute(
        "SELECT id FROM filiali WHERE nome = 'Gruaro Magazzino'"
    ).fetchone()
    if not show or not maga:
        return
    show_id, maga_id = show["id"], maga["id"]
    if old:
        old_id = old["id"]
        for p in conn.execute(
            "SELECT id, note FROM prodotti WHERE filiale_id = ?", (old_id,)
        ).fetchall():
            note = (p["note"] or "").upper()
            if "MAGAZZINO" in note or "MAGA" in note:
                target = maga_id
            else:
                target = show_id
            if "SHOWROOM" in note:
                target = show_id
            conn.execute(
                "UPDATE prodotti SET filiale_id = ? WHERE id = ?",
                (target, p["id"]),
            )
        conn.execute(
            "UPDATE utenti SET filiale_id = ? WHERE filiale_id = ?",
            (show_id, old_id),
        )
        conn.execute("DELETE FROM filiali WHERE id = ?", (old_id,))
    # Assicura utente filiale gruaro (vede entrambe via webapp)
    existing_gruaro = conn.execute(
        "SELECT id FROM utenti WHERE username = 'gruaro' COLLATE NOCASE"
    ).fetchone()
    if not existing_gruaro:
        conn.execute(
            "INSERT INTO utenti (username, password_hash, nome_completo, ruolo, filiale_id, must_change_password) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (
                "gruaro",
                _hash_password("Gruaro2026!"),
                "Utente Gruaro",
                "filiale",
                show_id,
            ),
        )
    ordini = conn.execute(
        "SELECT id, filiale_id FROM utenti WHERE username = 'ordini.gruaro' COLLATE NOCASE"
    ).fetchone()
    if ordini and not ordini["filiale_id"]:
        conn.execute(
            "UPDATE utenti SET filiale_id = ? WHERE id = ?",
            (show_id, ordini["id"]),
        )


def is_gruaro_filiale(nome: str | None) -> bool:
    return bool(nome) and str(nome).upper().startswith("GRUARO")


def list_filiali_for_user(user: dict[str, Any]) -> list[dict[str, Any]]:
    """Filiali visibili/modificabili: utente Gruaro vede Showroom + Magazzino."""
    all_f = [dict(f) for f in list_filiali()]
    ruolo = (user.get("ruolo") or "").strip().lower()
    if ruolo in {"admin", "responsabile_ordini"}:
        return all_f
    if ruolo == "filiale":
        nome = user.get("filiale_nome") or ""
        username = (user.get("username") or "").strip().lower()
        # Gruaro: entrambe le cassette, mai le altre filiali
        if is_gruaro_filiale(nome) or username == "gruaro" or "gruaro" in username:
            return [f for f in all_f if is_gruaro_filiale(f["nome"])]
        fid = user.get("filiale_id")
        if fid is None:
            return []
        return [f for f in all_f if int(f["id"]) == int(fid)]
    return []


def _seed_default_users(conn: sqlite3.Connection) -> None:
    """Crea utenti di default (password da cambiare al primo accesso)."""
    # Password iniziali documentate in GUIDA_USO.md
    conn.execute(
        "INSERT INTO utenti (username, password_hash, nome_completo, ruolo, filiale_id, must_change_password) "
        "VALUES (?, ?, ?, ?, NULL, 1)",
        ("admin", _hash_password("Admin2026!!"), "Amministratore", "admin"),
    )
    rows = conn.execute("SELECT id, nome FROM filiali ORDER BY nome").fetchall()
    default_pw = {
        "Tavagnacco": "Tavagnacco2026!",
        "Verona": "Verona2026!",
        "Padova": "Padova2026!",
        "Marghera": "Marghera2026!",
        "Villorba": "Villorba2026!",
        "Mirandola": "Mirandola2026!",
    }
    show_id = None
    for row in rows:
        if row["nome"] == "Gruaro Showroom":
            show_id = row["id"]
            continue
        if row["nome"] == "Gruaro Magazzino":
            continue
        username = row["nome"].lower().replace(" ", "")
        pw = default_pw.get(row["nome"], f"{row['nome']}2026!")
        conn.execute(
            "INSERT INTO utenti (username, password_hash, nome_completo, ruolo, filiale_id, must_change_password) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (username, _hash_password(pw), f"Utente {row['nome']}", "filiale", row["id"]),
        )
    if show_id is not None:
        conn.execute(
            "INSERT INTO utenti (username, password_hash, nome_completo, ruolo, filiale_id, must_change_password) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            ("gruaro", _hash_password("Gruaro2026!"), "Utente Gruaro", "filiale", show_id),
        )
        conn.execute(
            "INSERT INTO utenti (username, password_hash, nome_completo, ruolo, filiale_id, must_change_password) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            ("ordini.gruaro", _hash_password("OrdiniGruaro2026!"),
             "Responsabile Ordini Gruaro", "responsabile_ordini", show_id),
        )


# ---------------------------------------------------------------------------
#  Autenticazione
# ---------------------------------------------------------------------------

def authenticate(username: str, password: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT u.*, f.nome AS filiale_nome "
            "FROM utenti u LEFT JOIN filiali f ON f.id = u.filiale_id "
            "WHERE u.username = ? AND u.attivo = 1",
            (username.strip(),),
        ).fetchone()
        if row is None:
            return None
        ok, needs_rehash = verify_password(row["password_hash"], password)
        if not ok:
            return None
        user = dict(row)
        if needs_rehash:
            new_hash = hash_password(password)
            conn.execute(
                "UPDATE utenti SET password_hash = ? WHERE id = ?",
                (new_hash, user["id"]),
            )
            user["password_hash"] = new_hash
        return user


def change_password(
    utente_id: int, nuova_password: str, clear_must_change: bool = True
) -> None:
    with connect() as conn:
        if clear_must_change:
            conn.execute(
                "UPDATE utenti SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                (hash_password(nuova_password), utente_id),
            )
        else:
            conn.execute(
                "UPDATE utenti SET password_hash = ?, must_change_password = 1 WHERE id = ?",
                (hash_password(nuova_password), utente_id),
            )


# ---------------------------------------------------------------------------
#  CRUD utenti (admin)
# ---------------------------------------------------------------------------

def get_utente_by_id(utente_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT u.*, f.nome AS filiale_nome "
            "FROM utenti u LEFT JOIN filiali f ON f.id = u.filiale_id "
            "WHERE u.id = ?",
            (utente_id,),
        ).fetchone()
        return dict(row) if row else None


def list_utenti() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT u.*, f.nome AS filiale_nome "
            "FROM utenti u LEFT JOIN filiali f ON f.id = u.filiale_id "
            "ORDER BY u.ruolo, u.username"
        ).fetchall()
        return [dict(r) for r in rows]


def emails_responsabili_ordini() -> list[str]:
    """Email degli account responsabile_ordini attivi (es. ordini.gruaro)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT email FROM utenti "
            "WHERE attivo = 1 AND ruolo = 'responsabile_ordini' "
            "AND email IS NOT NULL AND TRIM(email) != ''"
        ).fetchall()
        return [str(r["email"]).strip() for r in rows if r["email"]]


def _sync_utenti_email_filiali(conn: sqlite3.Connection) -> None:
    """Allinea email utenti filiale da settings.filiale_emails (prima mail della lista)."""
    try:
        from app.settings import load_settings
        from app.settings import sanitize_recipients
    except Exception:
        return
    try:
        fe = (load_settings().get("filiale_emails") or {})
    except Exception:
        return
    username_by_filiale = {
        "Marghera": "marghera",
        "Verona": "verona",
        "Villorba": "villorba",
        "Padova": "padova",
        "Tavagnacco": "tavagnacco",
        "Gruaro Showroom": "gruaro",
        "Gruaro Magazzino": "gruaro",
    }
    for filiale_nome, username in username_by_filiale.items():
        emails = sanitize_recipients(fe.get(filiale_nome) or [])
        if not emails:
            continue
        primary = emails[0]
        row = conn.execute(
            "SELECT id, email FROM utenti WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
        if not row:
            continue
        current = (row["email"] or "").strip()
        if not current:
            conn.execute(
                "UPDATE utenti SET email = ? WHERE id = ?",
                (primary, row["id"]),
            )


def prodotti_alert_non_notificati(giorni: int = 15) -> list[dict[str, Any]]:
    """Prodotti in finestra scadenza non ancora notificati (esauriti esclusi: mail a parte)."""
    in_alert = [
        p for p in prodotti_in_alert(giorni) if p.get("stato") != "esaurito" and p.get("scadenza")
    ]
    if not in_alert:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT prodotto_id, scadenza FROM alert_notifiche"
        ).fetchall()
    already = {(int(r["prodotto_id"]), str(r["scadenza"])) for r in rows}
    return [
        p
        for p in in_alert
        if (int(p["id"]), str(p["scadenza"])) not in already
    ]


def marca_alert_notificati(prodotti: list[dict[str, Any]]) -> None:
    """Registra i prodotti come già notificati per la loro scadenza attuale."""
    if not prodotti:
        return
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        for p in prodotti:
            scad = p.get("scadenza")
            if not scad:
                continue
            conn.execute(
                """
                INSERT INTO alert_notifiche (prodotto_id, scadenza, inviato_il)
                VALUES (?, ?, ?)
                ON CONFLICT(prodotto_id, scadenza) DO UPDATE SET inviato_il = excluded.inviato_il
                """,
                (int(p["id"]), str(scad), now),
            )

def add_utente(
    username: str,
    password: str,
    nome_completo: str,
    ruolo: str,
    filiale_id: int | None = None,
    email: str | None = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO utenti (username, password_hash, nome_completo, ruolo, filiale_id, email, must_change_password) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (username.strip(), _hash_password(password), nome_completo.strip(),
             ruolo, filiale_id, email),
        )
        return int(cur.lastrowid)


def update_utente(utente_id: int, **fields: Any) -> None:
    allowed = {"username", "nome_completo", "ruolo", "filiale_id", "email", "attivo"}
    data = {k: v for k, v in fields.items() if k in allowed}
    if "password" in fields and fields["password"]:
        data["password_hash"] = _hash_password(fields["password"])
    if not data:
        return
    cols = ", ".join(f"{k} = ?" for k in data)
    values = list(data.values()) + [utente_id]
    with connect() as conn:
        conn.execute(f"UPDATE utenti SET {cols} WHERE id = ?", values)


def delete_utente(utente_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM utenti WHERE id = ?", (utente_id,))


# ---------------------------------------------------------------------------
#  Filiali
# ---------------------------------------------------------------------------

def list_filiali() -> list[sqlite3.Row]:
    with connect() as conn:
        return list(conn.execute("SELECT * FROM filiali ORDER BY nome"))


def get_filiale_by_name(nome: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM filiali WHERE nome = ?", (nome,)
        ).fetchone()


# ---------------------------------------------------------------------------
#  Prodotti
# ---------------------------------------------------------------------------

def _cassetta(value: Any) -> str:
    text = str(value or "fissa").strip().lower()
    if text not in CASSETTE:
        raise ValueError(f"Cassetta non valida: {value!r}")
    return text


def list_prodotti(
    filiale_id: int | None = None, cassetta: str | None = None
) -> list[dict[str, Any]]:
    """Prodotti di una filiale (o tutte); cassetta=None = fissa + portatile."""
    where = []
    params: list[Any] = []
    if filiale_id is not None:
        where.append("p.filiale_id = ?")
        params.append(filiale_id)
    if cassetta is not None:
        where.append("p.cassetta = ?")
        params.append(_cassetta(cassetta))
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    if filiale_id is None:
        order_sql = "f.nome, p.cassetta, p.nome"
    else:
        order_sql = """
                    p.cassetta,
                    CASE WHEN p.non_scade = 1 THEN 1 ELSE 0 END,
                    p.scadenza IS NULL,
                    p.scadenza,
                    p.nome"""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT p.*, f.nome AS filiale
            FROM prodotti p
            JOIN filiali f ON f.id = p.filiale_id
            {where_sql}
            ORDER BY {order_sql}
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_prodotto(prodotto_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT p.*, f.nome AS filiale
            FROM prodotti p
            JOIN filiali f ON f.id = p.filiale_id
            WHERE p.id = ?
            """,
            (prodotto_id,),
        ).fetchone()
        return dict(row) if row else None


def add_prodotto(
    filiale_id: int,
    nome: str,
    pezzi_previsti: int = 0,
    pezzi_effettivi: int = 0,
    scadenza: Any = None,
    non_scade: bool = False,
    ultima_verifica: str | None = None,
    note: str | None = None,
    cassetta: str = "fissa",
) -> int:
    scadenza_iso = None if non_scade else _parse_date(scadenza)
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO prodotti (
                filiale_id, nome, pezzi_previsti, pezzi_effettivi,
                scadenza, non_scade, ultima_verifica, note, cassetta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filiale_id,
                nome.strip(),
                int(pezzi_previsti or 0),
                int(pezzi_effettivi or 0),
                scadenza_iso,
                1 if non_scade else 0,
                ultima_verifica,
                note,
                _cassetta(cassetta),
            ),
        )
        return int(cur.lastrowid)


def update_prodotto(prodotto_id: int, **fields: Any) -> None:
    allowed = {
        "nome", "pezzi_previsti", "pezzi_effettivi", "scadenza",
        "non_scade", "ultima_verifica", "note", "filiale_id", "cassetta",
    }
    data = {k: v for k, v in fields.items() if k in allowed}
    if "cassetta" in data:
        data["cassetta"] = _cassetta(data["cassetta"])
    if "non_scade" in data:
        data["non_scade"] = 1 if data["non_scade"] else 0
        if data["non_scade"]:
            data["scadenza"] = None
    if "scadenza" in data and data.get("non_scade") != 1:
        data["scadenza"] = _parse_date(data["scadenza"])
    if not data:
        return
    cols = ", ".join(f"{k} = ?" for k in data)
    values = list(data.values()) + [prodotto_id]
    with connect() as conn:
        conn.execute(f"UPDATE prodotti SET {cols} WHERE id = ?", values)


def delete_prodotto(prodotto_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM prodotti WHERE id = ?", (prodotto_id,))


def count_prodotti(filiale_id: int | None = None) -> int:
    with connect() as conn:
        if filiale_id is None:
            row = conn.execute("SELECT COUNT(*) AS c FROM prodotti").fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM prodotti WHERE filiale_id = ?",
                (filiale_id,),
            ).fetchone()
        return int(row["c"])


# ---------------------------------------------------------------------------
#  Alert e scadenze
# ---------------------------------------------------------------------------

def prodotti_in_alert(giorni: int = 15, filiale_id: int | None = None) -> list[dict[str, Any]]:
    """Prodotti esauriti, scaduti o in scadenza entro N giorni."""
    oggi = date.today()
    limite = oggi.toordinal() + int(giorni)
    prodotti = list_prodotti(filiale_id)
    risultati: list[dict[str, Any]] = []
    for p in prodotti:
        effettivi = int(p.get("pezzi_effettivi") or 0)
        if effettivi <= 0:
            item = dict(p)
            item["giorni_rimasti"] = -10_000  # in cima: da riordinare subito
            item["stato"] = "esaurito"
            risultati.append(item)
            continue
        if p["non_scade"] or not p["scadenza"]:
            continue
        scad = date.fromisoformat(p["scadenza"])
        giorni_rimasti = (scad - oggi).days
        if scad.toordinal() <= limite:
            item = dict(p)
            item["giorni_rimasti"] = giorni_rimasti
            item["stato"] = "scaduto" if giorni_rimasti < 0 else "in_scadenza"
            risultati.append(item)
    risultati.sort(key=lambda x: x["giorni_rimasti"])
    return risultati


def stato_prodotto(prodotto: dict[str, Any], giorni_alert: int = 15) -> str:
    # Quantità a zero = esaurito (priorità su scadenza)
    if int(prodotto.get("pezzi_effettivi") or 0) <= 0:
        return "esaurito"
    if prodotto.get("non_scade"):
        return "non_scade"
    if not prodotto.get("scadenza"):
        return "senza_data"
    giorni = (date.fromisoformat(prodotto["scadenza"]) - date.today()).days
    if giorni < 0:
        return "scaduto"
    if giorni <= giorni_alert:
        return "in_scadenza"
    return "ok"


# ---------------------------------------------------------------------------
#  Alert posticipati
# ---------------------------------------------------------------------------

def posticipa_alert(
    prodotto_id: int,
    mese_corrente: str,
    mese_destinazione: str,
    utente_id: int | None = None,
    note: str | None = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO alert_posticipati
                (prodotto_id, posticipato_da, posticipato_a, creato_il, utente_id, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                prodotto_id,
                mese_corrente,
                mese_destinazione,
                datetime.now().isoformat(timespec="seconds"),
                utente_id,
                note,
            ),
        )
        return int(cur.lastrowid)


def alert_posticipati_attivi(mese: str | None = None) -> list[dict[str, Any]]:
    """Prodotti posticipati a un dato mese (formato YYYY-MM), o tutti se mese=None."""
    with connect() as conn:
        if mese:
            rows = conn.execute(
                """
                SELECT ap.*, p.nome AS prodotto_nome, p.cassetta AS cassetta, f.nome AS filiale_nome
                FROM alert_posticipati ap
                JOIN prodotti p ON p.id = ap.prodotto_id
                JOIN filiali f ON f.id = p.filiale_id
                WHERE ap.posticipato_a = ?
                ORDER BY ap.creato_il DESC
                """,
                (mese,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT ap.*, p.nome AS prodotto_nome, p.cassetta AS cassetta, f.nome AS filiale_nome
                FROM alert_posticipati ap
                JOIN prodotti p ON p.id = ap.prodotto_id
                JOIN filiali f ON f.id = p.filiale_id
                ORDER BY ap.posticipato_a, ap.creato_il DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]


def is_posticipato(prodotto_id: int, mese: str) -> bool:
    """Verifica se un prodotto è posticipato per il mese corrente (YYYY-MM)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM alert_posticipati "
            "WHERE prodotto_id = ? AND posticipato_da = ?",
            (prodotto_id, mese),
        ).fetchone()
        return int(row["c"]) > 0


def rimuovi_posticipo(posticipo_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM alert_posticipati WHERE id = ?", (posticipo_id,))


def copia_catalogo(da_filiale_id: int, a_filiale_id: int, solo_vuota: bool = True) -> int:
    with connect() as conn:
        if solo_vuota:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM prodotti WHERE filiale_id = ?",
                (a_filiale_id,),
            ).fetchone()["c"]
            if n:
                return 0
        source = conn.execute(
            "SELECT * FROM prodotti WHERE filiale_id = ?",
            (da_filiale_id,),
        ).fetchall()
        count = 0
        for row in source:
            conn.execute(
                """
                INSERT INTO prodotti (
                    filiale_id, nome, pezzi_previsti, pezzi_effettivi,
                    scadenza, non_scade, ultima_verifica, note, cassetta
                ) VALUES (?, ?, ?, 0, NULL, ?, NULL, ?, ?)
                """,
                (
                    a_filiale_id,
                    row["nome"],
                    row["pezzi_previsti"],
                    row["non_scade"],
                    row["note"],
                    row["cassetta"],
                ),
            )
            count += 1
        return count
