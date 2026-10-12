@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (py -3 "verify_archive_images.py" "ChatGPT_Local_Archive") else (python "verify_archive_images.py" "ChatGPT_Local_Archive")
pause
