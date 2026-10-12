@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist "ChatGPT_Local_Archive\index.html" (
  echo ERROR: First run 01_BUILD_ARCHIVE.bat.
  pause
  exit /b 1
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "serve_archive.py" "ChatGPT_Local_Archive"
) else (
  where python >nul 2>nul
  if errorlevel 1 goto missing
  python "serve_archive.py" "ChatGPT_Local_Archive"
)
if errorlevel 1 pause
exit /b %ERRORLEVEL%
:missing
echo ERROR: Python 3.9+ is required.
pause
exit /b 1
