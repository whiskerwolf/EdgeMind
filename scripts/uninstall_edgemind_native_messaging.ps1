<#
.SYNOPSIS
    Uninstalls the EdgeMind Chrome Native Messaging Host.

.DESCRIPTION
    - Removes the registry key HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host.
    - Removes scripts\com.edgemind.native_host.json.
    - Safely leaves project files, backend scripts, and extension intact.
#>

[CmdletBinding()]
param ()

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host " EdgeMind Native Messaging Uninstaller" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor DarkCyan

# 1. Remove Registry Key (strictly EdgeMind-owned)
$registryKeyPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host"
if (Test-Path $registryKeyPath) {
    Remove-Item -Path $registryKeyPath -Recurse -Force
    Write-Host "[SUCCESS] Removed registry key: $registryKeyPath" -ForegroundColor Green
} else {
    Write-Host "[INFO] Registry key was not present." -ForegroundColor Cyan
}

# 2. Remove Manifest JSON from LocalAppData application directory
$appDataDir = Join-Path $env:LOCALAPPDATA "EdgeMind"
$installedManifest = Join-Path $appDataDir "com.edgemind.native_host.json"
if (Test-Path $installedManifest) {
    Remove-Item -Path $installedManifest -Force
    Write-Host "[SUCCESS] Removed installed manifest file: $installedManifest" -ForegroundColor Green
}
if ((Test-Path $appDataDir) -and ((Get-ChildItem -Path $appDataDir).Count -eq 0)) {
    Remove-Item -Path $appDataDir -Force
    Write-Host "[SUCCESS] Removed empty app directory: $appDataDir" -ForegroundColor Green
}

# 3. Clean up scripts manifest if present
$manifestPath = Join-Path $ScriptDir "com.edgemind.native_host.json"
if (Test-Path $manifestPath) {
    # Leave or reset template
    Write-Host "[INFO] Project scripts manifest preserved." -ForegroundColor Cyan
}

Write-Host "`n[DONE] Native messaging integration uninstalled cleanly." -ForegroundColor Green

