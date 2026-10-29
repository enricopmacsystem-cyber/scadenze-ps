"""Crea sul Desktop il collegamento Scadenze PS (croce verde)."""
from __future__ import annotations

import ctypes
import os
import shutil
import sys
from pathlib import Path


def _msg(title: str, text: str, error: bool = False) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if error:
            messagebox.showerror(title, text, parent=root)
        else:
            messagebox.showinfo(title, text, parent=root)
        root.destroy()
    except Exception:
        print(title)
        print(text)


def _log(msg: str) -> None:
    try:
        log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Scadenze-PS"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "shortcut.log").open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def _known_desktop() -> Path | None:
    """Desktop reale di Windows (FOLDERID_Desktop)."""
    try:
        import uuid

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        def to_guid(s: str) -> GUID:
            u = uuid.UUID(s)
            g = GUID()
            g.Data1 = u.time_low
            g.Data2 = u.time_mid
            g.Data3 = u.time_hi_version
            for i, b in enumerate(u.bytes[8:]):
                g.Data4[i] = b
            return g

        fid = to_guid("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")
        SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
        SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(GUID),
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        path_ptr = ctypes.c_wchar_p()
        hr = SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(path_ptr))
        if hr == 0 and path_ptr.value:
            p = Path(path_ptr.value)
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            if p.is_dir():
                return p
    except Exception as exc:
        _log(f"known_desktop fail: {exc}")
    return None


def _desktop_dirs() -> list[Path]:
    found: list[Path] = []

    def add(p: Path | None) -> None:
        if p is None:
            return
        try:
            p = p.resolve()
        except OSError:
            pass
        if p.is_dir() and p not in found:
            found.append(p)

    add(_known_desktop())

    try:
        import win32com.client

        add(Path(win32com.client.Dispatch("WScript.Shell").SpecialFolders("Desktop")))
    except Exception as exc:
        _log(f"SpecialFolders Desktop: {exc}")

    add(Path.home() / "Desktop")
    add(Path.home() / "OneDrive" / "Desktop")
    for p in Path.home().glob("OneDrive*/Desktop"):
        add(p)

    # Desktop pubblico (visibile a tutti gli utenti del PC)
    public = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"
    add(public)

    _log("Desktop candidati: " + " | ".join(str(x) for x in found))
    return found


def _local_icon(source_ico: Path) -> Path:
    dest_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Scadenze-PS"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "scadenze-ps.ico"
    shutil.copy2(source_ico, dest)
    return dest


def _create_shortcut(lnk: Path, pythonw: Path, avvia: Path, root: Path, icon: Path) -> None:
    import win32com.client

    lnk.parent.mkdir(parents=True, exist_ok=True)
    if lnk.exists():
        try:
            lnk.unlink()
        except OSError:
            pass

    ws = win32com.client.Dispatch("WScript.Shell")
    s = ws.CreateShortcut(str(lnk))
    s.TargetPath = str(pythonw)
    s.Arguments = f'"{avvia}"'
    s.WorkingDirectory = str(root)
    s.IconLocation = f"{icon},0"
    s.Description = "Scadenze cassette pronto soccorso"
    s.Save()
    if not lnk.exists():
        raise OSError(f"Save non ha creato il file: {lnk}")


def _resolve_root() -> Path:
    env_root = os.environ.get("SCADENZE_PS_APP_ROOT", "").strip()
    if env_root and Path(env_root).is_dir():
        return Path(env_root)

    root = Path(__file__).resolve().parent
    if root.name.lower() == "scadenze-ps" and "appdata" in str(root).lower():
        nas = Path(r"\\172.17.17.11\supporto-tecnico\Scadenze-PS")
        if nas.is_dir():
            return nas
    return root


def main() -> int:
    _log("--- avvio creazione collegamento ---")
    root = _resolve_root()
    avvia = root / "avvia.pyw"
    source_icon = root / "assets" / "scadenze-ps.ico"
    _log(f"root={root}")

    if not avvia.exists():
        _msg("Scadenze PS", f"File non trovato:\n{avvia}", error=True)
        return 1
    if not source_icon.exists():
        _msg("Scadenze PS", f"Icona non trovata:\n{source_icon}", error=True)
        return 1

    py = Path(sys.executable)
    pythonw = py.with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = py

    try:
        import win32com.client  # noqa: F401
    except ImportError:
        _msg(
            "Scadenze PS",
            "Manca pywin32.\nEsegui: python -m pip install pywin32",
            error=True,
        )
        return 1

    try:
        icon = _local_icon(source_icon)
    except OSError as exc:
        _msg("Scadenze PS", f"Impossibile copiare l'icona:\n{exc}", error=True)
        return 1

    created: list[str] = []
    errors: list[str] = []

    # Sempre anche in AppData locale (fallback sicuro)
    appdata_lnk = Path(os.environ["LOCALAPPDATA"]) / "Scadenze-PS" / "Scadenze PS.lnk"
    targets = [appdata_lnk]
    targets.extend(d / "Scadenze PS.lnk" for d in _desktop_dirs())

    for lnk in targets:
        try:
            _create_shortcut(lnk, pythonw, avvia, root, icon)
            created.append(str(lnk))
            _log(f"OK {lnk}")
        except Exception as exc:
            errors.append(f"{lnk}: {exc}")
            _log(f"FAIL {lnk}: {exc}")

    desktop_created = [c for c in created if "desktop" in c.lower() or "OneDrive" in c]
    if desktop_created:
        _msg(
            "Scadenze PS",
            "Collegamento creato.\n\n"
            "Lo trovi qui:\n"
            + "\n".join(desktop_created)
            + "\n\nSe non lo vedi: tasto destro sul Desktop → Aggiorna.\n"
            "Oppure apri Esplora file e vai in quella cartella.",
        )
        return 0

    if created:
        # Solo AppData: apri la cartella e avvisa
        fallback = created[0]
        try:
            os.startfile(str(Path(fallback).parent))
        except OSError:
            pass
        _msg(
            "Scadenze PS",
            "Non sono riuscito a scrivere sul Desktop.\n\n"
            f"Collegamento creato qui:\n{fallback}\n\n"
            "Copia quel file sul Desktop (tasto destro → Copia, poi Incolla sul Desktop).",
        )
        return 0

    _msg(
        "Scadenze PS",
        "Impossibile creare il collegamento.\n\n" + "\n".join(errors),
        error=True,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
