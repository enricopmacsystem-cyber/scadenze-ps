from __future__ import annotations

from datetime import date, timedelta
from functools import wraps
from pathlib import Path
import secrets
from typing import Any

from flask import (    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from app import database as db
from app.email_alerts import (
    check_and_send_alerts,
    notify_prodotto_esaurito,
    smtp_ready,
)
from app.excel_import import import_excel, preview_excel
from app.icons import icon
from app.paths import UPLOADS_DIR, ensure_dirs
from app.security import (
    app_secret_key,
    clear_login_failures,
    login_rate_limited,
    new_csrf_token,
    password_policy_ok,
    register_login_failure,
    strong_temp_password,
    validate_csrf,
)
from app.settings import load_settings, posticipo_attivo, save_settings

STATO_LABEL = {
    "ok": "OK",
    "in_scadenza": "In scadenza",
    "scaduto": "Scaduto",
    "esaurito": "Esaurito",
    "non_scade": "Non scade",
    "senza_data": "Senza data",
}

_ALLOWED_EXCEL_EXT = {".xlsx", ".xlsm"}
_XLSX_MAGIC = b"PK"  # Office Open XML = ZIP


def _validate_excel_upload(file_storage: Any) -> tuple[str | None, str | None]:
    """
    Valida upload Excel: estensione, nome sicuro, magic ZIP.
    Ritorna (secure_name, error_message).
    """
    raw_name = (getattr(file_storage, "filename", None) or "").strip()
    if not raw_name:
        return None, "Seleziona un file Excel"
    safe = secure_filename(raw_name)
    if not safe or safe in {".", ".."}:
        return None, "Nome file non valido"
    ext = Path(safe).suffix.lower()
    if ext not in _ALLOWED_EXCEL_EXT:
        return None, "Formato non consentito: usa .xlsx o .xlsm"
    # Peek magic bytes senza consumare tutto lo stream
    head = file_storage.stream.read(4)
    try:
        file_storage.stream.seek(0)
    except Exception:
        pass
    if not head.startswith(_XLSX_MAGIC):
        return None, "Il file non sembra un Excel valido (.xlsx/.xlsm)"
    return safe, None


def _safe_upload_path(secure_name: str) -> Path:
    """Percorso unico sotto UPLOADS_DIR (niente path traversal / overwrite cieco)."""
    ensure_dirs()
    ext = Path(secure_name).suffix.lower() or ".xlsx"
    unique = f"{secrets.token_hex(8)}_{Path(secure_name).stem[:40]}{ext}"
    path = (UPLOADS_DIR / unique).resolve()
    uploads_root = UPLOADS_DIR.resolve()
    if uploads_root not in path.parents and path != uploads_root:
        raise ValueError("Percorso upload non consentito")
    return path


def create_app() -> Flask:
    ensure_dirs()
    db.init_db()

    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent.parent / "templates"),
        static_folder=str(Path(__file__).resolve().parent.parent / "static"),
    )
    app.secret_key = app_secret_key()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=10),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    )

    @app.before_request
    def load_user() -> None:
        g.user = None
        uid = session.get("user_id")
        if uid:
            user = db.get_utente_by_id(int(uid))
            if user and user.get("attivo"):
                g.user = user
        if "csrf_token" not in session:
            session["csrf_token"] = new_csrf_token()

    @app.before_request
    def csrf_protect() -> Any:
        if request.method != "POST":
            return None
        if request.endpoint in {None, "static"}:
            return None
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if validate_csrf(session.get("csrf_token"), token):
            return None
        flash("Sessione non valida (CSRF). Ricarica la pagina e riprova.", "error")
        if request.endpoint == "login":
            return render_template("login.html", error="Sessione scaduta, riprova.")
        return redirect(request.referrer or url_for("dashboard"))

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.user:
                return redirect(url_for("login"))
            if g.user.get("must_change_password") and request.endpoint not in {
                "change_password",
                "logout",
                "static",
            }:
                flash("Devi cambiare la password al primo accesso.", "warning")
                return redirect(url_for("change_password"))
            return view(*args, **kwargs)

        return wrapped

    def role_required(*roles):
        def decorator(view):
            @wraps(view)
            @login_required
            def wrapped(*args, **kwargs):
                if g.user["ruolo"] not in roles:
                    flash("Accesso non consentito.", "error")
                    return redirect(url_for("dashboard"))
                return view(*args, **kwargs)

            return wrapped

        return decorator

    # ----- auth -----
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user and not g.user.get("must_change_password"):
            return redirect(url_for("dashboard"))
        error = None
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password", "")
            rate_key = f"{request.remote_addr}|{username.lower()}"
            if login_rate_limited(rate_key):
                error = "Troppi tentativi. Riprova tra qualche minuto."
            else:
                user = db.authenticate(username, password)
                if not user:
                    register_login_failure(rate_key)
                    error = "Credenziali non valide"
                else:
                    clear_login_failures(rate_key)
                    session.clear()
                    session["csrf_token"] = new_csrf_token()
                    session.permanent = True
                    session["user_id"] = user["id"]
                    if user.get("must_change_password"):
                        flash("Cambia la password prima di continuare.", "warning")
                        return redirect(url_for("change_password"))
                    ruolo = (user.get("ruolo") or "").strip().lower()
                    if ruolo == "responsabile_ordini":
                        settings = load_settings()
                        giorni = int(settings.get("alert_days") or 15)
                        n_alert = len(db.prodotti_in_alert(giorni))
                        if n_alert:
                            flash(
                                f"Ci sono {n_alert} prodotti in alert (scaduti o entro {giorni} giorni).",
                                "warning",
                            )
                        else:
                            flash("Nessun prodotto in alert al momento.", "success")
                        return redirect(url_for("dashboard", view="alert"))
                    return redirect(url_for("dashboard"))
        return render_template("login.html", error=error)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/change-password", methods=["GET", "POST"])
    @login_required
    def change_password():
        error = None
        forced = bool(g.user.get("must_change_password"))
        if request.method == "POST":
            p1 = request.form.get("password", "")
            p2 = request.form.get("password2", "")
            ok_pw, msg_pw = password_policy_ok(p1)
            if not ok_pw:
                error = msg_pw
            elif p1 != p2:
                error = "Le due password non coincidono"
            else:
                db.change_password(g.user["id"], p1, clear_must_change=True)
                flash("Password aggiornata.", "success")
                return redirect(url_for("dashboard"), code=303)
        return render_template(
            "change_password.html",
            error=error,
            forced=forced,
            hide_shell=forced,
        )

    # ----- dashboard / prodotti -----
    @app.route("/", methods=["GET", "POST"])
    @login_required
    def dashboard():
        if request.method == "POST":
            return redirect(url_for("dashboard"), code=303)
        settings = load_settings()
        giorni = int(settings.get("alert_days") or 15)
        ruolo = (g.user.get("ruolo") or "").strip().lower()
        # Solo le filiali consentite: filiale→proprie; admin/ordini→tutte
        filiali = db.list_filiali_for_user(g.user)
        allowed_ids = {int(f["id"]) for f in filiali}
        is_global = ruolo in {"admin", "responsabile_ordini"}

        view = request.args.get("view")
        raw_filiale = request.args.get("filiale")
        cassetta = _cassetta_arg(request.args.get("cassetta"))
        posticipo = posticipo_attivo(settings)
        if view == "posticipati" and not posticipo:
            return redirect(url_for("dashboard"))

        if is_global and view == "alert":
            prodotti = db.prodotti_in_alert(giorni)
            selected = -1
        elif is_global and view == "posticipati":
            mese = date.today().strftime("%Y-%m")
            posticipati = db.alert_posticipati_attivi(mese)
            return render_template(
                "posticipati.html",
                posticipati=posticipati,
                filiali=filiali,
                giorni=giorni,
                selected=-2,
                mese=mese,
                read_only=True,
            )
        else:
            selected = _parse_filiale_arg(raw_filiale, allowed_ids, multi=len(filiali) > 1)
            if selected is None:
                # Tutte (admin/ordini) oppure entrambe le cassette Gruaro
                if is_global:
                    prodotti = db.list_prodotti(None, cassetta)
                else:
                    prodotti = []
                    for f in filiali:
                        prodotti.extend(db.list_prodotti(int(f["id"]), cassetta))
            else:
                prodotti = db.list_prodotti(selected, cassetta)

        mese = date.today().strftime("%Y-%m")
        rows = []
        alert_count = 0
        for p in prodotti:
            # Sicurezza: utente filiale non vede mai altre filiali
            if not is_global and int(p["filiale_id"]) not in allowed_ids:
                continue
            stato = db.stato_prodotto(p, giorni)
            if stato in {"in_scadenza", "scaduto", "esaurito"}:
                alert_count += 1
            posticipato = posticipo and db.is_posticipato(p["id"], mese)
            rows.append({**p, "stato": "posticipato" if posticipato else stato,
                         "stato_label": "Posticipato" if posticipato else STATO_LABEL[stato]})

        can_edit = False
        if ruolo == "admin":
            can_edit = True
        elif ruolo == "filiale":
            can_edit = selected in allowed_ids if selected is not None else bool(filiali)
        # responsabile_ordini: sola lettura (può solo posticipare / inviare email)
        # Per riga: admin tutto; filiale = list_filiali_for_user (Gruaro = entrambe)
        editable_filiale_ids = allowed_ids if ruolo in {"admin", "filiale"} else set()

        return render_template(
            "dashboard.html",
            prodotti=rows,
            filiali=filiali,
            selected=selected,
            giorni=giorni,
            alert_count=alert_count,
            can_edit=can_edit,
            editable_filiale_ids=editable_filiale_ids,
            is_global=is_global,
            read_only=(ruolo == "responsabile_ordini"),
            cassetta=None if selected == -1 else cassetta,
        )

    def _cassetta_arg(raw: str | None) -> str:
        return "portatile" if (raw or "").strip().lower() == "portatile" else "fissa"

    def _dashboard_url(filiale_id: int, cassetta: str | None) -> str:
        if cassetta == "portatile":
            return url_for("dashboard", filiale=filiale_id, cassetta="portatile")
        return url_for("dashboard", filiale=filiale_id)

    def _parse_filiale_arg(
        raw: str | None,
        allowed_ids: set[int],
        multi: bool,
    ) -> int | None:
        """None = tutte/entrambe; altrimenti id filiale consentito."""
        if raw in (None, "", "all"):
            if multi or (g.user.get("ruolo") or "").strip().lower() in {
                "admin",
                "responsabile_ordini",
            }:
                return None
            # Una sola filiale: mostra sempre quella
            return next(iter(allowed_ids)) if allowed_ids else None
        try:
            fid = int(raw)
        except (TypeError, ValueError):
            return None if multi else (next(iter(allowed_ids)) if allowed_ids else None)
        if fid not in allowed_ids:
            if multi or (g.user.get("ruolo") or "").strip().lower() in {
                "admin",
                "responsabile_ordini",
            }:
                return None
            return next(iter(allowed_ids)) if allowed_ids else None
        return fid

    def _can_edit(filiale_id: int | None) -> bool:
        if not g.user:
            return False
        ruolo = (g.user.get("ruolo") or "").strip().lower()
        if ruolo == "admin":
            return True
        if ruolo == "responsabile_ordini":
            return False
        if ruolo == "filiale" and filiale_id is not None:
            allowed = {int(f["id"]) for f in db.list_filiali_for_user(g.user)}
            return int(filiale_id) in allowed
        return False

    def _editable_filiali():
        ruolo = (g.user.get("ruolo") or "").strip().lower()
        if ruolo == "responsabile_ordini":
            return []
        return db.list_filiali_for_user(g.user)

    @app.route("/prodotti/nuovo", methods=["GET", "POST"])
    @login_required
    def prodotto_nuovo():
        filiali = _editable_filiali()
        if not filiali:
            flash("Non puoi aggiungere prodotti.", "error")
            return redirect(url_for("dashboard"))
        error = None
        cassetta = _cassetta_arg(request.values.get("cassetta"))
        if request.method == "POST":
            try:
                fid = int(request.form["filiale_id"])
                if not _can_edit(fid):
                    raise PermissionError("Filiale non consentita")
                non_scade = request.form.get("non_scade") == "on"
                effettivi = int(request.form.get("pezzi_effettivi") or 0)
                new_id = db.add_prodotto(
                    cassetta=cassetta,
                    filiale_id=fid,
                    nome=request.form["nome"],
                    pezzi_previsti=int(request.form.get("pezzi_previsti") or 0),
                    pezzi_effettivi=effettivi,
                    scadenza=None if non_scade else request.form.get("scadenza"),
                    non_scade=non_scade,
                    note=request.form.get("note") or None,
                )
                flash("Prodotto aggiunto.", "success")
                if effettivi <= 0:
                    creato = db.get_prodotto(new_id)
                    if creato:
                        mail = notify_prodotto_esaurito(creato)
                        flash(mail["message"], "success" if mail["sent"] else "warning")
                return redirect(_dashboard_url(fid, cassetta))
            except Exception as exc:
                error = str(exc)
        return render_template(
            "prodotto_form.html", prodotto=None, filiali=filiali, error=error,
            cassetta=cassetta, selected_filiale=request.args.get("filiale", type=int),
        )

    @app.route("/prodotti/<int:pid>/modifica", methods=["GET", "POST"])
    @login_required
    def prodotto_modifica(pid: int):
        prodotto = db.get_prodotto(pid)
        if not prodotto or not _can_edit(prodotto["filiale_id"]):
            flash("Prodotto non trovato o accesso negato.", "error")
            return redirect(url_for("dashboard"))
        filiali = _editable_filiali()
        error = None
        if request.method == "POST":
            try:
                fid = int(request.form["filiale_id"])
                if not _can_edit(fid):
                    raise PermissionError("Filiale non consentita")
                non_scade = request.form.get("non_scade") == "on"
                old_eff = int(prodotto.get("pezzi_effettivi") or 0)
                new_eff = int(request.form.get("pezzi_effettivi") or 0)
                cassetta = _cassetta_arg(request.form.get("cassetta"))
                db.update_prodotto(
                    pid,
                    filiale_id=fid,
                    cassetta=cassetta,
                    nome=request.form["nome"],
                    pezzi_previsti=int(request.form.get("pezzi_previsti") or 0),
                    pezzi_effettivi=new_eff,
                    scadenza=None if non_scade else request.form.get("scadenza"),
                    non_scade=non_scade,
                    note=request.form.get("note") or None,
                )
                flash("Prodotto aggiornato.", "success")
                # Passaggio a quantità 0 → esaurito + mail riordino immediata
                if old_eff > 0 and new_eff <= 0:
                    aggiornato = db.get_prodotto(pid)
                    if aggiornato:
                        mail = notify_prodotto_esaurito(aggiornato)
                        flash(mail["message"], "success" if mail["sent"] else "warning")
                return redirect(_dashboard_url(fid, cassetta))
            except Exception as exc:
                error = str(exc)
        return render_template(
            "prodotto_form.html", prodotto=prodotto, filiali=filiali, error=error,
            cassetta=prodotto.get("cassetta") or "fissa", selected_filiale=None,
        )

    @app.route("/prodotti/<int:pid>/elimina", methods=["POST"])
    @login_required
    def prodotto_elimina(pid: int):
        prodotto = db.get_prodotto(pid)
        if not prodotto or not _can_edit(prodotto["filiale_id"]):
            flash("Accesso negato.", "error")
            return redirect(url_for("dashboard"))
        db.delete_prodotto(pid)
        flash("Prodotto eliminato.", "success")
        return redirect(_dashboard_url(prodotto["filiale_id"], prodotto.get("cassetta")))

    # ----- import -----
    @app.route("/import", methods=["GET", "POST"])
    @login_required
    def import_page():
        filiali = _editable_filiali()
        if not filiali:
            flash("Non puoi importare Excel.", "error")
            return redirect(url_for("dashboard"))
        error = None
        if request.method == "POST":
            f = request.files.get("excel")
            if not f or not f.filename:
                error = "Seleziona un file Excel"
            else:
                fid = int(request.form["filiale_id"])
                if not _can_edit(fid):
                    error = "Filiale non consentita"
                else:
                    safe_name, err = _validate_excel_upload(f)
                    if err or not safe_name:
                        error = err or "File non valido"
                    else:
                        nome = next(x["nome"] for x in filiali if x["id"] == fid)
                        try:
                            path = _safe_upload_path(safe_name)
                            f.save(path)
                            anteprima = preview_excel(path)
                            # Le righe con SEDE Showroom/Magazzino vanno nelle cassette corrette
                            result = import_excel(path, filiale_nome=nome, replace=True)
                            fogli = ", ".join(result.get("fogli") or [])
                            flash(
                                f"Importati {result['importati']} prodotti in {result['filiale']}"
                                f" (anteprima {anteprima.get('totale', 0)} da {fogli or 'foglio'}).",
                                "success",
                            )
                            return redirect(url_for("dashboard", filiale=fid))
                        except Exception as exc:
                            error = (
                                f"Impossibile leggere il file: {exc}. "
                                "Controlla che ci siano colonne Prodotto / Pezzi / Scadenza "
                                "(anche con nomi diversi)."
                            )
        return render_template("import.html", filiali=filiali, error=error)

    # ----- posticipo / alert -----
    @app.route("/posticipa/<int:pid>", methods=["POST"])
    @role_required("admin", "responsabile_ordini")
    def posticipa(pid: int):
        if not posticipo_attivo():
            flash("La funzione «Posticipa mese» non è attiva.", "warning")
            return redirect(url_for("dashboard", view="alert"))
        prodotto = db.get_prodotto(pid)
        if not prodotto:
            flash("Prodotto non trovato.", "error")
            return redirect(url_for("dashboard", view="alert"))
        oggi = date.today()
        mese_corrente = oggi.strftime("%Y-%m")
        if oggi.month == 12:
            mese_next = f"{oggi.year + 1}-01"
        else:
            mese_next = f"{oggi.year}-{oggi.month + 1:02d}"
        if db.is_posticipato(pid, mese_corrente):
            flash("Già posticipato per questo mese.", "warning")
        else:
            db.posticipa_alert(pid, mese_corrente, mese_next, g.user["id"], "Ordine cumulativo")
            flash(f"Posticipato a {mese_next}.", "success")
        return redirect(url_for("dashboard", view="alert"))

    @app.route("/alert/invia", methods=["POST"])
    @role_required("admin", "responsabile_ordini")
    def invia_alert():
        result = check_and_send_alerts(force=True)
        flash(result["message"], "success" if result["sent"] else "warning")
        return redirect(url_for("dashboard", view="alert"))

    @app.route("/profilo-email", methods=["GET", "POST"])
    @login_required
    def profilo_email():
        """Email personale: usata per ricevere gli alert (responsabile ordini)."""
        error = None
        if request.method == "POST":
            email = (request.form.get("email") or "").strip()
            if email and "@" not in email:
                error = "Indirizzo email non valido"
            else:
                db.update_utente(g.user["id"], email=email or None)
                g.user["email"] = email or None
                flash(
                    "Email salvata. Riceverai gli alert anche via posta."
                    if email
                    else "Email rimossa.",
                    "success",
                )
                return redirect(url_for("dashboard", view="alert"))
        return render_template(
            "profilo_email.html",
            email=g.user.get("email") or "",
            error=error,
        )

    # ----- admin -----
    @app.route("/admin/utenti", methods=["GET", "POST"])
    @role_required("admin")
    def admin_utenti():
        error = None
        if request.method == "POST":
            action = request.form.get("action")
            try:
                if action == "add":
                    pw = request.form.get("password") or strong_temp_password()
                    db.add_utente(
                        username=request.form["username"],
                        password=pw,
                        nome_completo=request.form.get("nome_completo") or "",
                        ruolo=request.form["ruolo"],
                        filiale_id=request.form.get("filiale_id", type=int) or None,
                        email=request.form.get("email") or None,
                    )
                    flash(
                        f"Utente creato. Password temporanea: {pw} "
                        "(cambio obbligatorio al primo accesso).",
                        "success",
                    )
                elif action == "toggle":
                    uid = int(request.form["utente_id"])
                    utenti = db.list_utenti()
                    u = next(x for x in utenti if x["id"] == uid)
                    db.update_utente(uid, attivo=0 if u["attivo"] else 1)
                    flash("Stato utente aggiornato.", "success")
                elif action == "reset_pw":
                    uid = int(request.form["utente_id"])
                    temp = strong_temp_password()
                    db.change_password(uid, temp, clear_must_change=False)
                    flash(
                        f"Password resettata a: {temp} — cambio obbligatorio al prossimo accesso.",
                        "success",
                    )
            except Exception as exc:
                error = str(exc)
        return render_template(
            "admin_utenti.html",
            utenti=db.list_utenti(),
            filiali=[dict(r) for r in db.list_filiali()],
            ruoli=db.RUOLI,
            error=error,
        )

    @app.route("/admin/impostazioni", methods=["GET", "POST"])
    @role_required("admin")
    def admin_impostazioni():
        settings = load_settings()
        if request.method == "POST":
            prev = load_settings()
            settings["alert_days"] = int(request.form.get("alert_days") or 15)
            # Forza spegnimento finché il go-live non è esplicitamente riattivato nel codice
            settings["email_alerts_enabled"] = False
            settings["posticipo_enabled"] = request.form.get("posticipo_enabled") == "on"
            settings["recipients"] = [
                x.strip() for x in request.form.get("recipients", "").splitlines() if x.strip()
            ]
            # Parse "Filiale: email1, email2"
            fe: dict[str, list[str]] = {}
            for line in (request.form.get("filiale_emails_text") or "").splitlines():
                line = line.strip()
                if not line or ":" not in line:
                    continue
                nome, _, rest = line.partition(":")
                nome = nome.strip()
                emails = [x.strip() for x in rest.replace(";", ",").split(",") if x.strip()]
                if nome:
                    fe[nome] = emails
            settings["filiale_emails"] = fe
            new_pw = request.form.get("password", "")
            settings["smtp"] = {
                "host": request.form.get("host", "").strip(),
                "port": int(request.form.get("port") or 587),
                "use_tls": request.form.get("use_tls") == "on",
                "username": request.form.get("username", "").strip(),
                "password": new_pw if new_pw else (prev.get("smtp") or {}).get("password", ""),
                "from_email": request.form.get("from_email", "").strip(),
                "from_name": request.form.get("from_name", "Scadenze PS").strip() or "Scadenze PS",
            }
            save_settings(settings)
            flash("Impostazioni salvate.", "success")
            return redirect(url_for("admin_impostazioni"))
        ok, msg = smtp_ready(settings)
        return render_template("admin_impostazioni.html", settings=settings, smtp_ok=ok, smtp_msg=msg)

    @app.route("/guida")
    @login_required
    def guida():
        return render_template("guida.html")

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        return {
            "current_user": getattr(g, "user", None),
            "STATO_LABEL": STATO_LABEL,
            "icon": icon,
            "posticipo_attivo": posticipo_attivo() if getattr(g, "user", None) else False,
            "today": date.today().isoformat(),
            "hide_shell": False,
            "csrf_token": session.get("csrf_token", ""),
        }

    return app


def os_secret() -> str:
    """Compat: delega a app_secret_key."""
    return app_secret_key()
