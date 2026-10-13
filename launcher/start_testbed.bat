@echo off
rem KIIS testbed one-click launcher (double-click). See start_testbed.ps1 for options.
rem pwsh (PowerShell 7) if installed, otherwise Windows PowerShell - never both.
where pwsh >nul 2>nul
if %errorlevel%==0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_testbed.ps1" %*
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_testbed.ps1" %*
)
