# Register the three scheduled tasks that make this a service rather than a
# terminal somebody has to remember to keep open.
#
#   JobPilot API     -- at logon, stays up, restarts if it dies
#   JobPilot Crawl   -- twice a day, catches up if the machine was off
#   JobPilot Backup  -- nightly
#
# MUST be run from an elevated PowerShell: registering a task in the root task
# folder needs Administrator, and without it Register-ScheduledTask fails with a
# bare "Access is denied" that says nothing about elevation.
#
# The tasks themselves then run as the ordinary logged-in user, which is what we
# want -- the API has no business holding admin rights for weeks at a time.
#
# Re-running is safe: existing tasks are replaced.
#
#     powershell -ExecutionPolicy Bypass -File deploy\windows\install-tasks.ps1

[CmdletBinding()]
param(
    [string]  $RepoDir    = '',
    [string[]]$CrawlTimes = @('08:30', '18:30'),
    [string]  $BackupTime = '03:00',
    [int]     $Port       = 8000
)

$ErrorActionPreference = 'Stop'

# Check up front rather than letting Register-ScheduledTask fail three commands
# later with "Access is denied", which names neither the cause nor the fix.
$admin = ([Security.Principal.WindowsPrincipal] `
          [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    throw "This needs an elevated PowerShell. Right-click PowerShell -> Run as Administrator, then re-run."
}

# See backup.ps1: $PSScriptRoot is empty in a param default when the script is
# invoked by a relative path, so this is resolved in the body.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoDir) { $RepoDir = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path }
$RepoDir = (Resolve-Path $RepoDir).Path

# Reported, not used as the task's Execute. All three tasks go through a .cmd
# wrapper that calls a bare `python`, so they resolve the interpreter the same
# way at run time. Registering one task with a full path and the others with
# PATH is how a machine ends up crawling with one interpreter and serving with
# another -- which surfaces as a package that is both installed and missing.
$python = (Get-Command python.exe -ErrorAction Stop).Source

Write-Output "repo:    $RepoDir"
Write-Output "python:  $python  (tasks resolve it via PATH at run time)"

# Interactive, deliberately, after trying the alternative.
#
# S4U ("Service For User") looked better -- background, no window, no stored
# password -- and made the server *unmanageable*: it runs in a different logon
# session, so from an ordinary shell `taskkill` answers "Access is denied" and
# Get-CimInstance returns a blank CommandLine, which makes process lookups
# quietly match nothing. Restarting the API would have needed Administrator
# every time.
#
# Interactive keeps the server in this user's session, where restart-api.ps1 can
# stop it by port without elevation. hidden.vbs supplies the missing piece --
# no console window -- and waits for the command, so the task stays Running for
# the server's lifetime and RestartCount still fires if it crashes.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

function Register-JobPilotTask {
    param($Name, $Action, $Triggers, $Settings, $Description)
    # Unregister first: Register-ScheduledTask -Force still fails on some
    # settings changes, and a half-updated task is worse than a missing one.
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Triggers `
        -Settings $Settings -Principal $principal -Description $Description | Out-Null
    Write-Output "  registered: $Name"
}

# --------------------------------------------------------------------------- #
# 1. The API + dashboard
# --------------------------------------------------------------------------- #
# Launched through run-api.cmd rather than python directly, for two reasons the
# first attempt at this proved the hard way: the task died with a bare "0x1" and
# no log to say why, and the cause turned out to be a stripped environment where
# `import asyncio` failed in Winsock for want of %SystemRoot%. The wrapper fixes
# both. hidden.vbs keeps the console window off the screen; it waits for the
# command, so this task stays Running rather than reporting success instantly.
#
# Stopping it is deploy\windows\restart-api.ps1, NOT Stop-ScheduledTask: the
# scheduler kills the shim and leaves the server orphaned holding the port,
# which makes the next start fail to bind and look like a successful restart.
$apiAction = New-ScheduledTaskAction -Execute 'wscript.exe' `
    -Argument "`"$ScriptDir\hidden.vbs`" `"$ScriptDir\run-api.cmd`" $Port" `
    -WorkingDirectory $RepoDir

$apiSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)   # 0 = never kill it

Register-JobPilotTask -Name 'JobPilot API' `
    -Action $apiAction `
    -Triggers (New-ScheduledTaskTrigger -AtLogOn) `
    -Settings $apiSettings `
    -Description 'JobPilot dashboard + API on 127.0.0.1. Reached from other devices only via tailscale serve.'

# --------------------------------------------------------------------------- #
# 2. Crawl
# --------------------------------------------------------------------------- #
# StartWhenAvailable is the point of running this here rather than on a server:
# a laptop is closed sometimes, and a crawl window missed at 08:30 should happen
# when the machine comes back, not be skipped in silence.
$crawlSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 45)

$crawlTriggers = $CrawlTimes | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }

Register-JobPilotTask -Name 'JobPilot Crawl' `
    -Action (New-ScheduledTaskAction -Execute 'wscript.exe' `
                -Argument "`"$ScriptDir\hidden.vbs`" `"$ScriptDir\run-crawl.cmd`"" `
                -WorkingDirectory $RepoDir) `
    -Triggers $crawlTriggers `
    -Settings $crawlSettings `
    -Description "Crawl the enabled job boards ($($CrawlTimes -join ', ')). Runs here, not on a server, so it uses a Vietnamese residential IP."

# --------------------------------------------------------------------------- #
# 3. Backup
# --------------------------------------------------------------------------- #
# Destination, retention and the rclone remote all come from `backup:` in
# config.yaml / config.local.yaml, so the scheduled task, the CLI and the
# dashboard button cannot be pointed at three different places by three
# different callers.
$backupAction = New-ScheduledTaskAction -Execute 'wscript.exe' `
    -Argument "`"$ScriptDir\hidden.vbs`" `"$ScriptDir\run-backup.cmd`"" `
    -WorkingDirectory $RepoDir

Register-JobPilotTask -Name 'JobPilot Backup' `
    -Action $backupAction `
    -Triggers (New-ScheduledTaskTrigger -Daily -At $BackupTime) `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
                                            -ExecutionTimeLimit (New-TimeSpan -Minutes 30)) `
    -Description 'pg_dump + CV export. Destination and retention come from `backup:` in config.yaml.'

Write-Output ''
Write-Output 'Done. Check with:  Get-ScheduledTask JobPilot*'
Write-Output 'Backups land where `backup.dir` in config.yaml says.'
Write-Output ''
Write-Output 'The data now lives on exactly one laptop, so verify a restore at least once:'
Write-Output '  pg_restore --list <a .dump file>     # should list tables, not error'
