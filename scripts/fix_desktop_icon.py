import os
import shutil
from pathlib import Path

import win32com.client

root = Path(__file__).resolve().parent.parent
src = root / "assets" / "scadenze-ps.ico"
dest_dir = Path(os.environ["LOCALAPPDATA"]) / "Scadenze-PS"
dest_dir.mkdir(exist_ok=True)
dest = dest_dir / "scadenze-ps.ico"
shutil.copy2(src, dest)
print("local ico", dest, dest.stat().st_size)

pyw = Path(r"C:\Users\enrico.patres\AppData\Local\Programs\Python\Python312\pythonw.exe")
if not pyw.exists():
    pyw = Path(__import__("sys").executable).with_name("pythonw.exe")
avvia = root / "avvia.pyw"
ws = win32com.client.Dispatch("WScript.Shell")
for name in [Path.home() / "Desktop" / "Scadenze PS.lnk", root / "Scadenze PS.lnk"]:
    if name.exists():
        try:
            name.unlink()
        except OSError:
            pass
    s = ws.CreateShortcut(str(name))
    s.TargetPath = str(pyw)
    s.Arguments = f'"{avvia}"'
    s.WorkingDirectory = str(root)
    s.IconLocation = f"{dest},0"
    s.Description = "Scadenze cassette pronto soccorso"
    s.Save()
    print("lnk", name)
    print("  icon", s.IconLocation)
