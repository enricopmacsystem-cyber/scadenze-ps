from __future__ import annotations

from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any

import customtkinter as ctk

from app import database as db
from app.email_alerts import check_and_send_alerts, smtp_ready
from app.excel_import import import_excel
from app.settings import load_settings, save_settings

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")

STATO_LABEL = {
    "ok": "OK",
    "in_scadenza": "In scadenza",
    "scaduto": "Scaduto",
    "esaurito": "Esaurito",
    "non_scade": "Non scade",
    "senza_data": "Senza data",
}

STATO_COLOR = {
    "ok": "#1b7f4e",
    "in_scadenza": "#b36b00",
    "scaduto": "#b00020",
    "esaurito": "#6b21a8",
    "non_scade": "#555555",
    "senza_data": "#6a6a6a",
}


# ===========================================================================
#  Login
# ===========================================================================

class LoginWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Scadenze PS — Accesso")
        self.geometry("440x420")
        self.minsize(440, 420)
        self.resizable(False, False)
        self.user: dict | None = None

        frame = ctk.CTkFrame(self)
        frame.pack(expand=True, fill="both", padx=36, pady=28)

        ctk.CTkLabel(
            frame, text="Scadenze PS", font=ctk.CTkFont(size=24, weight="bold")
        ).pack(pady=(20, 4))
        ctk.CTkLabel(frame, text="Accedi con le tue credenziali", text_color="#666").pack(
            pady=(0, 24)
        )

        ctk.CTkLabel(frame, text="Username", anchor="w").pack(fill="x", padx=24)
        self.username = ctk.CTkEntry(frame, width=320, height=36, placeholder_text="username")
        self.username.pack(padx=24, pady=(4, 12))

        ctk.CTkLabel(frame, text="Password", anchor="w").pack(fill="x", padx=24)
        self.password = ctk.CTkEntry(frame, width=320, height=36, show="*", placeholder_text="password")
        self.password.pack(padx=24, pady=(4, 20))

        self.password.bind("<Return>", lambda _e: self._login())

        ctk.CTkButton(
            frame,
            text="Accedi",
            width=220,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._login,
        ).pack(pady=(4, 12))

        self.error_label = ctk.CTkLabel(frame, text="", text_color="#b00020", height=24)
        self.error_label.pack(pady=(0, 12))

    def _login(self) -> None:
        u = self.username.get().strip()
        p = self.password.get().strip()
        if not u or not p:
            self.error_label.configure(text="Inserisci username e password")
            return
        user = db.authenticate(u, p)
        if not user:
            self.error_label.configure(text="Credenziali non valide")
            return
        self.user = user
        self.destroy()


# ===========================================================================
#  Dialogs
# ===========================================================================

class ProductDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, filiali: list[dict], prodotto: dict | None = None, lock_filiale: bool = False):
        super().__init__(master)
        self.title("Prodotto" if prodotto else "Nuovo prodotto")
        self.geometry("560x480")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result: dict | None = None

        pad = {"padx": 16, "pady": 6}
        ctk.CTkLabel(self, text="Filiale").pack(anchor="w", **pad)
        state = "disabled" if lock_filiale else "readonly"
        self.filiale = ctk.CTkComboBox(
            self, values=[f["nome"] for f in filiali], width=500, state=state
        )
        self.filiale.pack(anchor="w", padx=16)
        if prodotto:
            self.filiale.set(prodotto["filiale"])
        elif filiali:
            self.filiale.set(filiali[0]["nome"])

        ctk.CTkLabel(self, text="Nome prodotto").pack(anchor="w", **pad)
        self.nome = ctk.CTkEntry(self, width=500)
        self.nome.pack(anchor="w", padx=16)
        if prodotto:
            self.nome.insert(0, prodotto["nome"])

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(row, text="Pezzi previsti").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(row, text="Pezzi effettivi").grid(row=0, column=1, sticky="w", padx=(24, 0))
        self.previsti = ctk.CTkEntry(row, width=120)
        self.previsti.grid(row=1, column=0, sticky="w")
        self.effettivi = ctk.CTkEntry(row, width=120)
        self.effettivi.grid(row=1, column=1, sticky="w", padx=(24, 0))
        self.previsti.insert(0, str(prodotto["pezzi_previsti"] if prodotto else 1))
        self.effettivi.insert(0, str(prodotto["pezzi_effettivi"] if prodotto else 1))

        self.non_scade = ctk.CTkCheckBox(self, text="Non scade", command=self._toggle_scadenza)
        self.non_scade.pack(anchor="w", padx=16, pady=8)

        ctk.CTkLabel(self, text="Scadenza (GG/MM/AAAA)").pack(anchor="w", **pad)
        self.scadenza = ctk.CTkEntry(self, width=200, placeholder_text="31/12/2026")
        self.scadenza.pack(anchor="w", padx=16)
        if prodotto:
            if prodotto.get("non_scade"):
                self.non_scade.select()
                self.scadenza.configure(state="disabled")
            elif prodotto.get("scadenza"):
                d = date.fromisoformat(prodotto["scadenza"])
                self.scadenza.insert(0, d.strftime("%d/%m/%Y"))

        ctk.CTkLabel(self, text="Note").pack(anchor="w", **pad)
        self.note = ctk.CTkEntry(self, width=500)
        self.note.pack(anchor="w", padx=16)
        if prodotto and prodotto.get("note"):
            self.note.insert(0, prodotto["note"])

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=20)
        ctk.CTkButton(btns, text="Annulla", width=120, fg_color="#666", command=self.destroy).pack(side="right", padx=6)
        ctk.CTkButton(btns, text="Salva", width=120, command=self._save).pack(side="right")
        self.after(50, self.lift)

    def _toggle_scadenza(self) -> None:
        if self.non_scade.get():
            self.scadenza.delete(0, "end")
            self.scadenza.configure(state="disabled")
        else:
            self.scadenza.configure(state="normal")

    def _save(self) -> None:
        nome = self.nome.get().strip()
        if not nome:
            messagebox.showwarning("Attenzione", "Inserire il nome del prodotto.", parent=self)
            return
        non_scade = bool(self.non_scade.get())
        scadenza = self.scadenza.get().strip() or None
        if not non_scade and not scadenza:
            messagebox.showwarning("Attenzione", "Inserire la scadenza oppure segnare 'Non scade'.", parent=self)
            return
        try:
            previsti = int(self.previsti.get().strip() or 0)
            effettivi = int(self.effettivi.get().strip() or 0)
        except ValueError:
            messagebox.showwarning("Attenzione", "I pezzi devono essere numeri interi.", parent=self)
            return
        if scadenza and not non_scade:
            try:
                datetime.strptime(scadenza, "%d/%m/%Y")
            except ValueError:
                messagebox.showwarning("Attenzione", "Formato data non valido. Usa GG/MM/AAAA.", parent=self)
                return
        self.result = {
            "filiale": self.filiale.get(),
            "nome": nome,
            "pezzi_previsti": previsti,
            "pezzi_effettivi": effettivi,
            "non_scade": non_scade,
            "scadenza": scadenza,
            "note": self.note.get().strip() or None,
        }
        self.destroy()


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master: Any):
        super().__init__(master)
        self.title("Impostazioni email")
        self.geometry("620x560")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.settings = load_settings()

        scroll = ctk.CTkScrollableFrame(self, width=580, height=480)
        scroll.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(scroll, text="Giorni di preavviso alert", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 4))
        self.alert_days = ctk.CTkEntry(scroll, width=100)
        self.alert_days.pack(anchor="w")
        self.alert_days.insert(0, str(self.settings.get("alert_days", 15)))

        smtp = self.settings.get("smtp") or {}
        fields = [
            ("host", "Host SMTP", smtp.get("host", "")),
            ("port", "Porta", str(smtp.get("port", 587))),
            ("username", "Username", smtp.get("username", "")),
            ("password", "Password", ""),  # mai precompilare (cifrate o in chiaro)
            ("from_email", "Email mittente", smtp.get("from_email", "")),
            ("from_name", "Nome mittente", smtp.get("from_name", "Scadenze PS")),
        ]
        self.smtp_vars: dict[str, ctk.CTkEntry] = {}
        for key, label, value in fields:
            ctk.CTkLabel(scroll, text=label).pack(anchor="w", pady=(10, 2))
            show = "*" if key == "password" else None
            entry = ctk.CTkEntry(scroll, width=540, show=show)
            entry.pack(anchor="w")
            if key == "password":
                entry.configure(placeholder_text="Lascia vuoto per non modificare")
            else:
                entry.insert(0, value or "")
            self.smtp_vars[key] = entry

        self.use_tls = ctk.CTkCheckBox(scroll, text="Usa TLS (STARTTLS)")
        self.use_tls.pack(anchor="w", pady=10)
        if smtp.get("use_tls", True):
            self.use_tls.select()

        ctk.CTkLabel(scroll, text="Destinatari (uno per riga)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(8, 4))
        self.recipients = ctk.CTkTextbox(scroll, width=540, height=120)
        self.recipients.pack(anchor="w")
        self.recipients.insert("1.0", "\n".join(self.settings.get("recipients") or []))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(btns, text="Annulla", width=120, fg_color="#666", command=self.destroy).pack(side="right", padx=6)
        ctk.CTkButton(btns, text="Salva", width=120, command=self._save).pack(side="right")
        self.after(50, self.lift)

    def _save(self) -> None:
        try:
            giorni = int(self.alert_days.get().strip())
            if giorni < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Attenzione", "Giorni di preavviso non validi.", parent=self)
            return
        try:
            port = int(self.smtp_vars["port"].get().strip() or 587)
        except ValueError:
            messagebox.showwarning("Attenzione", "Porta SMTP non valida.", parent=self)
            return
        recipients = [l.strip() for l in self.recipients.get("1.0", "end").splitlines() if l.strip()]
        prev_smtp = self.settings.get("smtp") or {}
        new_pw = self.smtp_vars["password"].get()
        self.settings["alert_days"] = giorni
        self.settings["recipients"] = recipients
        self.settings["smtp"] = {
            "host": self.smtp_vars["host"].get().strip(),
            "port": port,
            "use_tls": bool(self.use_tls.get()),
            "username": self.smtp_vars["username"].get().strip(),
            "password": new_pw if new_pw else prev_smtp.get("password", ""),
            "from_email": self.smtp_vars["from_email"].get().strip(),
            "from_name": self.smtp_vars["from_name"].get().strip() or "Scadenze PS",
        }
        save_settings(self.settings)
        messagebox.showinfo("Salvato", "Impostazioni email salvate.", parent=self)
        self.destroy()


class ChangePasswordDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, utente_id: int):
        super().__init__(master)
        self.title("Cambia password")
        self.geometry("400x260")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.utente_id = utente_id

        ctk.CTkLabel(self, text="Nuova password").pack(anchor="w", padx=20, pady=(20, 4))
        self.pw1 = ctk.CTkEntry(self, width=340, show="*")
        self.pw1.pack(padx=20)
        ctk.CTkLabel(self, text="Conferma password").pack(anchor="w", padx=20, pady=(12, 4))
        self.pw2 = ctk.CTkEntry(self, width=340, show="*")
        self.pw2.pack(padx=20)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(btns, text="Annulla", width=100, fg_color="#666", command=self.destroy).pack(side="right", padx=6)
        ctk.CTkButton(btns, text="Salva", width=100, command=self._save).pack(side="right")
        self.after(50, self.lift)

    def _save(self) -> None:
        from app.security import password_policy_ok

        p1 = self.pw1.get()
        p2 = self.pw2.get()
        ok_pw, msg_pw = password_policy_ok(p1)
        if not ok_pw:
            messagebox.showwarning("Attenzione", msg_pw, parent=self)
            return
        if p1 != p2:
            messagebox.showwarning("Attenzione", "Le due password non coincidono.", parent=self)
            return
        db.change_password(self.utente_id, p1)
        messagebox.showinfo("OK", "Password aggiornata.", parent=self)
        self.destroy()


class UserDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, filiali: list[dict], utente: dict | None = None):
        super().__init__(master)
        self.title("Utente" if utente else "Nuovo utente")
        self.geometry("500x440")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result: dict | None = None

        pad = {"padx": 16, "pady": 6}
        ctk.CTkLabel(self, text="Username").pack(anchor="w", **pad)
        self.username = ctk.CTkEntry(self, width=440)
        self.username.pack(anchor="w", padx=16)
        if utente:
            self.username.insert(0, utente["username"])

        ctk.CTkLabel(self, text="Password" + (" (lascia vuoto per non cambiare)" if utente else "")).pack(anchor="w", **pad)
        self.password = ctk.CTkEntry(self, width=440, show="*")
        self.password.pack(anchor="w", padx=16)

        ctk.CTkLabel(self, text="Nome completo").pack(anchor="w", **pad)
        self.nome_completo = ctk.CTkEntry(self, width=440)
        self.nome_completo.pack(anchor="w", padx=16)
        if utente:
            self.nome_completo.insert(0, utente.get("nome_completo") or "")

        ctk.CTkLabel(self, text="Ruolo").pack(anchor="w", **pad)
        self.ruolo = ctk.CTkComboBox(self, values=list(db.RUOLI), width=300)
        self.ruolo.pack(anchor="w", padx=16)
        if utente:
            self.ruolo.set(utente["ruolo"])
        else:
            self.ruolo.set("filiale")

        ctk.CTkLabel(self, text="Filiale").pack(anchor="w", **pad)
        nomi = ["(nessuna)"] + [f["nome"] for f in filiali]
        self.filiale = ctk.CTkComboBox(self, values=nomi, width=300)
        self.filiale.pack(anchor="w", padx=16)
        if utente and utente.get("filiale_nome"):
            self.filiale.set(utente["filiale_nome"])
        else:
            self.filiale.set("(nessuna)")

        ctk.CTkLabel(self, text="Email").pack(anchor="w", **pad)
        self.email = ctk.CTkEntry(self, width=440)
        self.email.pack(anchor="w", padx=16)
        if utente and utente.get("email"):
            self.email.insert(0, utente["email"])

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=16)
        ctk.CTkButton(btns, text="Annulla", width=100, fg_color="#666", command=self.destroy).pack(side="right", padx=6)
        ctk.CTkButton(btns, text="Salva", width=100, command=self._save).pack(side="right")
        self.after(50, self.lift)

    def _save(self) -> None:
        username = self.username.get().strip()
        if not username:
            messagebox.showwarning("Attenzione", "Inserisci username.", parent=self)
            return
        password = self.password.get()
        filiale_nome = self.filiale.get()
        fmap = {f["nome"]: f["id"] for f in db.list_filiali()}
        filiale_id = fmap.get(filiale_nome)
        self.result = {
            "username": username,
            "password": password if password else None,
            "nome_completo": self.nome_completo.get().strip(),
            "ruolo": self.ruolo.get(),
            "filiale_id": filiale_id,
            "email": self.email.get().strip() or None,
        }
        self.destroy()


