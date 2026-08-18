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

' 0 = hidden window, False = do not wait. Not waiting matters: the task should
' register as started rather than sitting "running" for the process's lifetime.
shell.Run cmd, 0, False
