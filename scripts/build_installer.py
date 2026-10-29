#!/usr/bin/env python3
"""Compila l'eseguibile con PyInstaller e crea l'installer .exe con Inno Setup."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SPEC = ROOT / "ScadenzePS.spec"
ISS = ROOT / "installer" / "ScadenzePS.iss"

ISCC_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
]


def find_iscc() -> Path | None:
    for p in ISCC_PATHS:
        if p.exists():
            return p
    return None


def main() -> None:
    print("==> PyInstaller")
    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)],
        cwd=ROOT,
    )

    built = DIST / "ScadenzePS"
    if not (built / "ScadenzePS.exe").exists():
        raise SystemExit("Build fallita: exe non trovato")

    iscc = find_iscc()
    if iscc:
        print()
        print("==> Inno Setup")
        subprocess.check_call([str(iscc), str(ISS)], cwd=ROOT)
        setup = DIST / "Scadenze-PS-Setup.exe"
        if setup.exists():
            size_mb = setup.stat().st_size / (1024 * 1024)
            print()
            print("Installer pronto:")
            print(f"  {setup}")
            print(f"  ({size_mb:.1f} MB)")
            print()
            print("Invia questo .exe al collega. Installa e disinstalla da Windows normalmente.")
            return

    print()
    print("Inno Setup non trovato, creo ZIP di fallback...")
    out_dir = DIST / "Scadenze-PS-Installer"
    app_dir = out_dir / "app"
    zip_path = DIST / "Scadenze-PS-Installer.zip"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    shutil.copytree(built, app_dir)
    installer_src = ROOT / "installer"
    shutil.copy2(installer_src / "Installa.bat", out_dir / "Installa.bat")
    shutil.copy2(installer_src / "LEGGIMI.txt", out_dir / "LEGGIMI.txt")
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", out_dir)
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  {zip_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
