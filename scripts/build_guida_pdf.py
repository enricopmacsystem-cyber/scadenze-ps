#!/usr/bin/env python3
"""Genera le guide PDF Scadenze PS (Admin, Ordini, Filiale) + indice generale."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
NAS_DIR = Path(r"\\172.17.17.11\supporto-tecnico\Scadenze-PS")
DESKTOP = Path.home() / "Desktop"

GREEN = colors.HexColor("#1f6f5b")
INK = colors.HexColor("#14221f")
MUTED = colors.HexColor("#5a6b66")
LINE = colors.HexColor("#c9d6cf")
BG = colors.HexColor("#f3f7f4")
WARN_BG = colors.HexColor("#fff3d6")
WARN_INK = colors.HexColor("#7a4e00")


def build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleIT",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=GREEN,
            spaceAfter=6,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "SubIT",
            parent=base["Normal"],
            fontSize=11,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=14,
            leading=15,
        ),
        "h1": ParagraphStyle(
            "H1IT",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=GREEN,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2IT",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=INK,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "BodyIT",
            parent=base["Normal"],
            fontSize=10,
            textColor=INK,
            leading=14,
            spaceAfter=6,
        ),
        "note": ParagraphStyle(
            "NoteIT",
            parent=base["Normal"],
            fontSize=9,
            textColor=MUTED,
            leading=13,
            leftIndent=6,
            rightIndent=6,
            spaceBefore=4,
            spaceAfter=8,
            backColor=BG,
            borderPadding=6,
        ),
        "important": ParagraphStyle(
            "ImportantIT",
            parent=base["Normal"],
            fontSize=10,
            textColor=WARN_INK,
            leading=14,
            leftIndent=6,
            rightIndent=6,
            spaceBefore=6,
            spaceAfter=10,
            backColor=WARN_BG,
            borderPadding=8,
            fontName="Helvetica-Bold",
        ),
        "code": ParagraphStyle(
            "CodeIT",
            fontName="Courier",
            fontSize=8.5,
            textColor=INK,
            leading=12,
            backColor=BG,
            leftIndent=4,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "cell": ParagraphStyle(
            "CellIT",
            parent=base["Normal"],
            fontSize=9,
            textColor=INK,
            leading=12,
        ),
        "cell_bold": ParagraphStyle(
            "CellBoldIT",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=INK,
            leading=12,
        ),
    }


def table(data: list[list[str]], styles, col_widths=None) -> Table:
    header_style = ParagraphStyle(
        "Hdr",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.white,
        leading=12,
    )
    rows = []
    for i, row in enumerate(data):
        style = header_style if i == 0 else styles["cell"]
        rows.append([Paragraph(str(c).replace("\n", "<br/>"), style) for c in row])
    t = Table(rows, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
            ]
        )
    )
    return t


def bullets(items: list[str], styles) -> ListFlowable:
    return ListFlowable(
        [
            ListItem(Paragraph(i, styles["body"]), leftIndent=12, bulletColor=GREEN)
            for i in items
        ],
        bulletType="bullet",
        start="•",
        leftIndent=15,
        bulletFontSize=10,
    )


def numbered(items: list[str], styles) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(i, styles["body"]), leftIndent=12) for i in items],
        bulletType="1",
        leftIndent=15,
    )


def _doc(path: Path, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title=title,
        author="Scadenze PS",
    )


def _header(story, styles, title: str, subtitle: str) -> None:
    story.append(Paragraph(title, styles["title"]))
    story.append(Paragraph(subtitle, styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GREEN, spaceAfter=12))


def _avvio_comune(story, styles) -> None:
    story.append(Paragraph("Avvio", styles["h1"]))
    story.append(
        numbered(
            [
                "Doppio clic sull'icona <b>Scadenze PS</b> sul Desktop",
                "Si apre il browser su <font face='Courier'>http://localhost:5000</font>",
                "Accedi con username e password (al primo accesso cambia la password)",
            ],
            styles,
        )
    )
    story.append(
        Paragraph(
            "Prima volta su un PC nuovo: aprire "
            r"<font face='Courier'>\\172.17.17.11\supporto-tecnico\Scadenze-PS</font> "
            "e lanciare <b>Crea collegamento Desktop.bat</b>.",
            styles["note"],
        )
    )


def build_filiale(path: Path) -> Path:
    styles = build_styles()
    doc = _doc(path, "Guida Filiale — Scadenze PS")
    story: list = []
    w = doc.width

    _header(
        story,
        styles,
        "Guida responsabili di filiale",
        "Scadenze PS — cassette di pronto soccorso<br/>"
        "Cosa fare ogni giorno nella propria sede",
    )

    story.append(
        Paragraph(
            "IMPORTANTE — Prodotto esaurito: aggiornare subito i pezzi a 0. "
            "Solo così lo stato diventa «Esaurito» e, a sistema attivo, parte subito "
            "la mail di riordino a Silvia e ai responsabili. Se non aggiornate in app, "
            "nessuno viene avvisato e la cassetta resta scoperta.",
            styles["important"],
        )
    )

    _avvio_comune(story, styles)

    story.append(Paragraph("Il tuo account", styles["h1"]))
    story.append(
        Paragraph(
            "Usi l'utente della tua filiale (es. <font face='Courier'>marghera</font>, "
            "<font face='Courier'>villorba</font>, <font face='Courier'>gruaro</font>). "
            "A <b>Gruaro</b> un solo utente gestisce <b>Showroom</b> e <b>Magazzino</b> "
            "(schede Entrambe / Showroom / Magazzino).",
            styles["body"],
        )
    )

    story.append(Paragraph("Cosa puoi fare", styles["h1"]))
    story.append(
        bullets(
            [
                "Vedere e modificare solo i prodotti della propria cassetta",
                "Importare Excel (anche con colonne/nomi diversi)",
                "Aggiungere, modificare o eliminare prodotti",
                "Aggiornare pezzi effettivi e date di scadenza dopo sostituzione o consumo",
            ],
            styles,
        )
    )

    story.append(Paragraph("Stati prodotto (da conoscere)", styles["h1"]))
    story.append(
        table(
            [
                ["Stato", "Significato", "Cosa fare"],
                ["OK", "Disponibile e non in scadenza", "Nessuna azione"],
                [
                    "In scadenza",
                    "Scade entro 15 giorni",
                    "Segnalare / preparare sostituzione",
                ],
                ["Scaduto", "Data già passata", "Sostituire subito"],
                [
                    "Esaurito",
                    "Pezzi effettivi = 0",
                    "Aggiornare subito in app → riordino",
                ],
            ],
            styles,
            col_widths=[w * 0.22, w * 0.38, w * 0.40],
        )
    )

    story.append(Paragraph("Procedura: prodotto consumato / esaurito", styles["h1"]))
    story.append(
        numbered(
            [
                "Apri <b>Modifica</b> sul prodotto",
                "Imposta <b>Pezzi effettivi</b> a <b>0</b> e salva",
                "In elenco lo stato diventa <b>Esaurito</b> (non più OK verde)",
                "A go-live attivo, il sistema invia subito la richiesta di riordino "
                "(Silvia + email della filiale)",
                "Quando arriva il ricambio: aggiorna pezzi e nuova scadenza",
            ],
            styles,
        )
    )
    story.append(
        Paragraph(
            "Non aspettare la fine della giornata o l'import Excel successivo: "
            "l'aggiornamento tempestivo è obbligatorio per la sicurezza della cassetta.",
            styles["important"],
        )
    )

    story.append(Paragraph("Flusso consigliato", styles["h1"]))
    story.append(
        numbered(
            [
                "Controllare periodicamente pezzi e scadenze in app",
                "Dopo ogni consumo / sostituzione, aggiornare subito i dati",
                "Importare Excel quando si ha un file aggiornato della cassetta",
                "Segnalare eventuali anomalie all'admin o a chi gestisce gli ordini",
            ],
            styles,
        )
    )

    story.append(Paragraph("Problemi frequenti", styles["h1"]))
    story.append(
        bullets(
            [
                "<b>Errore NAS</b>: rete aziendale e percorso "
                r"<font face='Courier'>\\172.17.17.11\supporto-tecnico</font>",
                "<b>Password dimenticata</b>: chiedere reset all'amministratore",
                "<b>Porta già in uso</b>: l'app riapre sul browser; una sola istanza",
            ],
            styles,
        )
    )

    doc.build(story)
    return path


def build_ordini(path: Path) -> Path:
    styles = build_styles()
    doc = _doc(path, "Guida Ordini materiale — Scadenze PS")
    story: list = []
    w = doc.width

    _header(
        story,
        styles,
        "Guida ordini materiale",
        "Scadenze PS — per chi riceve gli alert e coordina i riordini<br/>"
        "(account <font face='Courier'>ordini.gruaro</font> e destinatari come Silvia)",
    )

    story.append(
        Paragraph(
            "Ricevi gli avvisi di prodotti in scadenza / scaduti e le richieste di "
            "riordino per prodotti esauriti. Le filiali devono aggiornare i pezzi a 0 "
            "in tempo reale: senza quel passaggio non parte la mail di riordino.",
            styles["note"],
        )
    )

    _avvio_comune(story, styles)

    story.append(Paragraph("Account e permessi", styles["h1"]))
    story.append(
        bullets(
            [
                "Login tipico: <font face='Courier'>ordini.gruaro</font> "
                "(password iniziale in guida admin / primo accesso)",
                "<b>Sola lettura</b> sui prodotti: non puoi importare, creare o modificare",
                "Vedi <b>tutte</b> le filiali e la vista <b>In alert</b>",
                "Puoi <b>posticipare</b> un prodotto all'ordine del mese successivo",
                "Puoi usare <b>Invia alert email</b> (quando l'invio è attivo)",
                "Opzionale: <b>La mia email</b> per ricevere gli alert anche in posta",
            ],
            styles,
        )
    )

    story.append(Paragraph("Cosa finisce in alert", styles["h1"]))
    story.append(
        table(
            [
                ["Caso", "Stato in app", "Azione tipica"],
                [
                    "Scade entro 15 giorni",
                    "In scadenza",
                    "Ordinare o posticipare",
                ],
                ["Già scaduto", "Scaduto", "Sostituire / ordinare subito"],
                [
                    "Pezzi effettivi = 0",
                    "Esaurito",
                    "Riordino immediato (mail dedicata)",
                ],
            ],
            styles,
            col_widths=[w * 0.32, w * 0.28, w * 0.40],
        )
    )

    story.append(Paragraph("Email (quando il go-live è attivo)", styles["h1"]))
    story.append(
        bullets(
            [
                "<b>Silvia</b> (destinatario globale): quadro completo di tutte le filiali",
                "<b>Responsabili filiale</b>: solo i prodotti della propria sede",
                "<b>Esaurito</b>: mail di riordino immediata a Silvia + filiale, "
                "nel momento in cui la filiale salva pezzi = 0",
                "<b>Scadenze</b>: notifica la prima volta che un prodotto entra "
                "nella finestra dei 15 giorni (non ogni giorno)",
            ],
            styles,
        )
    )
    story.append(
        Paragraph(
            "Oggi l'invio SMTP è <b>disattivato</b> fino al go-live definitivo. "
            "In app gli alert restano comunque visibili.",
            styles["important"],
        )
    )

    story.append(Paragraph("Flusso consigliato", styles["h1"]))
    story.append(
        numbered(
            [
                "Aprire la vista <b>In alert</b> (o controllare le mail a go-live attivo)",
                "Decidere cosa ordinare subito e cosa <b>Posticipa mese</b>",
                "Coordinare con le filiali la sostituzione in cassetta",
                "Verificare che dopo il ricambio la filiale aggiorni pezzi e scadenza",
            ],
            styles,
        )
    )

    story.append(Paragraph("Posticipo", styles["h1"]))
    story.append(
        Paragraph(
            "Su un prodotto in scadenza/scaduto puoi usare <b>Posticipa mese</b>: "
            "resta in elenco per l'ordine cumulativo del mese successivo. "
            "I prodotti <b>esauriti</b> richiedono invece riordino immediato "
            "(non ha senso posticiparli se la cassetta è scoperta).",
            styles["body"],
        )
    )

    doc.build(story)
    return path


def build_admin(path: Path) -> Path:
    styles = build_styles()
    doc = _doc(path, "Guida Admin — Scadenze PS")
    story: list = []
    w = doc.width

    _header(
        story,
        styles,
        "Guida amministratore",
        "Scadenze PS — installazione, utenti, SMTP, go-live email",
    )

    _avvio_comune(story, styles)

    story.append(Paragraph("Architettura", styles["h1"]))
    story.append(
        table(
            [
                ["Cosa", "Dove"],
                ["Applicazione + database", "Solo sul NAS aziendale"],
                ["PC utente", "Solo collegamento Desktop + Python"],
            ],
            styles,
            col_widths=[w * 0.4, w * 0.6],
        )
    )
    story.append(
        Preformatted(
            "\\\\172.17.17.11\\supporto-tecnico\\Scadenze-PS\\\n"
            "  data\\scadenze.db\n"
            "  config\\settings.json\n"
            "  uploads\\\n"
            "  GUIDA_*.pdf",
            styles["code"],
        )
    )

    story.append(Paragraph("Credenziali di primo accesso", styles["h1"]))
    story.append(
        Paragraph(
            "<b>Cambiare la password al primo login</b> (obbligatorio).",
            styles["body"],
        )
    )
    story.append(
        table(
            [
                ["Username", "Password iniziale", "Ruolo"],
                ["admin", "Admin2026!!", "Amministratore"],
                ["tavagnacco", "Tavagnacco2026!", "Filiale"],
                ["verona", "Verona2026!", "Filiale"],
                ["padova", "Padova2026!", "Filiale"],
                ["marghera", "Marghera2026!", "Filiale"],
                ["gruaro", "Gruaro2026!", "Gruaro Showroom + Magazzino"],
                ["villorba", "Villorba2026!", "Filiale"],
                ["mirandola", "Mirandola2026!", "Filiale"],
                ["ordini.gruaro", "OrdiniGruaro2026!", "Responsabile ordini"],
            ],
            styles,
            col_widths=[w * 0.28, w * 0.32, w * 0.40],
        )
    )

    story.append(Paragraph("Cosa fa l'admin", styles["h1"]))
    story.append(
        bullets(
            [
                "Gestione utenti e reset password (Utenti)",
                "Accesso completo a tutte le filiali",
                "Impostazioni SMTP, destinatari globali (Silvia), email per filiale",
                "Giorni di preavviso scadenza (oggi: <b>15</b>)",
                "Pulsante Invia alert (quando invio attivo)",
            ],
            styles,
        )
    )

    story.append(Paragraph("Email e go-live", styles["h1"]))
    story.append(
        bullets(
            [
                "<b>Scadenze</b>: mail quando un prodotto entra nei 15 giorni "
                "(Silvia = quadro completo; filiale = solo i propri)",
                "<b>Esaurito</b>: mail di riordino immediata quando la filiale "
                "salva pezzi effettivi = 0",
                "Destinatario globale attuale: "
                "<font face='Courier'>silvia.drigo@macsystem.it</font>",
                "Email filiali configurate in Impostazioni "
                "(Marghera, Gruaro×2, Verona, Villorba, Padova, Tavagnacco; "
                "Mirandola/Modena in standby)",
            ],
            styles,
        )
    )
    story.append(
        Paragraph(
            "STATO ATTUALE: invio SMTP bloccato (go-live non attivo). "
            "Gli stati in app (In scadenza / Scaduto / Esaurito) funzionano; "
            "nessuna mail parte finché non si riattiva il sistema definitivo.",
            styles["important"],
        )
    )

    story.append(Paragraph("Guide per ruolo", styles["h1"]))
    story.append(
        bullets(
            [
                "<b>GUIDA_FILIALE.pdf</b> — responsabili cassetta "
                "(obbligo aggiornamento pezzi a 0)",
                "<b>GUIDA_ORDINI.pdf</b> — chi coordina ordini / riceve alert",
                "<b>GUIDA_ADMIN.pdf</b> — questa guida",
            ],
            styles,
        )
    )

    story.append(Paragraph("Problemi frequenti", styles["h1"]))
    story.append(
        bullets(
            [
                "<b>Database locked</b>: altro utente in scrittura; riprovare",
                "<b>Email non parte</b>: verificare blocco go-live, SMTP e destinatari",
                "<b>Più istanze su :5000</b>: chiudere i processi pythonw e rilanciare",
            ],
            styles,
        )
    )

    doc.build(story)
    return path


def build_indice(path: Path) -> Path:
    styles = build_styles()
    doc = _doc(path, "Guida d'uso — Scadenze PS")
    story: list = []

    _header(
        story,
        styles,
        "Guida d'uso — Scadenze PS",
        "Indice delle guide per ruolo<br/>"
        "Tavagnacco · Verona · Padova · Marghera · Gruaro · Villorba · Mirandola",
    )

    story.append(
        Paragraph(
            "Le istruzioni operative sono suddivise in tre PDF. "
            "Distribuisci a ciascuno la guida del proprio ruolo.",
            styles["body"],
        )
    )
    story.append(
        table(
            [
                ["File", "Destinatari", "Contenuto chiave"],
                [
                    "GUIDA_FILIALE.pdf",
                    "Responsabili di filiale",
                    "Aggiornare pezzi/scadenze; ESAURITO → pezzi a 0 subito",
                ],
                [
                    "GUIDA_ORDINI.pdf",
                    "Chi ordina il materiale",
                    "Vista alert, posticipo, lettura mail riordino",
                ],
                [
                    "GUIDA_ADMIN.pdf",
                    "Amministratore",
                    "Utenti, SMTP, 15 gg, go-live email",
                ],
            ],
            styles,
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "Stati in app: OK · In scadenza (≤15 gg) · Scaduto · "
            "<b>Esaurito</b> (pezzi = 0). "
            "Invio email attualmente disattivato fino al go-live.",
            styles["important"],
        )
    )
    story.append(
        Paragraph(
            "Cartella NAS: "
            r"<font face='Courier'>\\172.17.17.11\supporto-tecnico\Scadenze-PS</font>",
            styles["note"],
        )
    )

    doc.build(story)
    return path


def _copy_out(src: Path, *dests: Path) -> None:
    data = src.read_bytes()
    for d in dests:
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_bytes(data)
            print(f"  -> {d}")
        except OSError as exc:
            print(f"  ! {d}: {exc}")


def main() -> None:
    out_dir = ROOT
    files = {
        "indice": out_dir / "GUIDA_USO.pdf",
        "filiale": out_dir / "GUIDA_FILIALE.pdf",
        "ordini": out_dir / "GUIDA_ORDINI.pdf",
        "admin": out_dir / "GUIDA_ADMIN.pdf",
    }
    print("Generazione PDF…")
    build_indice(files["indice"])
    build_filiale(files["filiale"])
    build_ordini(files["ordini"])
    build_admin(files["admin"])
    for key, path in files.items():
        print(f"Creato: {path.name}")
        _copy_out(
            path,
            DESKTOP / path.name,
            NAS_DIR / path.name,
        )
        if key == "indice":
            _copy_out(path, DESKTOP / "GUIDA_USO_Scadenze_PS.pdf")


if __name__ == "__main__":
    main()
