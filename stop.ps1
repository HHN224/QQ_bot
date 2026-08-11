$ErrorActionPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ProjectRoot "data\server.pid"

if (-not (Test-Path $PidFile)) { exit 0 }
$ServerProcessId = [int](Get-Content -LiteralPath $PidFile -Raw)
$ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ServerProcessId"
if ($ProcessInfo -and $ProcessInfo.CommandLine -match "uvicorn.+app\.main:app") {
    Stop-Process -Id $ServerProcessId -Force
}
Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
