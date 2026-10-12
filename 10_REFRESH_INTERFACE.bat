@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "refresh_ui_only.py"
) else (
  where python >nul 2>nul
  if errorlevel 1 goto missing
  python "refresh_ui_only.py"
)
if errorlevel 1 goto fail
echo.
echo ALL INTERFACE FEATURES INSTALLED. Run 02_OPEN_ARCHIVE.bat
pause
exit /b 0
:missing
echo ERROR: Python 3.9+ is required.
:fail
echo.
echo INTERFACE SETUP DID NOT FINISH. See the error above.
pause
exit /b 1
