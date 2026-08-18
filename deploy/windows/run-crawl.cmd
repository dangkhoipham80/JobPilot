@echo off
REM Crawl for the "JobPilot Crawl" scheduled task.
REM
REM A wrapper for the same two reasons as run-api.cmd -- a log to look at when
REM it goes wrong, and an environment cmd.exe has normalised -- plus a third:
REM all three tasks now reach python the same way, through PATH. Registering one
REM task with a full interpreter path and the others with a bare `python` is how
REM a machine ends up crawling with one interpreter and serving with another,
REM which shows up as a package that is installed and also missing.

setlocal

if "%SystemRoot%"=="" set "SystemRoot=C:\Windows"
if "%windir%"==""     set "windir=%SystemRoot%"

cd /d "%~dp0..\.."
if not exist logs mkdir logs

echo. >> logs\crawl.log
echo ============ started %DATE% %TIME% ============ >> logs\crawl.log

python -m jobpilot.cli crawl >> logs\crawl.log 2>&1
set RC=%ERRORLEVEL%

echo ============ exited %DATE% %TIME% rc=%RC% ============ >> logs\crawl.log
exit /b %RC%
