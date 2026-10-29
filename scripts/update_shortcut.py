"""Aggiorna i collegamenti Scadenze PS per avvio senza CMD."""
from __future__ import annotations

import sys
from pathlib import Path

import win32com.client

root = Path(__file__).resolve().parent.parent
py = Path(sys.executable)
pythonw = py.with_name("pythonw.exe")
if not pythonw.exists():
    pythonw = py

avvia = root / "avvia.pyw"
icon = root / "assets" / "scadenze-ps.ico"
ws = win32com.client.Dispatch("WScript.Shell")

for dest in [root / "Scadenze PS.lnk", Path.home() / "Desktop" / "Scadenze PS.lnk"]:
    s = ws.CreateShortcut(str(dest))
    s.TargetPath = str(pythonw)
    s.Arguments = f'"{avvia}"'
    s.WorkingDirectory = str(root)
    s.IconLocation = str(icon)
    s.Description = "Scadenze cassette pronto soccorso"
    s.Save()
    print("updated", dest)
