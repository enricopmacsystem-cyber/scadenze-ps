# Setup PC filiale: verifica/installa Python + dipendenze, poi crea collegamento Desktop.
# Log: %LOCALAPPDATA%\Scadenze-PS\setup.log

$ErrorActionPreference = "Continue"

if (Test-Path (Join-Path $PSScriptRoot "avvia.pyw")) {
    $Root = $PSScriptRoot
} else {
    $Root = Split-Path -Parent $PSScriptRoot
}

$LogDir = Join-Path $env:LOCALAPPDATA "Scadenze-PS"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "setup.log"

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
    Write-Log $msg
}

function Write-Info([string]$msg) {
    Write-Host $msg
    Write-Log $msg
}

function Write-Err([string]$msg) {
    Write-Host $msg -ForegroundColor Red
    Write-Log "ERROR: $msg"
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$user;$machine"
}

function Add-PythonToSessionPath([string]$PythonExe) {
    $dir = Split-Path $PythonExe
    $scripts = Join-Path $dir "Scripts"
    if ($env:Path -notlike "*$dir*") {
        $env:Path = "$dir;$scripts;$env:Path"
    }
}

function Find-Python {
    Refresh-Path
    $candidates = New-Object System.Collections.Generic.List[string]

    foreach ($cmd in @("py", "python", "python3")) {
        $c = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($c -and $c.Source -notmatch "WindowsApps") {
            [void]$candidates.Add($c.Source)
        }
    }

    $local = $env:LOCALAPPDATA
    $globs = @(
        "$local\Programs\Python\Python3*\python.exe",
        "$env:ProgramFiles\Python3*\python.exe",
        "${env:ProgramFiles(x86)}\Python3*\python.exe"
    )
    foreach ($g in $globs) {
        Get-Item $g -ErrorAction SilentlyContinue | ForEach-Object {
            [void]$candidates.Add($_.FullName)
        }
    }

    foreach ($exe in $candidates) {
        try {
            $leaf = Split-Path -Leaf $exe
            if ($leaf -eq "py.exe") {
                $out = & $exe -3 -c 'import sys; print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0 -and $out) {
                    $resolved = ("$out").Trim()
                    if ($resolved -and (Test-Path $resolved) -and $resolved -notmatch "WindowsApps") {
                        return $resolved
                    }
                }
            } else {
                $out = & $exe -c 'import sys; assert sys.version_info >= (3, 10); print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0 -and $out) {
                    $resolved = ("$out").Trim()
                    if ($resolved -and (Test-Path $resolved)) { return $resolved }
                }
            }
        } catch {
            Write-Log "Find-Python skip $exe : $_"
        }
    }
    return $null
}

function Wait-ForPython([int]$seconds = 30) {
    for ($i = 0; $i -lt $seconds; $i += 2) {
        Refresh-Path
        $py = Find-Python
        if ($py) { return $py }
        Start-Sleep -Seconds 2
    }
    return $null
}

function Install-Python {
    Write-Step "Python non trovato. Tentativo di installazione..."

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Info "Provo con winget (Python 3.12, utente corrente)..."
        $wingetOut = & winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity 2>&1
        Write-Log ($wingetOut | Out-String)
        $py = Wait-ForPython 20
        if ($py) { return $py }
        Write-Info "winget non ha reso Python disponibile subito, provo installer ufficiale..."
    }

    Write-Info "Download installer ufficiale Python 3.12.10..."
    $installer = Join-Path $env:TEMP "python-3.12.10-amd64.exe"
    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    } catch {
        throw "Download Python fallito. Installa Python 3.12 da https://www.python.org/downloads/ (spunta Add python.exe to PATH) e rilancia. Dettaglio: $_"
    }

    Write-Info "Installazione silenziosa in corso (puo richiedere un minuto)..."
    $instArgs = @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_pip=1",
        "Include_launcher=1",
        "Include_test=0",
        "SimpleInstall=1"
    )
    $p = Start-Process -FilePath $installer -ArgumentList $instArgs -Wait -PassThru
    Write-Log "Python installer exit code: $($p.ExitCode)"
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) {
        throw "Installazione Python fallita (codice $($p.ExitCode)). Installa Python manualmente da python.org e rilancia."
    }

    $py = Wait-ForPython 40
    if (-not $py) {
        $guess = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
        if (Test-Path $guess) { return $guess }
        throw "Python sembra installato ma non risulta nel PATH. Chiudi questa finestra, riapri Crea collegamento Desktop.bat e riprova (oppure riavvia il PC)."
    }
    return $py
}