# ===========================================================================
#  Main application
# ===========================================================================

class App(ctk.CTk):
    def __init__(self, user: dict) -> None:
        super().__init__()
        self.current_user = user
        ruolo = user["ruolo"]
        filiale_nome = user.get("filiale_nome") or ""
        title_suffix = f" — {user['nome_completo'] or user['username']}"
        if ruolo == "filiale":
            title_suffix += f" ({filiale_nome})"
        elif ruolo == "responsabile_ordini":
            title_suffix += " (Resp. Ordini)"
        self.title(f"Scadenze PS{title_suffix}")
        self.geometry("1220x740")
        self.minsize(1000, 600)

        self.settings = load_settings()
        self.filiali = [dict(r) for r in db.list_filiali()]
        self.selected_filiale_id: int | None = None
        self._rows: list[dict] = []

        self._build_layout()

        if ruolo == "filiale" and user.get("filiale_id"):
            self._select_filiale(user["filiale_id"])
        elif ruolo == "responsabile_ordini":
            self._show_alerts()
        else:
            self._select_filiale(self.filiali[0]["id"] if self.filiali else None)

        self.after(400, self._startup_alert_hint)

    # ----- ruolo helpers -----
    @property
    def is_admin(self) -> bool:
        return self.current_user["ruolo"] == "admin"

    @property
    def is_responsabile(self) -> bool:
        return self.current_user["ruolo"] == "responsabile_ordini"

    @property
    def is_filiale(self) -> bool:
        return self.current_user["ruolo"] == "filiale"

    @property
    def user_filiale_id(self) -> int | None:
        return self.current_user.get("filiale_id")

    def _can_edit_filiale(self, filiale_id: int | None) -> bool:
        if self.is_admin:
            return True
        if self.is_responsabile:
            return False
        if self.is_filiale and filiale_id is not None:
            allowed = {int(f["id"]) for f in db.list_filiali_for_user(self.current_user)}
            return int(filiale_id) in allowed
        return False

    # ----- layout -----
    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        ctk.CTkLabel(sidebar, text="Scadenze PS", font=ctk.CTkFont(size=20, weight="bold")).pack(padx=16, pady=(20, 4), anchor="w")
        ctk.CTkLabel(sidebar, text="Filiali", text_color="#666").pack(padx=16, pady=(0, 12), anchor="w")

        self.filiale_buttons: dict[int, ctk.CTkButton] = {}

        if self.is_filiale:
            for f in db.list_filiali_for_user(self.current_user):
                btn = ctk.CTkButton(sidebar, text=f["nome"], anchor="w", fg_color="transparent",
                                    text_color=("gray10", "gray90"), hover_color=("gray80", "gray30"),
                                    command=lambda fid=f["id"]: self._select_filiale(fid))
                btn.pack(fill="x", padx=10, pady=2)
                self.filiale_buttons[f["id"]] = btn
        else:
            for f in self.filiali:
                btn = ctk.CTkButton(sidebar, text=f["nome"], anchor="w", fg_color="transparent",
                                    text_color=("gray10", "gray90"), hover_color=("gray80", "gray30"),
                                    command=lambda fid=f["id"]: self._select_filiale(fid))
                btn.pack(fill="x", padx=10, pady=2)
                self.filiale_buttons[f["id"]] = btn

            ctk.CTkButton(sidebar, text="Tutte le filiali", anchor="w",
                          command=lambda: self._select_filiale(None)).pack(fill="x", padx=10, pady=(16, 4))

        ctk.CTkButton(sidebar, text="Prodotti in alert", anchor="w", fg_color="#b36b00",
                      command=self._show_alerts).pack(fill="x", padx=10, pady=4)

        if self.is_responsabile:
            ctk.CTkButton(sidebar, text="Posticipati", anchor="w", fg_color="#4a6fa5",
                          command=self._show_posticipati).pack(fill="x", padx=10, pady=4)

        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=10, pady=12)
        ctk.CTkButton(bottom, text="Cambia password", anchor="w", fg_color="transparent",
                      text_color=("gray10", "gray90"), hover_color=("gray80", "gray30"),
                      command=self._change_password).pack(fill="x", pady=2)
        ctk.CTkButton(bottom, text="Logout", anchor="w", fg_color="#b00020",
                      command=self._logout).pack(fill="x", pady=2)

        # main area
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        self.header = ctk.CTkLabel(main, text="", font=ctk.CTkFont(size=22, weight="bold"))
        self.header.grid(row=0, column=0, sticky="w", pady=(0, 8))

        toolbar = ctk.CTkFrame(main, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        self.btn_aggiungi = ctk.CTkButton(toolbar, text="Aggiungi", width=110, command=self._add_product)
        self.btn_modifica = ctk.CTkButton(toolbar, text="Modifica", width=110, command=self._edit_product)
        self.btn_elimina = ctk.CTkButton(toolbar, text="Elimina", width=110, command=self._delete_product)
        self.btn_import = ctk.CTkButton(toolbar, text="Importa Excel", width=120, command=self._import_excel)
        for btn in (self.btn_aggiungi, self.btn_modifica, self.btn_elimina, self.btn_import):
            btn.pack(side="left", padx=3)

        if self.is_responsabile:
            ctk.CTkButton(toolbar, text="Posticipa al mese dopo", width=170, fg_color="#4a6fa5",
                          command=self._posticipa_selezionato).pack(side="left", padx=3)

        if self.is_admin or self.is_responsabile:
            ctk.CTkButton(toolbar, text="Invia alert email", width=130, command=self._send_alerts).pack(side="left", padx=3)

        if self.is_admin:
            ctk.CTkButton(toolbar, text="Gestione utenti", width=130, command=self._manage_users).pack(side="left", padx=3)
            ctk.CTkButton(toolbar, text="Impostazioni", width=110, command=self._open_settings).pack(side="left", padx=3)

        table_frame = ctk.CTkFrame(main)
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        cols = ("filiale", "nome", "previsti", "effettivi", "scadenza", "stato", "verifica")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        headings = {
            "filiale": ("Filiale", 110),
            "nome": ("Prodotto", 340),
            "previsti": ("Previsti", 70),
            "effettivi": ("Effettivi", 70),
            "scadenza": ("Scadenza", 100),
            "stato": ("Stato", 110),
            "verifica": ("Verifica", 100),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w" if key in {"filiale", "nome"} else "center")

        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", lambda _e: self._edit_product())

        self.status = ctk.CTkLabel(main, text="", anchor="w", text_color="#555")
        self.status.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        for tag, color in STATO_COLOR.items():
            self.tree.tag_configure(tag, foreground=color)
        self.tree.tag_configure("posticipato", foreground="#4a6fa5")

    # ----- filiale navigation -----
    def _filiale_map(self) -> dict[str, int]:
        return {f["nome"]: f["id"] for f in self.filiali}

    def _select_filiale(self, filiale_id: int | None) -> None:
        self.selected_filiale_id = filiale_id
        for fid, btn in self.filiale_buttons.items():
            if fid == filiale_id:
                btn.configure(fg_color=("#2a8c55", "#2a8c55"), text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=("gray10", "gray90"))
        if filiale_id is None:
            self.header.configure(text="Tutte le filiali")
        else:
            nome = next(f["nome"] for f in self.filiali if f["id"] == filiale_id)
            self.header.configure(text=f"Cassetta PS — {nome}")

        can_edit = self._can_edit_filiale(filiale_id)
        state = "normal" if can_edit else "disabled"
        for btn in (self.btn_aggiungi, self.btn_modifica, self.btn_elimina, self.btn_import):
            btn.configure(state=state)

        self.refresh()

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        giorni = int(self.settings.get("alert_days") or 15)
        mese_corrente = date.today().strftime("%Y-%m")
        self._rows = db.list_prodotti(self.selected_filiale_id)
        alerts = 0
        for p in self._rows:
            stato = db.stato_prodotto(p, giorni)
            if stato in {"in_scadenza", "scaduto", "esaurito"}:
                alerts += 1
            if p.get("non_scade"):
                scad_txt = "NON SCADE"
            elif p.get("scadenza"):
                scad_txt = date.fromisoformat(p["scadenza"]).strftime("%d/%m/%Y")
            else:
                scad_txt = "—"
            verifica = ""
            if p.get("ultima_verifica"):
                verifica = date.fromisoformat(p["ultima_verifica"]).strftime("%d/%m/%Y")

            tag = stato
            if db.is_posticipato(p["id"], mese_corrente):
                tag = "posticipato"
                stato_label = "Posticipato"
            else:
                stato_label = STATO_LABEL[stato]

            self.tree.insert("", "end", iid=str(p["id"]),
                             values=(p["filiale"], p["nome"], p["pezzi_previsti"],
                                     p["pezzi_effettivi"], scad_txt, stato_label, verifica),
                             tags=(tag,))
        self.status.configure(text=f"{len(self._rows)} prodotti — {alerts} in alert (≤{giorni} giorni)")

    def _selected_product(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        pid = int(sel[0])
        return next((p for p in self._rows if p["id"] == pid), None)

    # ----- product CRUD -----
    def _allowed_filiali(self) -> list[dict]:
        if self.is_responsabile:
            return []
        if self.is_admin:
            return self.filiali
        if self.is_filiale:
            return db.list_filiali_for_user(self.current_user)
        return self.filiali

    def _add_product(self) -> None:
        allowed = self._allowed_filiali()
        dlg = ProductDialog(self, allowed, lock_filiale=self.is_filiale)
        if self.selected_filiale_id is not None and self._can_edit_filiale(self.selected_filiale_id):
            nome = next(f["nome"] for f in self.filiali if f["id"] == self.selected_filiale_id)
            dlg.filiale.set(nome)
        self.wait_window(dlg)
        if not dlg.result:
            return
        fmap = self._filiale_map()
        db.add_prodotto(
            filiale_id=fmap[dlg.result["filiale"]],
            nome=dlg.result["nome"],
            pezzi_previsti=dlg.result["pezzi_previsti"],
            pezzi_effettivi=dlg.result["pezzi_effettivi"],
            scadenza=dlg.result["scadenza"],
            non_scade=dlg.result["non_scade"],
            note=dlg.result["note"],
        )
        self.refresh()

    def _edit_product(self) -> None:
        prodotto = self._selected_product()
        if not prodotto:
            messagebox.showinfo("Modifica", "Seleziona un prodotto.")
            return
        if not self._can_edit_filiale(prodotto["filiale_id"]):
            messagebox.showwarning("Accesso negato", "Non hai i permessi per modificare i prodotti di questa filiale.")
            return
        allowed = self._allowed_filiali()
        dlg = ProductDialog(self, allowed, prodotto, lock_filiale=self.is_filiale)
        self.wait_window(dlg)
        if not dlg.result:
            return
        fmap = self._filiale_map()
        old_eff = int(prodotto.get("pezzi_effettivi") or 0)
        new_eff = int(dlg.result["pezzi_effettivi"] or 0)
        db.update_prodotto(
            prodotto["id"],
            filiale_id=fmap[dlg.result["filiale"]],
            nome=dlg.result["nome"],
            pezzi_previsti=dlg.result["pezzi_previsti"],
            pezzi_effettivi=new_eff,
            scadenza=dlg.result["scadenza"],
            non_scade=dlg.result["non_scade"],
            note=dlg.result["note"],
        )
        if old_eff > 0 and new_eff <= 0:
            from app.email_alerts import notify_prodotto_esaurito

            aggiornato = db.get_prodotto(prodotto["id"])
            if aggiornato:
                mail = notify_prodotto_esaurito(aggiornato)
                if mail.get("sent"):
                    messagebox.showinfo("Riordino", mail["message"])
                else:
                    messagebox.showwarning("Riordino", mail.get("message") or "Mail non inviata")
        self.refresh()

    def _delete_product(self) -> None:
        prodotto = self._selected_product()
        if not prodotto:
            messagebox.showinfo("Elimina", "Seleziona un prodotto.")
            return
        if not self._can_edit_filiale(prodotto["filiale_id"]):
            messagebox.showwarning("Accesso negato", "Non hai i permessi.")
            return
        if not messagebox.askyesno("Conferma", f"Eliminare «{prodotto['nome']}» da {prodotto['filiale']}?"):
            return
        db.delete_prodotto(prodotto["id"])
        self.refresh()

    def _import_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleziona file Excel",
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Tutti i file", "*.*")],
        )
        if not path:
            return
        if self.is_filiale:
            allowed = self._allowed_filiali()
            if self.selected_filiale_id is not None and any(
                int(f["id"]) == int(self.selected_filiale_id) for f in allowed
            ):
                filiale_nome = next(
                    f["nome"] for f in allowed if int(f["id"]) == int(self.selected_filiale_id)
                )
            else:
                filiale_nome = allowed[0]["nome"] if allowed else None
        elif self.selected_filiale_id is not None:
            filiale_nome = next(f["nome"] for f in self.filiali if f["id"] == self.selected_filiale_id)
        else:
            filiale_nome = None
        try:
            result = import_excel(path, filiale_nome=filiale_nome, replace=True)
        except Exception as exc:
            messagebox.showerror("Import fallito", str(exc))
            return
        messagebox.showinfo("Import completato", f"Importati {result['importati']} prodotti in {result['filiale']}.")
        target = next(f for f in self.filiali if f["nome"] == result["filiale"])
        self._select_filiale(target["id"])

    # ----- alert & posticipo -----
    def _show_alerts(self) -> None:
        giorni = int(self.settings.get("alert_days") or 15)
        mese_corrente = date.today().strftime("%Y-%m")
        if self.is_filiale:
            alerts = db.prodotti_in_alert(giorni, self.user_filiale_id)
        else:
            alerts = db.prodotti_in_alert(giorni)

        for item in self.tree.get_children():
            self.tree.delete(item)
        self._rows = alerts
        self.header.configure(text=f"Prodotti in alert (≤{giorni} giorni)")
        self.selected_filiale_id = -1
        for fid, btn in self.filiale_buttons.items():
            btn.configure(fg_color="transparent", text_color=("gray10", "gray90"))
        for p in alerts:
            stato = p["stato"]
            scad_txt = date.fromisoformat(p["scadenza"]).strftime("%d/%m/%Y")
            tag = stato
            stato_label = STATO_LABEL[stato]
            if db.is_posticipato(p["id"], mese_corrente):
                tag = "posticipato"
                stato_label = "Posticipato"
            self.tree.insert("", "end", iid=str(p["id"]),
                             values=(p["filiale"], p["nome"], p["pezzi_previsti"],
                                     p["pezzi_effettivi"], scad_txt, stato_label, ""),
                             tags=(tag,))
        self.status.configure(text=f"{len(alerts)} prodotti da sostituire")

        for btn in (self.btn_aggiungi, self.btn_modifica, self.btn_elimina, self.btn_import):
            btn.configure(state="disabled")

    def _posticipa_selezionato(self) -> None:
        prodotto = self._selected_product()
        if not prodotto:
            messagebox.showinfo("Posticipa", "Seleziona un prodotto dall'elenco alert.")
            return
        oggi = date.today()
        mese_corrente = oggi.strftime("%Y-%m")
        if oggi.month == 12:
            mese_next = f"{oggi.year + 1}-01"
        else:
            mese_next = f"{oggi.year}-{oggi.month + 1:02d}"

        if db.is_posticipato(prodotto["id"], mese_corrente):
            messagebox.showinfo("Posticipa", "Questo prodotto è già stato posticipato per questo mese.")
            return

        if not messagebox.askyesno(
            "Posticipa ordine",
            f"Posticipare «{prodotto['nome']}» ({prodotto['filiale']}) al mese prossimo ({mese_next})?\n\n"
            "Verrà incluso nell'ordine cumulativo del mese successivo.",
        ):
            return
        db.posticipa_alert(
            prodotto_id=prodotto["id"],
            mese_corrente=mese_corrente,
            mese_destinazione=mese_next,
            utente_id=self.current_user["id"],
            note="Posticipato per ordine cumulativo",
        )
        messagebox.showinfo("OK", f"Prodotto posticipato a {mese_next}.")
        self._show_alerts()

    def _show_posticipati(self) -> None:
        oggi = date.today()
        mese_corrente = oggi.strftime("%Y-%m")
        posticipati = db.alert_posticipati_attivi(mese_corrente)

        for item in self.tree.get_children():
            self.tree.delete(item)
        self._rows = []
        self.header.configure(text=f"Prodotti posticipati per {mese_corrente}")
        self.selected_filiale_id = -2
        for fid, btn in self.filiale_buttons.items():
            btn.configure(fg_color="transparent", text_color=("gray10", "gray90"))

        for p in posticipati:
            self.tree.insert("", "end", iid=str(p["id"]),
                             values=(p["filiale_nome"], p["prodotto_nome"], "", "",
                                     p["posticipato_da"], "Posticipato", p["posticipato_a"]),
                             tags=("posticipato",))

        self.status.configure(text=f"{len(posticipati)} prodotti posticipati a questo mese")
        for btn in (self.btn_aggiungi, self.btn_modifica, self.btn_elimina, self.btn_import):
            btn.configure(state="disabled")

    def _send_alerts(self) -> None:
        self.settings = load_settings()
        result = check_and_send_alerts()
        if result["sent"]:
            messagebox.showinfo("Alert email", result["message"])
        else:
            messagebox.showwarning("Alert email", result["message"] or "Nessuna email inviata.")

    # ----- admin -----
    def _manage_users(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Gestione utenti")
        win.geometry("800x500")
        win.transient(self)
        win.grab_set()

        cols = ("username", "nome", "ruolo", "filiale", "email", "attivo")
        tree = ttk.Treeview(win, columns=cols, show="headings", selectmode="browse")
        for c, w in [("username", 120), ("nome", 160), ("ruolo", 140), ("filiale", 110), ("email", 160), ("attivo", 60)]:
            tree.heading(c, text=c.capitalize())
            tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        def _refresh_users() -> None:
            for item in tree.get_children():
                tree.delete(item)
            for u in db.list_utenti():
                tree.insert("", "end", iid=str(u["id"]),
                            values=(u["username"], u.get("nome_completo") or "", u["ruolo"],
                                    u.get("filiale_nome") or "", u.get("email") or "",
                                    "Sì" if u["attivo"] else "No"))

        def _add_user() -> None:
            dlg = UserDialog(win, self.filiali)
            win.wait_window(dlg)
            if not dlg.result:
                return
            r = dlg.result
            if not r["password"]:
                messagebox.showwarning("Attenzione", "La password è obbligatoria per nuovi utenti.", parent=win)
                return
            try:
                db.add_utente(r["username"], r["password"], r["nome_completo"],
                              r["ruolo"], r["filiale_id"], r["email"])
            except Exception as exc:
                messagebox.showerror("Errore", str(exc), parent=win)
                return
            _refresh_users()

        def _edit_user() -> None:
            sel = tree.selection()
            if not sel:
                return
            uid = int(sel[0])
            utenti = db.list_utenti()
            utente = next((u for u in utenti if u["id"] == uid), None)
            if not utente:
                return
            dlg = UserDialog(win, self.filiali, utente)
            win.wait_window(dlg)
            if not dlg.result:
                return
            r = dlg.result
            try:
                db.update_utente(uid, username=r["username"], nome_completo=r["nome_completo"],
                                 ruolo=r["ruolo"], filiale_id=r["filiale_id"], email=r["email"],
                                 password=r["password"])
            except Exception as exc:
                messagebox.showerror("Errore", str(exc), parent=win)
                return
            _refresh_users()

        def _toggle_active() -> None:
            sel = tree.selection()
            if not sel:
                return
            uid = int(sel[0])
            utenti = db.list_utenti()
            utente = next((u for u in utenti if u["id"] == uid), None)
            if not utente:
                return
            db.update_utente(uid, attivo=0 if utente["attivo"] else 1)
            _refresh_users()

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(btns, text="Aggiungi", width=110, command=_add_user).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Modifica", width=110, command=_edit_user).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Attiva/Disattiva", width=130, command=_toggle_active).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Chiudi", width=100, fg_color="#666", command=win.destroy).pack(side="right", padx=4)

        _refresh_users()
        win.after(50, win.lift)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        self.wait_window(dlg)
        self.settings = load_settings()
        self.refresh()

    def _change_password(self) -> None:
        dlg = ChangePasswordDialog(self, self.current_user["id"])
        self.wait_window(dlg)

    def _logout(self) -> None:
        self.destroy()
        run()

    def _startup_alert_hint(self) -> None:
        giorni = int(self.settings.get("alert_days") or 15)
        if self.is_filiale:
            alerts = db.prodotti_in_alert(giorni, self.user_filiale_id)
        else:
            alerts = db.prodotti_in_alert(giorni)
        if not alerts:
            return
        ok, _ = smtp_ready(self.settings)
        if self.is_responsabile:
            extra = "Puoi posticipare i prodotti al mese dopo per un ordine cumulativo."
        elif ok:
            extra = "Puoi inviare l'alert email dal pulsante dedicato."
        else:
            extra = "Configura SMTP e destinatari in Impostazioni per inviare le email."
        messagebox.showwarning(
            "Scadenze in arrivo",
            f"Ci sono {len(alerts)} prodotti scaduti o in scadenza entro {giorni} giorni.\n\n{extra}",
        )


def run() -> None:
    db.init_db()
    login = LoginWindow()
    login.mainloop()
    user = login.user
    if not user:
        return
    app = App(user)
    app.mainloop()
