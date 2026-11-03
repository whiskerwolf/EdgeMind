<#
.SYNOPSIS
    Creates a Windows Desktop shortcut named 'EdgeMind Chrome'.

.DESCRIPTION
    - Detects Google Chrome installation path dynamically across registry, Program Files, and AppData.
    - Points shortcut to launch_edgemind_chrome.vbs (which executes launch_edgemind_chrome.ps1 silently).
    - Sets the shortcut icon to Chrome's native icon for seamless visual integration.
    - Saves shortcut to the current user's desktop: 'Desktop\EdgeMind Chrome.lnk'.
#>

[CmdletBinding()]
param ()

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path
$LauncherVbs = Join-Path $ProjectRoot "scripts\launch_edgemind_chrome.vbs"

function Find-ChromeExecutable {
    # 1. Registry App Paths
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

    # 2. Standard directories
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

    # 3. PATH
    $cmd = Get-Command "chrome.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    return $null
}

Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host " EdgeMind Desktop Shortcut Generator" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor DarkCyan

$desktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$shortcutPath = Join-Path $desktopPath "EdgeMind Chrome.lnk"

$chromePath = Find-ChromeExecutable
if ($chromePath) {
    Write-Host "Detected Chrome Executable: $chromePath" -ForegroundColor Green
} else {
    Write-Host "[WARNING] Chrome executable not found in registry/standard paths. Using default icon." -ForegroundColor Yellow
}

try {
    $wshShell = New-Object -ComObject WScript.Shell
    $shortcut = $wshShell.CreateShortcut($shortcutPath)

    # Use wscript.exe targeting launch_edgemind_chrome.vbs for zero-window flash
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = "`"$LauncherVbs`""
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.Description = "EdgeMind - Start API and Open Chrome Profile 7"

    if ($chromePath) {
        $shortcut.IconLocation = "$chromePath,0"
    }

    $shortcut.Save()

    Write-Host "[SUCCESS] Desktop shortcut created successfully!" -ForegroundColor Green
    Write-Host "  Shortcut : $shortcutPath" -ForegroundColor Green
    Write-Host "  Target   : wscript.exe `"$LauncherVbs`"" -ForegroundColor DarkGray
    Write-Host "  Icon     : $(if ($chromePath) { "$chromePath,0" } else { "Default" })" -ForegroundColor DarkGray
} catch {
    Write-Host "[ERROR] Failed to create desktop shortcut: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

exit 0