function Test-PythonImport([string]$PythonExe, [string]$Code) {
    # Evita -c con virgolette: PowerShell le mangia e print("OK") diventa print(OK)
    $tmp = Join-Path $env:TEMP ("scadenze_ps_check_{0}.py" -f [guid]::NewGuid().ToString("N"))
    Set-Content -Path $tmp -Value $Code -Encoding UTF8
    try {
        $out = & $PythonExe $tmp 2>&1
        $code = $LASTEXITCODE
        Write-Log "check exit=$code out=$out"
        return ($code -eq 0)
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Ensure-Dependencies([string]$PythonExe) {
    Write-Step "Verifica dipendenze (Flask, openpyxl, cryptography, pywin32)..."
    Add-PythonToSessionPath $PythonExe

    $ok = Test-PythonImport $PythonExe "import flask`nimport openpyxl`nimport cryptography`nfrom cryptography.fernet import Fernet`nimport win32com.client`nprint('OK')"
    if ($ok) {
        Write-Info "Dipendenze gia presenti."
        return
    }

    $reqSrc = Join-Path $Root "requirements-runtime.txt"
    if (-not (Test-Path $reqSrc)) {
        $reqSrc = Join-Path $Root "requirements.txt"
    }
    if (-not (Test-Path $reqSrc)) {
        throw "File requirements non trovato in $Root"
    }

    $reqLocal = Join-Path $env:TEMP "scadenze-ps-requirements.txt"
    Copy-Item $reqSrc $reqLocal -Force
    Write-Info "Installazione librerie (puo richiedere un minuto)..."

    & $PythonExe -m ensurepip --upgrade 2>&1 | ForEach-Object { Write-Log $_ }
    $pipUp = & $PythonExe -m pip install --upgrade pip 2>&1
    Write-Log ($pipUp | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "pip non funziona. Reinstalla Python spuntando 'pip' e 'Add to PATH'."
    }

    $pipInst = & $PythonExe -m pip install -r $reqLocal 2>&1
    Write-Log ($pipInst | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "Installazione librerie fallita. Serve Internet. Dettagli nel log: $LogFile"
    }

    # Messaggio COM "no permissions" di pywin32 e' innocuo per utenti non admin
    $ok2 = Test-PythonImport $PythonExe "import win32com.client`nprint('OK')"
    if (-not $ok2) {
        Write-Info "Configurazione pywin32..."
        $postScript = Join-Path (Split-Path $PythonExe) "Scripts\pywin32_postinstall.py"
        if (Test-Path $postScript) {
            & $PythonExe $postScript -install 2>&1 | ForEach-Object { Write-Log $_ }
        }
        $ok3 = Test-PythonImport $PythonExe "import win32com.client`nprint('OK')"
        if (-not $ok3) {
            throw "pywin32 non funziona. Dettagli nel log: $LogFile"
        }
    }
    Write-Info "Dipendenze installate correttamente."
}

function Create-Shortcut([string]$PythonExe) {
    Write-Step "Creazione collegamento Desktop..."
    $creatorNas = Join-Path $Root "Crea collegamento Desktop.pyw"
    if (-not (Test-Path $creatorNas)) {
        throw "File non trovato: $creatorNas"
    }

    # Copia script in locale: eseguire .pyw da NAS puo fallire
    $creatorLocal = Join-Path $LogDir "Crea_collegamento_Desktop.pyw"
    Copy-Item $creatorNas $creatorLocal -Force

    # Lo script usa Path(__file__).parent come root app — sbagliato se copiato in AppData!
    # Passiamo la root NAS come argomento.
    $env:SCADENZE_PS_APP_ROOT = "$Root"
    Write-Log "SCADENZE_PS_APP_ROOT=$Root"
    Write-Log "Eseguo: $PythonExe $creatorLocal"

    $out = & $PythonExe $creatorLocal 2>&1
    $code = $LASTEXITCODE
    Write-Log ($out | Out-String)
    Write-Log "shortcut exit: $code"
    Remove-Item Env:SCADENZE_PS_APP_ROOT -ErrorAction SilentlyContinue

    if ($code -ne 0) {
        throw "Creazione collegamento non riuscita (codice $code). Apri il log: $LogFile"
    }
}

# --- main ---
try {
    "" | Set-Content -Path $LogFile -Encoding UTF8
    Write-Host "========================================"
    Write-Host " Scadenze PS - preparazione PC"
    Write-Host "========================================"
    Write-Info "Cartella app: $Root"
    Write-Info "Log: $LogFile"

    if (-not (Test-Path (Join-Path $Root "avvia.pyw"))) {
        throw "Cartella app non valida (manca avvia.pyw): $Root"
    }

    Write-Step "Ricerca Python..."
    $python = Find-Python
    if (-not $python) {
        $python = Install-Python
    }
    Add-PythonToSessionPath $python
    Write-Info "Python: $python"
    $ver = & $python -c 'import sys; print(sys.version.split()[0])' 2>&1
    Write-Info "Versione: $ver"

    Ensure-Dependencies $python
    Create-Shortcut $python

    Write-Host ""
    Write-Host "Completato. Usa l icona Scadenze PS sul Desktop." -ForegroundColor Green
    Write-Log "SUCCESS"
    exit 0
}
catch {
    Write-Host ""
    Write-Err "ERRORE: $_"
    Write-Host ""
    Write-Host "Invia questo file all assistenza:" -ForegroundColor Yellow
    Write-Host "  $LogFile" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Premi un tasto per chiudere..."
    try {
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    } catch {
        Start-Sleep -Seconds 12
    }
    exit 1
}
