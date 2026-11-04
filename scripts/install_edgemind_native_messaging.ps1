<#
.SYNOPSIS
    Installs and registers the EdgeMind Chrome Native Messaging Host for Profile 7.

.DESCRIPTION
    - Compiles or verifies scripts\edgemind_native_host.exe using csc.exe.
    - Resolves the EdgeMind extension ID (verifying in Profile 7 Secure Preferences).
    - Generates scripts\com.edgemind.native_host.json with the exact extension ID and executable path.
    - Registers the native messaging host under HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host.
    - Runs a self-check test to ensure complete readiness.
#>

[CmdletBinding()]
param (
    [string]$ExtensionId = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host " EdgeMind Native Messaging Host Installer" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host "Project Root : $ProjectRoot"

# 1. Resolve Extension ID
if (-not $ExtensionId) {
    # Attempt to auto-detect from Profile 7 Secure Preferences
    $secPref = "$env:LOCALAPPDATA\Google\Chrome\User Data\Profile 7\Secure Preferences"
    if (Test-Path $secPref) {
        try {
            $json = Get-Content -Raw -Path $secPref | ConvertFrom-Json
            $exts = $json.extensions.settings
            foreach ($prop in $exts.PSObject.Properties) {
                if ($prop.Value.path -and $prop.Value.path -match "edgemind") {
                    $ExtensionId = $prop.Name
                    Write-Host "[DETECTED] Found EdgeMind in Profile 7: $ExtensionId" -ForegroundColor Green
                    break
                }
            }
        } catch {
            Write-Host "[WARN] Could not parse Profile 7 Secure Preferences." -ForegroundColor Yellow
        }
    }
}

if (-not $ExtensionId) {
    # Fallback to verified ID
    $ExtensionId = "ajhfccooimcjfbablbbpicimdjolmndn"
    Write-Host "[INFO] Using default verified EdgeMind Extension ID: $ExtensionId" -ForegroundColor Cyan
}

# 2. Build / Verify Native Host Executable
$csSource = Join-Path $ScriptDir "edgemind_native_host.cs"
$exePath  = Join-Path $ScriptDir "edgemind_native_host.exe"

$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) {
    $csc = "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
}

if (Test-Path $csSource) {
    if (Test-Path $csc) {
        Write-Host "Compiling native messaging host executable with csc.exe..." -ForegroundColor Cyan
        $compileProc = Start-Process -FilePath $csc -ArgumentList "/nologo /target:exe /out:`"$exePath`" `"$csSource`"" -Wait -NoNewWindow -PassThru
        if ($compileProc.ExitCode -eq 0 -and (Test-Path $exePath)) {
            Write-Host "[SUCCESS] Compiled: $exePath" -ForegroundColor Green
        } else {
            Write-Host "[WARN] Compilation exited with code $($compileProc.ExitCode). Checking if prebuilt executable exists..." -ForegroundColor Yellow
        }
    }
}

if (-not (Test-Path $exePath)) {
    Write-Host "[ERROR] Native host executable not found at: $exePath" -ForegroundColor Red
    exit 1
}

# 3. Generate Native Host Manifest JSON (Strict UTF-8 without BOM)
$manifestPath = Join-Path $ScriptDir "com.edgemind.native_host.json"
$escapedExePath = $exePath.Replace("\", "\\")

$manifestJson = @"
{
  "name": "com.edgemind.native_host",
  "description": "EdgeMind Native Messaging Host for Backend Management",
  "path": "$escapedExePath",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://$ExtensionId/"
  ]
}
"@

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, $utf8NoBom)
Write-Host "[SUCCESS] Written manifest (UTF-8 without BOM): $manifestPath" -ForegroundColor Green

# 4. Register in Windows Registry (HKCU)
$registryKeyPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host"

if (-not (Test-Path $registryKeyPath)) {
    New-Item -Path $registryKeyPath -Force | Out-Null
}

Set-ItemProperty -Path $registryKeyPath -Name "(Default)" -Value $manifestPath
Write-Host "[SUCCESS] Registered in HKCU Registry:" -ForegroundColor Green
Write-Host "  Key   : $registryKeyPath" -ForegroundColor Green
Write-Host "  Value : $manifestPath" -ForegroundColor Green

# 5. Diagnostic Self-Check
Write-Host "`nRunning native host self-check..." -ForegroundColor Cyan
$selfCheck = Start-Process -FilePath $exePath -ArgumentList "--check" -Wait -NoNewWindow -PassThru
if ($selfCheck.ExitCode -eq 0) {
    Write-Host "[VERIFIED] Native messaging host self-check passed." -ForegroundColor Green
} else {
    Write-Host "[WARN] Self-check returned exit code $($selfCheck.ExitCode)." -ForegroundColor Yellow
}

Write-Host "`n====================================================" -ForegroundColor DarkCyan
Write-Host " EdgeMind Native Messaging Installation Complete!" -ForegroundColor Green
Write-Host " Chrome Profile 7 will now automatically launch the" -ForegroundColor Green
Write-Host " EdgeMind backend via Native Messaging on startup." -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor DarkCyan
