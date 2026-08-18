' Run a command with no console window.
'
' Task Scheduler has no "hide the window" option -- its -Hidden setting hides the
' *task* in the UI, not the window the task opens. Without this shim a console
' sits on screen for as long as the API runs, which for an always-on service is
' the rest of the session, and closing it by reflex kills the dashboard.
'
'   wscript.exe hidden.vbs "C:\path\to\run-api.cmd" [args...]

Option Explicit

Dim shell, cmd, i
Set shell = CreateObject("WScript.Shell")

If WScript.Arguments.Count = 0 Then
    WScript.Echo "usage: wscript hidden.vbs <command> [args...]"
    WScript.Quit 1
End If

' Quote every argument: the paths involved contain spaces often enough
' (Program Files, user profiles) that an unquoted one is a question of when.
cmd = """" & WScript.Arguments(0) & """"
For i = 1 To WScript.Arguments.Count - 1
    cmd = cmd & " """ & WScript.Arguments(i) & """"
Next

' 0 = hidden window, True = WAIT for the command and pass its exit code back.
'
' Waiting is the whole point, and not waiting was a real bug: with False the
' task finished the instant it launched, so Task Scheduler reported success
' immediately and lost track of the process. Three things silently stopped
' working -- RestartCount never fired because the task never failed (so a
' crashed API stayed dead), Stop-ScheduledTask had nothing to stop, and the
' nightly backup reported 0x0 even when it failed.
'
' The window stays hidden either way; hiding and waiting are independent.
WScript.Quit shell.Run(cmd, 0, True)
