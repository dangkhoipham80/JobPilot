# Restart the API properly.
#
# Use this instead of Stop-ScheduledTask + Start-ScheduledTask, which does not
# work here and fails in the most misleading way possible.
#
# Task Scheduler terminates the task's own process -- cmd.exe -- but not the
# python it is waiting on. The server is orphaned rather than stopped: the task
# reports Ready, the port stays held, and the Start that follows launches a new
# instance that cannot bind and exits immediately. Everything looks like it
# restarted. Nothing did.
#
# That cost two rounds of "verifying" a deploy against the previous build. So
# this stops the server by whoever actually holds the port, waits for the port
# to be free, and only then starts the task.
#
#     powershell -ExecutionPolicy Bypass -File deploy\windows\restart-api.ps1

[CmdletBinding()]
param(
    [int]$Port    = 8000,
    [int]$WaitSec = 30,
    [switch]$StopOnly
)

$ErrorActionPreference = 'Stop'

function Get-PortOwner {
    param([int]$Port)
    # By port, not by process name or command line: under an S4U task the
    # server runs in another logon session, where a non-elevated
    # Get-CimInstance returns a *blank* CommandLine. Filtering on it silently
    # matches nothing and reports "no server running" while it serves happily.
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
}

$owners = @(Get-PortOwner -Port $Port)
if ($owners.Count -eq 0) {
    Write-Output "nothing listening on $Port"
} else {
    foreach ($pid_ in $owners) {
        Write-Output "stopping PID $pid_ (holds port $Port)"
        Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
    }
}

# Stop the task too, so the scheduler's own view matches reality.
Stop-ScheduledTask -TaskName 'JobPilot API' -ErrorAction SilentlyContinue

# Wait for the port rather than sleeping a guessed number of seconds: a socket
# in the middle of closing still refuses a bind, and the next start would fail
# for a reason that has nothing to do with the code being deployed.
for ($i = 0; $i -lt $WaitSec; $i++) {
    if (@(Get-PortOwner -Port $Port).Count -eq 0) { break }
    Start-Sleep -Seconds 1
}
if (@(Get-PortOwner -Port $Port).Count -gt 0) {
    throw "port $Port is still held after ${WaitSec}s -- not starting a second server on top of it"
}

if ($StopOnly) {
    Write-Output "stopped."
    return
}

Start-ScheduledTask -TaskName 'JobPilot API'

# Confirm it answers, rather than reporting success because a command returned.
for ($i = 1; $i -le 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2
        Write-Output "up after ${i}s: version $($r.version)"
        return
    } catch { }
}

throw "the API did not answer /health within 30s -- see logs\api.log"
