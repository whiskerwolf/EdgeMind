<#
.SYNOPSIS
    Guarantees the EdgeMind API is running and opens Google Chrome with Profile 7.

.DESCRIPTION
    1. Checks http://127.0.0.1:8000/health.
    2. If unavailable, starts the EdgeMind backend silently using the existing startup mechanism.
    3. Waits for /health to respond (timeout configurable, default 15s).
    4. Displays informative error if backend fails to start.
    5. Dynamically detects Google Chrome installation path.
    6. Launches or focuses Google Chrome with Profile 7.
    7. Avoids duplicate backend processes or unnecessary duplicate Chrome windows.
#>

[CmdletBinding()]
param (
    [int]$Port = 8000,
    [string]$HostAddress = "127.0.0.1",
    [int]$TimeoutSeconds = 15,
    [switch]$Silent
)

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path
$StartPs1    = Join-Path $ProjectRoot "scripts\start_edgemind_api.ps1"
$ErrLog      = Join-Path $ProjectRoot "logs\edgemind-api-error.log"
$OutLog      = Join-Path $ProjectRoot "logs\edgemind-api.log"
$HealthUrl   = "http://$HostAddress`:$Port/health"

function Show-Notification {
    param (
        [string]$Message,
        [string]$Title = "EdgeMind Chrome Launcher",
        [string]$Icon = "Information"
    )
    if (-not $Silent) {
        Write-Host "[$Icon] $Message" -ForegroundColor Yellow
    }
    # If invoked with hidden console, show GUI dialog
    $isConsoleVisible = [System.Environment]::UserInteractive -and ([System.Console]::WindowHeight -gt 0)
    if (-not $isConsoleVisible -or $Icon -eq "Error") {
        try {
            Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
            $msgIcon = if ($Icon -eq "Error") { [System.Windows.Forms.MessageBoxIcon]::Error } else { [System.Windows.Forms.MessageBoxIcon]::Information }
            [System.Windows.Forms.MessageBox]::Show($Message, $Title, [System.Windows.Forms.MessageBoxButtons]::OK, $msgIcon) | Out-Null
        } catch {}
    }
}

function Find-ChromeExecutable {
    # 1. Check registry App Paths
    $regPaths = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    )
    foreach ($rp in $regPaths) {
        if (Test-Path $rp) {
            $val = (Get-ItemProperty -Path $rp -ErrorAction SilentlyContinue).'(default)'
            if ($val -and (Test-Path $val)) {
                return $val
            }
        }
    }

    # 2. Check standard installation directories
    $candidates = @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
        (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path $cand)) {
            return $cand
        }
    }

    # 3. Check system PATH
    $cmd = Get-Command "chrome.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    return $null
}

# =============================================================================
# 1. Check Backend Health
# =============================================================================
if (-not $Silent) {
    Write-Host "Checking EdgeMind backend at $HealthUrl..." -ForegroundColor Cyan
}

$isHealthy = $false
try {
    $resp = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2 -ErrorAction Stop
    if ($resp -and $resp.status -eq "healthy") {
        $isHealthy = $true
        if (-not $Silent) {
            Write-Host "[OK] EdgeMind API is already active and healthy." -ForegroundColor Green
        }
    }
} catch {
    $isHealthy = $false
}

# =============================================================================
# 2. Start Backend Silently if Unavailable
# =============================================================================
if (-not $isHealthy) {
    if (-not $Silent) {
        Write-Host "EdgeMind API is offline. Starting backend service..." -ForegroundColor Yellow
    }

    if (-not (Test-Path $StartPs1)) {
        Show-Notification -Message "Startup script not found at $StartPs1" -Icon "Error"
        exit 1
    }

    # Launch start_edgemind_api.ps1 in hidden process
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell.exe"
    $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartPs1`""
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $psi.CreateNoWindow = $true
    $psi.UseShellExecute = $false

    $startProc = [System.Diagnostics.Process]::Start($psi)
    $startProc.WaitForExit()

    # Poll /health until healthy or timeout
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        Start-Sleep -Milliseconds 400
        try {
            $checkResp = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 1 -ErrorAction Stop
            if ($checkResp -and $checkResp.status -eq "healthy") {
                $isHealthy = $true
                break
            }
        } catch {}
    }
    $sw.Stop()

    if (-not $isHealthy) {
        $errMsg = "EdgeMind API failed to start on $HostAddress`:$Port within $TimeoutSeconds seconds."
        if (Test-Path $ErrLog) {
            $errContent = Get-Content -Path $ErrLog -Tail 10 -ErrorAction SilentlyContinue
            if ($errContent) {
                $errMsg += "`n`nRecent log errors:`n" + ($errContent -join "`n")
            }
        }
        Show-Notification -Message $errMsg -Icon "Error"
        exit 1
    }

    if (-not $Silent) {
        Write-Host "[OK] EdgeMind API is now online and healthy." -ForegroundColor Green
    }
}

# =============================================================================
# 3. Locate Chrome and Launch Profile 7
# =============================================================================
$chromePath = Find-ChromeExecutable

if (-not $chromePath) {
    Show-Notification -Message "Google Chrome executable could not be found on this computer.`nPlease install Google Chrome or add it to your PATH." -Icon "Error"
    exit 1
}

if (-not $Silent) {
    Write-Host "Launching Google Chrome (Profile 7)..." -ForegroundColor Cyan
    Write-Host "  Chrome : $chromePath" -ForegroundColor DarkGray
    Write-Host "  Profile: Profile 7" -ForegroundColor DarkGray
}

try {
    Start-Process -FilePath $chromePath -ArgumentList @('--profile-directory="Profile 7"')
    if (-not $Silent) {
        Write-Host "[SUCCESS] Chrome Profile 7 launched successfully." -ForegroundColor Green
    }
} catch {
    Show-Notification -Message "Failed to start Google Chrome: $($_.Exception.Message)" -Icon "Error"
    exit 1
}

exit 0

