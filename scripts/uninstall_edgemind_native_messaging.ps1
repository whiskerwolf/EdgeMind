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

# 1. Remove Registry Key
$registryKeyPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host"
if (Test-Path $registryKeyPath) {
    Remove-Item -Path $registryKeyPath -Recurse -Force
    Write-Host "[SUCCESS] Removed registry key: $registryKeyPath" -ForegroundColor Green
} else {
    Write-Host "[INFO] Registry key was not present." -ForegroundColor Cyan
}

# 2. Remove Manifest JSON
$manifestPath = Join-Path $ScriptDir "com.edgemind.native_host.json"
if (Test-Path $manifestPath) {
    Remove-Item -Path $manifestPath -Force
    Write-Host "[SUCCESS] Removed manifest file: $manifestPath" -ForegroundColor Green
}

Write-Host "`n[DONE] Native messaging integration uninstalled cleanly." -ForegroundColor Green

