@echo off
REM Backup for the "JobPilot Backup" scheduled task.
REM
REM A thin wrapper on purpose. All the actual rules -- pg_dump, the CV export,
REM the non-empty check, retention, the rclone mirror -- live in
REM jobpilot/backup.py, because the CLI, this task and the dashboard button must
REM apply the same ones. When copies of backup logic drift, what drifts first is
REM the verification, and the day you notice is the day you needed the backup.
REM
REM Same two reasons as run-api.cmd for being a .cmd at all: it writes a log, and
REM cmd.exe normalises an environment that Task Scheduler can otherwise hand over
REM without %SystemRoot%, which breaks Python before it reaches our code.

setlocal

if "%SystemRoot%"=="" set "SystemRoot=C:\Windows"
if "%windir%"==""     set "windir=%SystemRoot%"

cd /d "%~dp0..\.."
if not exist logs mkdir logs

echo. >> logs\backup.log
echo ============ started %DATE% %TIME% ============ >> logs\backup.log

python -m jobpilot.cli backup --verbose >> logs\backup.log 2>&1
set RC=%ERRORLEVEL%

echo ============ exited %DATE% %TIME% rc=%RC% ============ >> logs\backup.log
exit /b %RC%
