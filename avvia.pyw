"""Avvio senza finestra CMD — funziona anche dalla cartella NAS."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    os.chdir(ROOT)
except OSError:
    pass

from main import main

main()
