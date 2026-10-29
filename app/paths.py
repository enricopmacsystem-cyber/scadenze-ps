from __future__ import annotations

import os
from pathlib import Path


def app_root() -> Path:
    """Cartella dell'applicazione (locale o NAS)."""
    return Path(__file__).resolve().parent.parent


def _data_root() -> Path:
    """
    Dati condivisi.
    Se l'app è già sul NAS, dati = stessa cartella.
    Altrimenti (sviluppo) punta al NAS aziendale.
    """
    env = os.environ.get("SCADENZE_PS_DATA")
    if env:
        return Path(env)

    root = app_root()
    # Se siamo già su \\172.17.17.11\supporto-tecnico\Scadenze-PS → usa root
    parts = [p.lower() for p in root.parts]
    if "supporto-tecnico" in parts and root.name.lower() == "scadenze-ps":
        return root

    return Path(r"\\172.17.17.11\supporto-tecnico\Scadenze-PS")


ROOT = app_root()
NAS_ROOT = _data_root()
DATA_DIR = NAS_ROOT / "data"
CONFIG_DIR = NAS_ROOT / "config"
UPLOADS_DIR = NAS_ROOT / "uploads"
DB_PATH = DATA_DIR / "scadenze.db"
SETTINGS_PATH = CONFIG_DIR / "settings.json"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
