#!/usr/bin/env python3
"""Avvio locale Scadenze PS senza finestra CMD (usare avvia.pyw / pythonw)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HOST = "127.0.0.1"
PORT = 5000


def _show_error(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror(title, message, parent=root)
        root.destroy()
    except Exception:
        pass


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, port))
            return True
        except OSError:
            return False


def _pids_listening(port: int) -> list[int]:
    """Tutti i PID in LISTENING sulla porta (Windows)."""
    if sys.platform != "win32":
        return []
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            text=True,
            errors="ignore",
            creationflags=flags,
        )
    except Exception:
        return []
    pids: set[int] = set()
    suffix = f":{port}"
    for line in out.splitlines():
        upper = line.upper()
        if "LISTENING" not in upper:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_addr = parts[1]
        if not local_addr.endswith(suffix):
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid > 0 and pid != os.getpid():
            pids.add(pid)
    return sorted(pids)


def _stop_previous_instance(port: int) -> bool:
    """Chiude TUTTE le istanze sulla porta, poi verifica che sia libera."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for _attempt in range(3):
        pids = _pids_listening(port)
        if not pids and _port_free(port):
            return True
        for pid in pids:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F", "/T"],
                    capture_output=True,
                    creationflags=flags,
                    check=False,
                )
            except Exception:
                pass
        time.sleep(0.4)
    return _port_free(port)


def _open_browser() -> None:
    time.sleep(1.0)
    webbrowser.open(f"http://{HOST}:{PORT}/login")


def main() -> None:
    from app.paths import NAS_ROOT, ensure_dirs
    from app.webapp import create_app

    try:
        ensure_dirs()
    except OSError as exc:
        _show_error(
            "Scadenze PS — NAS non raggiungibile",
            "Impossibile accedere al NAS aziendale.\n\n"
            f"Percorso:\n{NAS_ROOT}\n\n"
            "Verifica di essere in rete aziendale e di avere accesso a:\n"
            r"\\172.17.17.11\supporto-tecnico"
            f"\n\nDettaglio: {exc}",
        )
        sys.exit(1)

    # Sempre termina le istanze precedenti (anche se la bind sembra libera:
    # su Windows possono restare più LISTENING sulla stessa porta).
    if not _stop_previous_instance(PORT):
        _show_error(
            "Scadenze PS — Porta occupata",
            f"La porta {PORT} è ancora occupata da un'altra applicazione.\n"
            "Chiudi le finestre di Scadenze PS dal Task Manager e riprova.",
        )
        webbrowser.open(f"http://{HOST}:{PORT}/login")
        return

    try:
        app = create_app()
    except Exception as exc:
        _show_error("Scadenze PS — Errore avvio", str(exc))
        sys.exit(1)

    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
