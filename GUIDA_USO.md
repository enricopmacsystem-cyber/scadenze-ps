# Guide Scadenze PS

Applicazione per le scadenze delle cassette di pronto soccorso.

**Filiali:** Tavagnacco, Verona, Padova, Marghera, Villorba, Mirandola, Gruaro Showroom, Gruaro Magazzino.

Le istruzioni operative sono in **tre PDF** (cartella NAS + Desktop dopo generazione):

| File | Destinatari |
|---|---|
| **GUIDA_FILIALE.pdf** | Responsabili di filiale |
| **GUIDA_ORDINI.pdf** | Chi coordina / ordina il materiale |
| **GUIDA_ADMIN.pdf** | Amministratore |
| GUIDA_USO.pdf | Indice breve (questa panoramica) |

Generazione: `python scripts/build_guida_pdf.py`

## Messaggio chiave per le filiali

Se un prodotto viene **consumato**, aggiornare subito i **pezzi effettivi a 0**.  
Lo stato diventa **Esaurito** e, a go-live attivo, parte subito la **mail di riordino**.  
Senza aggiornamento in app, nessuno riceve l’avviso.

## Stati in app

| Stato | Quando |
|---|---|
| OK | Disponibile, non in scadenza |
| In scadenza | Entro 15 giorni |
| Scaduto | Data passata |
| **Esaurito** | Pezzi effettivi = 0 |

Ogni filiale ha anche la **cassetta portatile** (voce *Cassetta portatile* nel menu), con gli stessi stati.

## Email (go-live)

- **Scadenze:** Silvia = quadro completo; filiale = solo i propri prodotti (prima volta entro 15 gg)
- **Esaurito:** mail di riordino immediata a Silvia + filiale quando si salva pezzi = 0
- **Stato attuale:** invio SMTP **disattivato** fino all’ok al go-live

## Accesso rapido

1. Icona Desktop **Scadenze PS** → `http://localhost:5000`
2. Prima volta: `\\172.17.17.11\scadenza ps` → `Crea collegamento Desktop.bat`
3. Credenziali e dettagli: vedere **GUIDA_ADMIN.pdf** / guida del proprio ruolo
