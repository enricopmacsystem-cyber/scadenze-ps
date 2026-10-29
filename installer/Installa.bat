@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Installa Scadenze PS

set "APP_NAME=Scadenze PS"
set "SRC=%~dp0app"
set "DEST=%LOCALAPPDATA%\Scadenze-PS"

echo.
echo  ========================================
echo   Installazione %APP_NAME%
echo  ========================================
echo.
echo  Destinazione: %DEST%
echo.

if not exist "%SRC%\ScadenzePS.exe" (
  echo [ERRORE] File applicazione non trovati in:
  echo   %SRC%
  echo.
  pause
  exit /b 1
)

if not exist "%DEST%" mkdir "%DEST%"

echo Copia file in corso...
robocopy "%SRC%" "%DEST%" /E /IS /IT /NFL /NDL /NJH /NJS /nc /ns /np >nul
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
  echo [ERRORE] Copia non riuscita ^(codice %RC%^).
  pause
  exit /b 1
)

REM Collegamento Desktop
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Scadenze PS.lnk'); $s.TargetPath = $env:LOCALAPPDATA + '\Scadenze-PS\ScadenzePS.exe'; $s.WorkingDirectory = $env:LOCALAPPDATA + '\Scadenze-PS'; $s.Description = 'Scadenze cassette pronto soccorso'; $s.Save()"

REM Collegamento Menu Start
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$dir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'; $ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut((Join-Path $dir 'Scadenze PS.lnk')); $s.TargetPath = $env:LOCALAPPDATA + '\Scadenze-PS\ScadenzePS.exe'; $s.WorkingDirectory = $env:LOCALAPPDATA + '\Scadenze-PS'; $s.Description = 'Scadenze cassette pronto soccorso'; $s.Save()"

(
  echo @echo off
  echo title Disinstalla Scadenze PS
  echo echo Rimozione collegamenti e file...
  echo del /q "%%USERPROFILE%%\Desktop\Scadenze PS.lnk" 2^>nul
  echo del /q "%%APPDATA%%\Microsoft\Windows\Start Menu\Programs\Scadenze PS.lnk" 2^>nul
  echo rd /s /q "%%LOCALAPPDATA%%\Scadenze-PS"
  echo echo Fatto.
  echo pause
) > "%DEST%\Disinstalla.bat"

echo.
echo  Installazione completata.
echo  Avvia l'app dal collegamento "Scadenze PS" sul Desktop.
echo.
pause
endlocal
