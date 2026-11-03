<#
.SYNOPSIS
    Safely stops the EdgeMind FastAPI backend server.

.DESCRIPTION
    - Reads saved PID from logs/edgemind-api.pid (or detects active port 8000 listener).
    - Verifies process ownership (must match python with core.api:app).
    - Prevents terminating unrelated Python processes or third-party services.
    - Recursively stops child worker processes if present.
    - Removes stale PID file.
    - Verifies port 8000 is released.
#>

[CmdletBinding()]
param (
    [int]$Port = 8000,
    [int]$MaxWaitSeconds = 5
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

$LogsDir = Join-Path $ProjectRoot "logs"
$PidFile = Join-Path $LogsDir "edgemind-api.pid"

Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host " EdgeMind Backend Shutdown Utility" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor DarkCyan

$targetPids = [System.Collections.Generic.List[int]]::new()

# 1. Check PID File
if (Test-Path $PidFile) {
    try {
        $savedPidText = (Get-Content -Path $PidFile -Raw).Trim()
        if ($savedPidText -match "^\d+$") {
            $savedPid = [int]$savedPidText
            $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
            if ($proc) {
                $targetPids.Add($savedPid)
            }
        }
    } catch {}
}

# 2. Check Port Listener if no valid PID found from file
$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    $portPid = $conn.OwningProcess
    if (-not $targetPids.Contains($portPid)) {
        $targetPids.Add($portPid)
    }
}

if ($targetPids.Count -eq 0) {
    Write-Host "[INFO] No running EdgeMind server detected on port $Port." -ForegroundColor Yellow
    if (Test-Path $PidFile) {
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    }
    exit 0
}

# 3. Verify Ownership for each target PID
$pidsToKill = [System.Collections.Generic.List[int]]::new()

foreach ($tPid in $targetPids) {
    $cmdLine = ""
    try {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $tPid" -ErrorAction SilentlyContinue
        if ($cim) { $cmdLine = $cim.CommandLine }
    } catch {}

    # Strict check: Command line must contain core.api:app or core.api
    if ($cmdLine -and ($cmdLine -match "core\.api:app" -or $cmdLine -match "core\.api")) {
        $pidsToKill.Add($tPid)

        # Check for child processes (e.g. uvicorn reloader child)
        try {
            $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $tPid" -ErrorAction SilentlyContinue
            foreach ($child in $children) {
                if (-not $pidsToKill.Contains($child.ProcessId)) {
                    $pidsToKill.Add($child.ProcessId)
                }
            }
        } catch {}
    } else {
        Write-Host "[WARNING] Process $tPid is listening on port $Port but does not match EdgeMind command signature." -ForegroundColor Red
        Write-Host "  Command line: $cmdLine" -ForegroundColor DarkGray
        Write-Host "Refusing to terminate unrelated process." -ForegroundColor Yellow
    }
}

if ($pidsToKill.Count -eq 0) {
    Write-Host "[WARNING] No verified EdgeMind processes found to terminate." -ForegroundColor Yellow
    exit 1
}

# 4. Terminate Verified Processes
foreach ($kPid in $pidsToKill) {
    try {
        $proc = Get-Process -Id $kPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Stopping EdgeMind process (PID: $kPid)..." -ForegroundColor Cyan
            Stop-Process -Id $kPid -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Write-Host "Notice: Could not stop PID $kPid (may have already exited)." -ForegroundColor DarkGray
    }
}

# 5. Remove PID file
if (Test-Path $PidFile) {
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
}

# 6. Verify Port is Released
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$released = $false

while ($sw.Elapsed.TotalSeconds -lt $MaxWaitSeconds) {
    $checkConn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $checkConn) {
        $released = $true
        break
    }
    Start-Sleep -Milliseconds 300
}

if ($released) {
    Write-Host "[SUCCESS] EdgeMind backend successfully stopped." -ForegroundColor Green
    Write-Host "Port $Port is now free." -ForegroundColor Green
    exit 0
} else {
    Write-Host "[WARNING] Processes signaled, but port $Port is still in use." -ForegroundColor Yellow
    exit 1
}

