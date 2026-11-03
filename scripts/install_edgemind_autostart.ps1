<#
.SYNOPSIS
    Installs automatic, invisible startup for the EdgeMind FastAPI backend at Windows login.

.DESCRIPTION
    - Registers a Windows Task Scheduler task named 'EdgeMindBackendAutostart'.
    - Configures trigger to run when the current Windows user logs on.
    - Executes completely silently via VBScript/PowerShell without displaying any terminal window.
    - Operates strictly with standard user privileges (no administrator rights required).
    - Enforces working directory to project root and binds to 127.0.0.1:8000.
    - Disables AC power requirements so the API starts on battery or network disconnect.
    - Prevents task timeout kills by setting unlimited execution time.
    - Automatically checks and creates the desktop shortcut for Chrome Profile 7 launcher.
#>

[CmdletBinding()]
param (
    [string]$TaskName = "EdgeMindBackendAutostart",
    [switch]$NoShortcut,
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"

# 1. Resolve paths
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path
$SilentVbs   = Join-Path $ProjectRoot "scripts\start_edgemind_silent.vbs"
$StartPs1    = Join-Path $ProjectRoot "scripts\start_edgemind_api.ps1"
$PythonExe   = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogsDir     = Join-Path $ProjectRoot "logs"

Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host " EdgeMind Autostart Installer (Windows Task Scheduler)" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor DarkCyan
Write-Host "Project Root : $ProjectRoot"
Write-Host "Task Name    : $TaskName"
Write-Host "User Session : $env:USERNAME"

# 2. Validation
if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Virtual environment Python not found at: $PythonExe" -ForegroundColor Red
    Write-Host "Please ensure the .venv environment is created and configured." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $StartPs1)) {
    Write-Host "[ERROR] Backend startup script not found at: $StartPs1" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $SilentVbs)) {
    Write-Host "[ERROR] Silent VBScript wrapper not found at: $SilentVbs" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
}

# 3. Register Task via Schedule.Service COM (No Admin Privileges Required)
try {
    Write-Host "Connecting to Windows Task Scheduler service..." -ForegroundColor Cyan
    $service = New-Object -ComObject("Schedule.Service")
    $service.Connect()
    $rootFolder = $service.GetFolder("\")

    # Check if task already exists
    $existingTask = $null
    try {
        $existingTask = $rootFolder.GetTask($TaskName)
    } catch {}

    if ($existingTask) {
        Write-Host "Existing task '$TaskName' detected. Updating configuration..." -ForegroundColor Yellow
    }

    # Create new task definition
    # 0 = TASK_DEFINITION
    $taskDef = $service.NewTask(0)

    # Registration Information
    $taskDef.RegistrationInfo.Description = "EdgeMind Adaptive Test Intelligence - Automatic invisible API startup on user logon."
    $taskDef.RegistrationInfo.Author = $env:USERNAME

    # Trigger: At User Logon
    # 9 = TASK_TRIGGER_LOGON
    $trigger = $taskDef.Triggers.Create(9)
    $trigger.UserId = $env:USERNAME
    $trigger.Enabled = $true

    # Action: Execute start_edgemind_silent.vbs via wscript.exe
    # 0 = TASK_ACTION_EXEC
    $action = $taskDef.Actions.Create(0)
    $action.Path = "wscript.exe"
    $action.Arguments = "`"$SilentVbs`""
    $action.WorkingDirectory = $ProjectRoot

    # Task Settings: Battery and Network resilience
    $settings = $taskDef.Settings
    $settings.AllowDemandStart = $true
    $settings.DisallowStartIfOnBatteries = $false
    $settings.StopIfGoingOnBatteries = $false
    $settings.StartWhenAvailable = $true
    $settings.RunOnlyIfNetworkAvailable = $false
    $settings.ExecutionTimeLimit = "PT0S" # No time limit (service stays alive)
    $settings.Priority = 7 # Normal priority

    # Register Task Definition under current user interactive token
    # 6 = TASK_CREATE_OR_UPDATE
    # 3 = TASK_LOGON_INTERACTIVE_TOKEN
    $registeredTask = $rootFolder.RegisterTaskDefinition(
        $TaskName,
        $taskDef,
        6,     # TASK_CREATE_OR_UPDATE
        $null, # User (null uses interactive session)
        $null, # Password
        3      # TASK_LOGON_INTERACTIVE_TOKEN
    )

    Write-Host "[SUCCESS] Windows Scheduled Task '$TaskName' registered successfully!" -ForegroundColor Green
    Write-Host "  Trigger     : At logon of user '$env:USERNAME'" -ForegroundColor Green
    Write-Host "  Action      : wscript.exe `"$SilentVbs`"" -ForegroundColor Green
    Write-Host "  Working Dir : $ProjectRoot" -ForegroundColor Green
    Write-Host "  Mode        : 100% Silent (Zero terminal window)" -ForegroundColor Green

} catch {
    Write-Host "[ERROR] Failed to register Scheduled Task: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 4. Create Desktop Shortcut unless -NoShortcut is specified
if (-not $NoShortcut) {
    $shortcutScript = Join-Path $ScriptDir "create_edgemind_desktop_shortcut.ps1"
    if (Test-Path $shortcutScript) {
        Write-Host "`nCreating desktop shortcut..." -ForegroundColor Cyan
        & $shortcutScript
    }
}

# 5. Optionally run now to verify
if ($RunNow) {
    Write-Host "`nTesting task execution now..." -ForegroundColor Cyan
    try {
        $registeredTask.Run($null) | Out-Null
        Start-Sleep -Seconds 2

        $healthCheck = Join-Path $ScriptDir "check_edgemind_api.ps1"
        if (Test-Path $healthCheck) {
            & $healthCheck
        }
    } catch {
        Write-Host "[WARNING] Could not trigger task run: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Write-Host "`n====================================================" -ForegroundColor DarkCyan
Write-Host " Installation Complete!" -ForegroundColor Green
Write-Host " The EdgeMind API will now start automatically and invisibly every time you log in." -ForegroundColor Cyan
Write-Host " To uninstall autostart, run: .\scripts\uninstall_edgemind_autostart.ps1" -ForegroundColor DarkGray
Write-Host "====================================================" -ForegroundColor DarkCyan
exit 0

