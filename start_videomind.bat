@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_videomind.ps1"
set "VIDEOMIND_EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%VIDEOMIND_EXIT_CODE%"=="0" (
  echo VideoMind-Agent launcher exited with an error.
)
echo Press any key to close this launcher window.
pause >nul
exit /b %VIDEOMIND_EXIT_CODE%
