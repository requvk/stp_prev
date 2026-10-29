@echo off
setlocal
title STEP Preview - Setup
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -Operation Install
set "setupExit=%ERRORLEVEL%"
if not "%setupExit%"=="0" echo ERROR: Setup failed. See the message above. Exit code: %setupExit%
echo.
if /I "%~1"=="--no-pause" goto done
pause
:done
exit /b %setupExit%
