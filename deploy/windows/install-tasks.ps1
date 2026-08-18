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
    [int]     $Port       = 8000,
    [string]  $BackupDir  = "$env:USERPROFILE\JobPilotBackups"
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

# The interpreter that has jobpilot installed, not whatever python the task
# scheduler would find first.
$python = (Get-Command python.exe -ErrorAction Stop).Source

Write-Output "repo:    $RepoDir"
Write-Output "python:  $python"

function Register-JobPilotTask {
    param($Name, $Action, $Triggers, $Settings, $Description)
    # Unregister first: Register-ScheduledTask -Force still fails on some
    # settings changes, and a half-updated task is worse than a missing one.
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Triggers `
        -Settings $Settings -Description $Description | Out-Null
    Write-Output "  registered: $Name"
}

# --------------------------------------------------------------------------- #
# 1. The API + dashboard
# --------------------------------------------------------------------------- #
# Launched through run-api.cmd rather than python directly, for two reasons the
# first attempt at this proved the hard way: the task died with a bare "0x1" and
# no log to say why, and the cause turned out to be a stripped environment where
# `import asyncio` failed in Winsock for want of %SystemRoot%. The wrapper fixes
# both. hidden.vbs then runs it without leaving a console window on screen for
# the rest of the session.
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
    -Action (New-ScheduledTaskAction -Execute $python -Argument '-m jobpilot.cli crawl' -WorkingDirectory $RepoDir) `
    -Triggers $crawlTriggers `
    -Settings $crawlSettings `
    -Description "Crawl the enabled job boards ($($CrawlTimes -join ', ')). Runs here, not on a server, so it uses a Vietnamese residential IP."

# --------------------------------------------------------------------------- #
# 3. Backup
# --------------------------------------------------------------------------- #
$backupAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptDir\backup.ps1`" -BackupDir `"$BackupDir`"" `
    -WorkingDirectory $RepoDir

Register-JobPilotTask -Name 'JobPilot Backup' `
    -Action $backupAction `
    -Triggers (New-ScheduledTaskTrigger -Daily -At $BackupTime) `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
                                            -ExecutionTimeLimit (New-TimeSpan -Minutes 30)) `
    -Description "pg_dump + CV export into $BackupDir"

Write-Output ''
Write-Output 'Done. Check with:  Get-ScheduledTask JobPilot*'
Write-Output "Backups land in:   $BackupDir"
Write-Output ''
Write-Output 'The data now lives on exactly one laptop, so verify a restore at least once:'
Write-Output '  pg_restore --list <a .dump file>     # should list tables, not error'
