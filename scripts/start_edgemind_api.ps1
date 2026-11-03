<#
.SYNOPSIS
    Starts the EdgeMind FastAPI backend server as an independent background process.

.DESCRIPTION
    - Automatically detects the project root directory.
    - Validates virtual environment Python (.venv\Scripts\python.exe).
    - Checks port 8000. If already running and healthy, reuses it without duplicate spawn.
    - Detects port conflicts with non-EdgeMind services and halts safely without killing them.
    - Launches Uvicorn detached from the calling terminal/job object via Windows Process Create.
    - Redirects standard output and error streams into logs/edgemind-api.log and logs/edgemind-api-error.log.
    - Saves the active process ID into logs/edgemind-api.pid.
    - Polls /health until responsive or timeout.
#>

[CmdletBinding()]
param (
    [int]$Port = 8000,
    [string]$HostAddress = "127.0.0.1",
    [int]$TimeoutSeconds = 15
)

$ErrorActionPreference = "Stop"

# 1. Resolve Project Root and Paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogsDir   = Join-Path $ProjectRoot "logs"
$PidFile   = Join-Path $LogsDir "edgemind-api.pid"
$OutLog    = Join-Path $LogsDir "edgemind-api.log"
$ErrLog    = Join-Path $LogsDir "edgemind-api-error.log"

# Ensure logs directory exists
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
}

Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host " EdgeMind Backend Launcher (FastAPI / Uvicorn)" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host "Project Root : $ProjectRoot"
Write-Host "Target Host  : $HostAddress`:$Port"

# 2. Verify Virtual Environment
if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Virtual environment Python not found at: $PythonExe" -ForegroundColor Red
    Write-Host "Please ensure the .venv virtual environment is configured before starting." -ForegroundColor Yellow
    exit 1
}

# 3. Check If Port is Already Occupied
$existingConn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1

if ($existingConn) {
    $owningPid = $existingConn.OwningProcess
    # Test if existing server is already healthy
    try {
        $healthUri = "http://$HostAddress`:$Port/health"
        $resp = Invoke-RestMethod -Uri $healthUri -Method Get -TimeoutSec 3 -ErrorAction Stop
        if ($resp -and $resp.status -eq "healthy") {
            Set-Content -Path $PidFile -Value $owningPid -Encoding utf8
            Write-Host "[ALREADY RUNNING] EdgeMind API is already active and healthy on port $Port." -ForegroundColor Green
            Write-Host "  PID    : $owningPid" -ForegroundColor Green
            Write-Host "  Health : $healthUri" -ForegroundColor Green
            Write-Host "Reusing existing background instance." -ForegroundColor Cyan
            exit 0
        }
    } catch {
        # Port is listening but /health did not return healthy
    }

    # Inspect the conflicting process
    $conflictingProc = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
    $procName = if ($conflictingProc) { $conflictingProc.ProcessName } else { "Unknown" }
    $cmdLine = ""
    try {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $owningPid" -ErrorAction SilentlyContinue
        if ($cim) { $cmdLine = $cim.CommandLine }
    } catch {}

    # If it is an EdgeMind process that is stuck/unresponsive, inform user
    if ($cmdLine -and $cmdLine -match "core\.api:app") {
        Write-Host "[WARNING] Port $Port is held by an unresponsive EdgeMind process (PID: $owningPid)." -ForegroundColor Yellow
        Write-Host "Run .\scripts\stop_edgemind_api.ps1 to cleanly stop it first, then start again." -ForegroundColor Yellow
        exit 1
    }

    # Non-EdgeMind conflict
    Write-Host "[PORT CONFLICT] Port $Port is already in use by another process." -ForegroundColor Red
    Write-Host "  PID     : $owningPid" -ForegroundColor Red
    Write-Host "  Process : $procName" -ForegroundColor Red
    if ($cmdLine) {
        Write-Host "  Command : $cmdLine" -ForegroundColor DarkGray
    }
    Write-Host "EdgeMind will NOT terminate third-party processes. Please free port $Port and try again." -ForegroundColor Yellow
    exit 1
}

# 4. Clean Stale PID File if Port is free
if (Test-Path $PidFile) {
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
}

# 5. Rotate Logs if over 5 MB
$maxLogBytes = 5 * 1024 * 1024
foreach ($logFile in @($OutLog, $ErrLog)) {
    if (Test-Path $logFile) {
        $fileItem = Get-Item $logFile
        if ($fileItem.Length -gt $maxLogBytes) {
            $backupFile = "$logFile.old"
            Move-Item -Path $logFile -Destination $backupFile -Force -ErrorAction SilentlyContinue
        }
    }
}

# 6. Launch Uvicorn as Independent Detached Background Process
# Using Win32_Process Create via cmd.exe redirection ensures process detachment from terminal job objects
Write-Host "Launching Uvicorn background process..." -ForegroundColor Cyan

$launchCmd = "cmd.exe /c `"`"$PythonExe`" -m uvicorn core.api:app --host $HostAddress --port $Port >> `"$OutLog`" 2>> `"$ErrLog`"`""

$createResult = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine      = $launchCmd
    CurrentDirectory = $ProjectRoot
}

if ($createResult.ReturnValue -ne 0) {
    Write-Host "[ERROR] Win32_Process Create failed with return code $($createResult.ReturnValue)." -ForegroundColor Red
    exit 1
}

# 7. Poll /health until ready
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$healthUrl = "http://$HostAddress`:$Port/health"
$isHealthy = $false
$serverPid = 0

while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
    Start-Sleep -Milliseconds 500

    # Query TCP Connection to identify the listening process PID
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $serverPid = $conn.OwningProcess
    }

    try {
        $res = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 1 -ErrorAction Stop
        if ($res -and $res.status -eq "healthy") {
            $isHealthy = $true
            break
        }
    } catch {
        # Still starting up
    }
}

$sw.Stop()

# 8. Report Status and Persist PID
if ($isHealthy) {
    if ($serverPid -eq 0) {
        $finalConn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($finalConn) {
            $serverPid = $finalConn.OwningProcess
        }
    }
    if ($serverPid -gt 0) {
        Set-Content -Path $PidFile -Value $serverPid -Encoding utf8
    }
    Write-Host "[SUCCESS] EdgeMind API is online and healthy!" -ForegroundColor Green
    Write-Host "  Endpoint   : http://$HostAddress`:$Port" -ForegroundColor Green
    Write-Host "  Health URL : $healthUrl" -ForegroundColor Green
    Write-Host "  PID        : $serverPid" -ForegroundColor Green
    Write-Host "  Log File   : $OutLog" -ForegroundColor DarkGray
    Write-Host "  Error Log  : $ErrLog" -ForegroundColor DarkGray
    exit 0
} else {
    Write-Host "[ERROR] EdgeMind API failed to respond within $TimeoutSeconds seconds." -ForegroundColor Red
    if (Test-Path $ErrLog) {
        $recentErrors = Get-Content -Path $ErrLog -Tail 20 -ErrorAction SilentlyContinue
        if ($recentErrors) {
            Write-Host "--- Recent Error Log Output ---" -ForegroundColor Yellow
            $recentErrors | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        }
    }
    if (Test-Path $OutLog) {
        $recentOut = Get-Content -Path $OutLog -Tail 20 -ErrorAction SilentlyContinue
        if ($recentOut) {
            Write-Host "--- Recent Standard Output ---" -ForegroundColor DarkGray
            $recentOut | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        }
    }
    exit 1
}
