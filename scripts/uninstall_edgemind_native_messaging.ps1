<#
.SYNOPSIS
    Uninstalls the EdgeMind Chrome Native Messaging Host.

.DESCRIPTION
    - Removes the registry key HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host.
    - Removes installed com.edgemind.native_host.json.
    - Safely leaves project files, backend scripts, and extension intact.
    - Supports automated testing via -ManifestDir, -RegistryKey, and -NoRegistry.
#>

[CmdletBinding()]
param (
    [string]$ManifestDir = "",
    [string]$RegistryKey = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host",
    [switch]$NoRegistry,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $Quiet) {
    Write-Host "====================================================" -ForegroundColor DarkCyan
    Write-Host " EdgeMind Native Messaging Uninstaller" -ForegroundColor Cyan
    Write-Host "====================================================" -ForegroundColor DarkCyan
}

# 1. Remove Registry Key unless -NoRegistry
if (-not $NoRegistry) {
    if (Test-Path $RegistryKey) {
        Remove-Item -Path $RegistryKey -Recurse -Force
        if (-not $Quiet) {
            Write-Host "[SUCCESS] Removed registry key: $RegistryKey" -ForegroundColor Green
        }
    } else {
        if (-not $Quiet) {
            Write-Host "[INFO] Registry key was not present: $RegistryKey" -ForegroundColor Cyan
        }
    }
}

# 2. Resolve Manifest Directory to clean up
if ($ManifestDir) {
    $targetDir = $ManifestDir
} else {
    $targetDir = Join-Path $env:LOCALAPPDATA "EdgeMind"
}

$installedManifest = Join-Path $targetDir "com.edgemind.native_host.json"
if (Test-Path $installedManifest) {
    Remove-Item -Path $installedManifest -Force
    if (-not $Quiet) {
        Write-Host "[SUCCESS] Removed manifest file: $installedManifest" -ForegroundColor Green
    }
}

# Clean up directory if empty
if ((Test-Path $targetDir) -and ((Get-ChildItem -Path $targetDir).Count -eq 0)) {
    Remove-Item -Path $targetDir -Force
    if (-not $Quiet) {
        Write-Host "[SUCCESS] Removed empty directory: $targetDir" -ForegroundColor Green
    }
}

if (-not $Quiet) {
    Write-Host "`n[DONE] Native messaging integration uninstalled cleanly." -ForegroundColor Green
}
