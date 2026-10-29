@echo off
chcp 65001 >nul
title Scadenze PS — Installazione e collegamento Desktop
cd /d "%~dp0"

echo.
echo  ========================================
echo   Scadenze PS — preparazione di questo PC
echo  ========================================
echo.
echo  Verifica Python e librerie necessarie.
echo  Se mancano, verranno installate (serve Internet).
echo.

REM Preferisci PowerShell 64-bit
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell.exe"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_pc.ps1"
set "ERR=%ERRORLEVEL%"

echo.
if "%ERR%"=="0" (
  echo  Operazione completata.
) else (
  echo  Operazione NON completata. Codice: %ERR%
  echo.
  echo  Apri e invia questo file di log:
  echo    %LOCALAPPDATA%\Scadenze-PS\setup.log
  echo.
  echo  Oppure installa Python 3.12 da https://www.python.org/downloads/
  echo  ^(spunta "Add python.exe to PATH"^) e rilancia questo file.
)
echo.
pause
exit /b %ERR%
