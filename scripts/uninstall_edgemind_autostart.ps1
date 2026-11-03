<#
.SYNOPSIS
    Uninstalls the EdgeMind automatic startup Scheduled Task.

.DESCRIPTION
    - Removes only the Windows Scheduled Task 'EdgeMindBackendAutostart'.
    - Strictly does not delete or modify project code, virtual environment, logs, user data,
      or the original extension in extension/chrome/.
    - Optionally removes the desktop shortcut if -RemoveShortcut is passed.
#>

[CmdletBinding()]
param (
    [string]$TaskName = "EdgeMindBackendAutostart",
    [switch]$RemoveShortcut
)

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host " EdgeMind Autostart Uninstaller" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host "Task Name : $TaskName"

# 1. Connect to Schedule.Service and Delete Task
$taskDeleted = $false
try {
    $service = New-Object -ComObject("Schedule.Service")
    $service.Connect()
    $rootFolder = $service.GetFolder("\")

    $existingTask = $null
    try {
        $existingTask = $rootFolder.GetTask($TaskName)
    } catch {}

    if ($existingTask) {
        $rootFolder.DeleteTask($TaskName, 0)
        Write-Host "[SUCCESS] Scheduled Task '$TaskName' removed successfully." -ForegroundColor Green
        $taskDeleted = $true
    } else {
        Write-Host "[INFO] Scheduled Task '$TaskName' was not found (already uninstalled)." -ForegroundColor Yellow
    }
} catch {
    # Fallback to schtasks.exe if COM throws
    try {
        $res = schtasks.exe /Delete /TN $TaskName /F 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[SUCCESS] Scheduled Task '$TaskName' removed via schtasks." -ForegroundColor Green
            $taskDeleted = $true
        } else {
            Write-Host "[INFO] Scheduled Task '$TaskName' was not found." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[WARNING] Could not remove scheduled task: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# 2. Optionally remove desktop shortcut
if ($RemoveShortcut) {
    $desktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
    $shortcutPath = Join-Path $desktopPath "EdgeMind Chrome.lnk"
    if (Test-Path $shortcutPath) {
        Remove-Item -Path $shortcutPath -Force -ErrorAction SilentlyContinue
        Write-Host "[SUCCESS] Desktop shortcut 'EdgeMind Chrome' removed." -ForegroundColor Green
    }
}

Write-Host "`nSafety guarantee:" -ForegroundColor DarkGray
Write-Host "  - No project files or source code were modified." -ForegroundColor DarkGray
Write-Host "  - No virtual environment or dependencies were altered." -ForegroundColor DarkGray
Write-Host "  - No user data or Chrome extensions were touched." -ForegroundColor DarkGray
Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host " EdgeMind autostart has been cleanly uninstalled." -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor DarkCyan
exit 0

