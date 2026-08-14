@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\prepare_competition_demo.ps1"
set "VIDEOMIND_EXIT_CODE=%ERRORLEVEL%"

echo.
echo Press any key to close this window.
pause >nul
exit /b %VIDEOMIND_EXIT_CODE%
