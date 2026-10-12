@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (py -3 "check_package.py") else (python "check_package.py")
pause
