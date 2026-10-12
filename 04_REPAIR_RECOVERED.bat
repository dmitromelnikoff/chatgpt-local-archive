@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (py -3 "repair_recovered_chats.py" "ChatGPT_Local_Archive") else (python "repair_recovered_chats.py" "ChatGPT_Local_Archive")
pause
