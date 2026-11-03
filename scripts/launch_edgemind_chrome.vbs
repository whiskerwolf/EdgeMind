' ==============================================================================
' EdgeMind - Silent Chrome Profile 7 Launcher
' Executes launch_edgemind_chrome.ps1 with SW_HIDE (0) so no terminal window
' appears when clicking the desktop shortcut.
' ==============================================================================
Option Explicit

Dim fso, scriptDir, psScript, wshShell, cmd

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
psScript = fso.BuildPath(scriptDir, "launch_edgemind_chrome.ps1")

If Not fso.FileExists(psScript) Then
    MsgBox "EdgeMind launcher script not found: " & psScript, vbCritical, "EdgeMind Error"
    WScript.Quit 1
End If

Set wshShell = CreateObject("WScript.Shell")
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & psScript & """ -Silent"
wshShell.Run cmd, 0, False

