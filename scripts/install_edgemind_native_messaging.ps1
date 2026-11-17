<#
.SYNOPSIS
    Installs and registers the EdgeMind Chrome Native Messaging Host.

.DESCRIPTION
    - Resolves the actual installation directory and native host executable path.
    - Supports custom installation directories, executable paths, and directories containing spaces.
    - Validates or discovers the exact Chrome extension ID (defaulting to the verified extension ID).
    - Guarantees exact extension origin formatting without wildcards.
    - Generates valid UTF-8 JSON without BOM for the native host manifest.
    - Registers the installed manifest in HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host.
    - Supports automated test isolation via -NoRegistry or -RegistryKey parameters.
#>

[CmdletBinding()]
param (
    [string]$ExtensionId = "",
    [string]$ExecutablePath = "",
    [string]$ManifestDir = "",
    [string]$RegistryKey = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host",
    [switch]$NoRegistry,
    [switch]$NoCompile,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

if (-not $Quiet) {
    Write-Host "====================================================" -ForegroundColor DarkCyan
    Write-Host " EdgeMind Native Messaging Host Installer" -ForegroundColor Cyan
    Write-Host "====================================================" -ForegroundColor DarkCyan
    Write-Host "Project Root : $ProjectRoot"
}

# 1. Resolve Executable Path (supports spaces and arbitrary Windows user/install directories)
if ($ExecutablePath) {
    if (-not (Test-Path $ExecutablePath)) {
        Write-Error "Specified executable not found at: $ExecutablePath"
        exit 1
    }
    $targetExe = (Resolve-Path $ExecutablePath).Path
} else {
    $targetExe = Join-Path $ScriptDir "edgemind_native_host.exe"
}

# Compile if missing and -NoCompile is not specified
if ((-not (Test-Path $targetExe)) -and (-not $NoCompile)) {
    $csSource = Join-Path $ScriptDir "edgemind_native_host.cs"
    $csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if (-not (Test-Path $csc)) {
        $csc = "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
    }
    if ((Test-Path $csSource) -and (Test-Path $csc)) {
        if (-not $Quiet) {
            Write-Host "Compiling native host executable: $targetExe..." -ForegroundColor Cyan
        }
        $compileProc = Start-Process -FilePath $csc -ArgumentList "/nologo /target:exe /out:`"$targetExe`" `"$csSource`"" -Wait -NoNewWindow -PassThru
        if ($compileProc.ExitCode -ne 0) {
            Write-Warning "Compilation returned exit code $($compileProc.ExitCode)."
        }
    }
}

if (-not (Test-Path $targetExe)) {
    Write-Error "Native host executable could not be found or built at: $targetExe"
    exit 1
}

$canonicalExePath = (Resolve-Path $targetExe).Path
if (-not $Quiet) {
    Write-Host "Native Host  : $canonicalExePath"
}

# 2. Resolve and Validate Extension ID & Origin (No Wildcards)
if (-not $ExtensionId) {
    # Check Profile 7 or Default profile Secure Preferences if present
    $possiblePrefs = @(
        "$env:LOCALAPPDATA\Google\Chrome\User Data\Profile 7\Secure Preferences",
        "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Secure Preferences"
    )
    foreach ($pref in $possiblePrefs) {
        if (Test-Path $pref) {
            try {
                $json = Get-Content -Raw -Path $pref | ConvertFrom-Json
                $exts = $json.extensions.settings
                foreach ($prop in $exts.PSObject.Properties) {
                    if ($prop.Value.path -and $prop.Value.path -match "edgemind") {
                        $ExtensionId = $prop.Name
                        if (-not $Quiet) {
                            Write-Host "[DETECTED] Found EdgeMind extension ID: $ExtensionId" -ForegroundColor Green
                        }
                        break
                    }
                }
            } catch {}
        }
        if ($ExtensionId) { break }
    }
}

if (-not $ExtensionId) {
    # Verified default EdgeMind extension ID
    $ExtensionId = "dcpgjneeokaigdhocommnadngnbaebgg"
    if (-not $Quiet) {
        Write-Host "[INFO] Using default verified EdgeMind Extension ID: $ExtensionId" -ForegroundColor Cyan
    }
}

# Strict extension ID validation: exactly 32 lowercase alpha characters [a-p]
if ($ExtensionId -notmatch '^[a-p]{32}$') {
    Write-Error "Invalid Extension ID format: '$ExtensionId'. Must be exactly 32 lowercase letters [a-p] with zero wildcards."
    exit 1
}

$exactOrigin = "chrome-extension://$ExtensionId/"

# 3. Resolve Target Manifest Directory
if ($ManifestDir) {
    $targetManifestDir = $ManifestDir
} else {
    $targetManifestDir = Join-Path $env:LOCALAPPDATA "EdgeMind"
}

if (-not (Test-Path $targetManifestDir)) {
    New-Item -Path $targetManifestDir -ItemType Directory -Force | Out-Null
}

$installedManifestPath = Join-Path $targetManifestDir "com.edgemind.native_host.json"

# 4. Generate Valid JSON Structure (Clean serialization via ConvertTo-Json)
$manifestObj = [ordered]@{
    name            = "com.edgemind.native_host"
    description     = "EdgeMind Native Messaging Host for Backend Management"
    path            = $canonicalExePath
    type            = "stdio"
    allowed_origins = @($exactOrigin)
}

$manifestJson = $manifestObj | ConvertTo-Json -Depth 5
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($installedManifestPath, $manifestJson, $utf8NoBom)

if (-not $Quiet) {
    Write-Host "[SUCCESS] Written native messaging manifest to: $installedManifestPath" -ForegroundColor Green
}

# 5. Register in Windows Registry (HKCU) unless -NoRegistry
if (-not $NoRegistry) {
    if (-not (Test-Path $RegistryKey)) {
        New-Item -Path $RegistryKey -Force | Out-Null
    }
    Set-ItemProperty -Path $RegistryKey -Name "(Default)" -Value $installedManifestPath
    if (-not $Quiet) {
        Write-Host "[SUCCESS] Registered in Registry:" -ForegroundColor Green
        Write-Host "  Key   : $RegistryKey" -ForegroundColor Green
        Write-Host "  Value : $installedManifestPath" -ForegroundColor Green
    }
}

# 6. Diagnostic Self-Check (Skipped if -Quiet or custom paths)
if (-not $Quiet) {
    Write-Host "`nRunning native host self-check..." -ForegroundColor Cyan
    $selfCheck = Start-Process -FilePath $canonicalExePath -ArgumentList "--check" -Wait -NoNewWindow -PassThru
    if ($selfCheck.ExitCode -eq 0) {
        Write-Host "[VERIFIED] Native messaging host self-check passed." -ForegroundColor Green
    } else {
        Write-Host "[WARN] Self-check returned exit code $($selfCheck.ExitCode)." -ForegroundColor Yellow
    }
}

if (-not $Quiet) {
    Write-Host "`n====================================================" -ForegroundColor DarkCyan
    Write-Host " EdgeMind Native Messaging Installation Complete!" -ForegroundColor Green
    Write-Host "====================================================" -ForegroundColor DarkCyan
}
