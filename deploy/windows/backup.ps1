# Back up everything that would hurt to lose: the database, and the CV.
#
# The CV is exported separately even though it lives in Postgres. A pg_dump is
# restorable only by a compatible Postgres; the JSON is readable by a human on
# any machine, and the Master CV is the one artefact that cannot be regenerated
# by crawling again. Two formats, two failure modes.
#
# Registered by install-tasks.ps1. Safe to run by hand at any time.

[CmdletBinding()]
param(
    [string]$RepoDir   = '',
    [string]$BackupDir = "$env:USERPROFILE\JobPilotBackups",
    [int]   $KeepDays  = 30
)

$ErrorActionPreference = 'Stop'

# Resolved here rather than as a param default: $PSScriptRoot is empty inside a
# param block when the script is invoked by a relative path, and the default
# then silently resolves against the current directory instead. That failed as
# "no .env at D:\.env" -- a message about the wrong directory entirely.
if (-not $RepoDir) {
    $here    = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepoDir = (Resolve-Path (Join-Path $here '..\..')).Path
}
Set-Location $RepoDir

# --- DATABASE_URL out of .env -------------------------------------------------
# Read rather than required in the environment: the scheduled task runs without
# the shell profile that would normally export it.
$envFile = Join-Path $RepoDir '.env'
if (-not (Test-Path $envFile)) { throw "no .env at $envFile" }

$dbUrl = (Select-String -Path $envFile -Pattern '^DATABASE_URL=(.+)$').Matches.Groups[1].Value.Trim()
if (-not $dbUrl) { throw "DATABASE_URL not found in .env" }

# pg_dump speaks libpq URLs, not SQLAlchemy ones -- the +psycopg driver suffix
# makes it fail with "invalid URI scheme".
$pgUrl = $dbUrl -replace '^postgresql\+psycopg:', 'postgresql:'

# --- locate pg_dump -----------------------------------------------------------
# Not on PATH by default on Windows, and the version directory changes with
# every major release, so look rather than assume.
$pgDump = (Get-Command pg_dump.exe -ErrorAction SilentlyContinue).Source
if (-not $pgDump) {
    $pgDump = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\pg_dump.exe' -ErrorAction SilentlyContinue |
              Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $pgDump) { throw "pg_dump.exe not found -- is PostgreSQL installed?" }

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$dump  = Join-Path $BackupDir "jobpilot-$stamp.dump"
$cvOut = Join-Path $BackupDir "cv-$stamp.json"

# -Fc: compressed, and restorable table-by-table with pg_restore rather than
# all-or-nothing.
& $pgDump -Fc $pgUrl -f $dump
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed ($LASTEXITCODE)" }

& python -m jobpilot.cli cv export $cvOut
if ($LASTEXITCODE -ne 0) { throw "cv export failed ($LASTEXITCODE)" }

# --- verify, don't assume -----------------------------------------------------
# A backup job that reports success while writing a zero-byte file is worse than
# no backup job, because it stops you checking.
foreach ($f in @($dump, $cvOut)) {
    if (-not (Test-Path $f) -or (Get-Item $f).Length -eq 0) {
        throw "backup produced an empty file: $f"
    }
}

Get-ChildItem $BackupDir -Include 'jobpilot-*.dump','cv-*.json' -Recurse |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
    Remove-Item -Force

$size = [math]::Round((Get-Item $dump).Length / 1MB, 2)
Write-Output "backed up to $BackupDir  (jobpilot-$stamp.dump ${size}MB, cv-$stamp.json)"
