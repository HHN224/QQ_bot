param(
    [switch]$SkipInstall,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VirtualEnv = Join-Path $ProjectRoot ".venv"
$PythonExe = Join-Path $VirtualEnv "Scripts\python.exe"

Write-Host "[QQ Digest] Preparing local environment..." -ForegroundColor Cyan

if (-not (Test-Path $PythonExe)) {
    python -m venv $VirtualEnv
}

if (-not $SkipInstall) {
    & $PythonExe -m pip install -r (Join-Path $ProjectRoot "backend\requirements.txt")
    Push-Location (Join-Path $ProjectRoot "frontend")
    try {
        npm install
        npm run build
    }
    finally {
        Pop-Location
    }
}

$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[QQ Digest] No .env found. Local fallback mode will be used." -ForegroundColor Yellow
}

$BackendPath = Join-Path $ProjectRoot "backend"
$ServerArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")
$Server = Start-Process -FilePath $PythonExe -ArgumentList $ServerArgs -WorkingDirectory $BackendPath -PassThru -WindowStyle Hidden

try {
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 40; $Attempt++) {
        try {
            $Health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 1
            if ($Health.status -eq "ok") { $Ready = $true; break }
        }
        catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $Ready) { throw "Backend did not become ready. Run backend manually to inspect logs." }

    Write-Host "[QQ Digest] Running at http://127.0.0.1:8000" -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:8000" }
    Wait-Process -Id $Server.Id
}
finally {
    if ($Server -and -not $Server.HasExited) { Stop-Process -Id $Server.Id }
}
