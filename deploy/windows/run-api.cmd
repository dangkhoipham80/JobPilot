@echo off
REM Launch the API for the "JobPilot API" scheduled task.
REM
REM Why a wrapper instead of pointing the task straight at python:
REM
REM 1. LOGS. A task that starts python directly and dies leaves nothing behind
REM    but a hex exit code in the Task Scheduler UI. The first failure here was
REM    "0x1" and nothing else, which says only that something went wrong.
REM
REM 2. ENVIRONMENT. Python's asyncio imports _overlapped, which needs Winsock,
REM    which needs %SystemRoot% to locate its provider DLLs. Launched with a
REM    stripped environment it dies at `import asyncio` with
REM    "WinError 10106: The requested service provider could not be loaded" --
REM    an error that names neither Python nor the missing variable. cmd.exe
REM    normalises the environment, and the guard below makes it explicit.

setlocal

if "%SystemRoot%"=="" set "SystemRoot=C:\Windows"
if "%windir%"==""     set "windir=%SystemRoot%"

REM Repo root is two levels up from this file, whatever it is called.
cd /d "%~dp0..\.."
if not exist logs mkdir logs

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8000"

echo. >> logs\api.log
echo ============ started %DATE% %TIME% (port %PORT%) ============ >> logs\api.log

REM --workers 1 is mandatory, not tuning: the task queue is a ThreadPoolExecutor
REM inside this process, so a second worker means a second queue with its own
REM WebSocket manager -- the same job can be tailored twice, and progress from a
REM task on worker A never reaches a dashboard connected to worker B. Both fail
REM silently.
python -m uvicorn jobpilot.api.main:app --host 127.0.0.1 --port %PORT% --workers 1 >> logs\api.log 2>&1

echo ============ exited %DATE% %TIME% rc=%ERRORLEVEL% ============ >> logs\api.log
exit /b %ERRORLEVEL%
