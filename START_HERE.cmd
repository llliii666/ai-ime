@echo off
setlocal
chcp 65001 >nul
title AI IME Setup
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1" %*
set EXIT_CODE=%ERRORLEVEL%

echo.
if "%EXIT_CODE%"=="0" (
  echo AI IME setup finished. You can close this window.
) else (
  echo AI IME setup failed. Please read the message above.
)
echo.
pause
exit /b %EXIT_CODE%
