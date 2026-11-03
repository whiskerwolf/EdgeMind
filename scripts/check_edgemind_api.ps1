<#
.SYNOPSIS
    Checks the status and health of the EdgeMind FastAPI backend service.

.DESCRIPTION
    - Verifies port 8000 socket listener.
    - Sends GET request to http://127.0.0.1:8000/health.
    - Validates JSON response schema.
    - Displays Connected, Offline, or Error with diagnostic information.
    - Shows PID and troubleshooting instructions if offline.
#>

[CmdletBinding()]
param (
    [int]$Port = 8000,
    [string]$HostAddress = "127.0.0.1",
    [int]$TimeoutSeconds = 3
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path
$PidFile = Join-Path $ProjectRoot "logs\edgemind-api.pid"
$ErrLog  = Join-Path $ProjectRoot "logs\edgemind-api-error.log"

Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host " EdgeMind Backend Health Status Check" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor DarkCyan

$healthUri = "http://$HostAddress`:$Port/health"

# 1. Check Port Listener
$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $conn) {
    Write-Host "[STATUS] Offline" -ForegroundColor Red
    Write-Host "  Reason   : Port $Port is not listening." -ForegroundColor Yellow
    Write-Host "  Solution : Start the server using:" -ForegroundColor Yellow
    Write-Host "             powershell -ExecutionPolicy Bypass -File .\scripts\start_edgemind_api.ps1" -ForegroundColor Cyan
    exit 2
}

$owningPid = $conn.OwningProcess
$cmdLine = ""
try {
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $owningPid" -ErrorAction SilentlyContinue
    if ($cim) { $cmdLine = $cim.CommandLine }
} catch {}

# 2. Query /health
try {
    $resp = Invoke-RestMethod -Uri $healthUri -Method Get -TimeoutSec $TimeoutSeconds -ErrorAction Stop

    if ($resp -and $resp.status -eq "healthy") {
        Write-Host "[STATUS] Connected" -ForegroundColor Green
        Write-Host "  Service  : $($resp.service)" -ForegroundColor Green
        Write-Host "  Status   : $($resp.status)" -ForegroundColor Green
        Write-Host "  Endpoint : $healthUri" -ForegroundColor Green
        Write-Host "  PID      : $owningPid" -ForegroundColor Green
        if ($cmdLine) {
            Write-Host "  Command  : $cmdLine" -ForegroundColor DarkGray
        }
        exit 0
    } else {
        Write-Host "[STATUS] Error" -ForegroundColor Red
        Write-Host "  Port $Port is listening, but /health returned an unexpected response:" -ForegroundColor Red
        Write-Host "  $($resp | ConvertTo-Json -Compress)" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "[STATUS] Error" -ForegroundColor Red
    Write-Host "  Port $Port is listening (PID: $owningPid), but /health request failed:" -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Yellow

    if ($cmdLine -and $cmdLine -notmatch "core\.api") {
        Write-Host "  NOTE: Port $Port appears to be occupied by an unrelated service:" -ForegroundColor Yellow
        Write-Host "        $cmdLine" -ForegroundColor DarkGray
    } elseif (Test-Path $ErrLog) {
        $recentErrors = Get-Content -Path $ErrLog -Tail 10 -ErrorAction SilentlyContinue
        if ($recentErrors) {
            Write-Host "--- Recent Server Errors ---" -ForegroundColor Yellow
            $recentErrors | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        }
    }
    exit 1
}

