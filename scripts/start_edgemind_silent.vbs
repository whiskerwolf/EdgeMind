' ==============================================================================
' EdgeMind - Silent Background API Starter
' Executes start_edgemind_api.ps1 with window style SW_HIDE (0) so no terminal
' window appears during startup or login.
' ==============================================================================
Option Explicit

Dim fso, scriptDir, projectRoot, psScript, wshShell, cmd

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
psScript = fso.BuildPath(scriptDir, "start_edgemind_api.ps1")

If Not fso.FileExists(psScript) Then
    MsgBox "EdgeMind startup script not found: " & psScript, vbCritical, "EdgeMind Error"
    WScript.Quit 1
End If

Set wshShell = CreateObject("WScript.Shell")
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & psScript & """"
wshShell.Run cmd, 0, False

