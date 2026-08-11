param(
    [switch]$SkipInstall,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VirtualEnv = Join-Path $ProjectRoot ".venv"
$PythonExe = Join-Path $VirtualEnv "Scripts\python.exe"
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$FrontendBuild = Join-Path $FrontendRoot "dist\index.html"
$NodeModules = Join-Path $FrontendRoot "node_modules"
$PidFile = Join-Path $ProjectRoot "data\server.pid"
$AppUrl = "http://127.0.0.1:8000"

function Test-DigestServer {
    try {
        $Health = Invoke-RestMethod -Uri "$AppUrl/api/health" -TimeoutSec 1
        return $Health.status -eq "ok" -and $Health.local_only -eq $true
    }
    catch {
        return $false
    }
}

if (Test-DigestServer) {
    Write-Host "[QQ Digest] Already running at $AppUrl" -ForegroundColor Green
    if (-not $NoBrowser) { Start-Process $AppUrl }
    exit 0
}

Write-Host "[QQ Digest] Preparing local environment..." -ForegroundColor Cyan

if (-not (Test-Path $PythonExe)) {
    python -m venv $VirtualEnv
}

$NeedsInstall = -not (Test-Path $NodeModules) -or -not (Test-Path $FrontendBuild)
if (-not $SkipInstall -or $NeedsInstall) {
    & $PythonExe -m pip install -r (Join-Path $ProjectRoot "backend\requirements.txt")
    Push-Location $FrontendRoot
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
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $PidFile) | Out-Null
Set-Content -LiteralPath $PidFile -Value $Server.Id -Encoding ASCII

try {
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 80; $Attempt++) {
        if ($Server.HasExited) { throw "Backend stopped before becoming ready." }
        if (Test-DigestServer) { $Ready = $true; break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $Ready) { throw "Backend did not become ready. Run start.ps1 in PowerShell to inspect logs." }

    Write-Host "[QQ Digest] Running at $AppUrl" -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
    if (-not $NoBrowser) { Start-Process $AppUrl }
    Wait-Process -Id $Server.Id
}
finally {
    if ($Server -and -not $Server.HasExited) { Stop-Process -Id $Server.Id }
    if (Test-Path $PidFile) {
        $RecordedId = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
        if ($RecordedId -eq $Server.Id) { Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue }
    }
}
