@echo off
chcp 65001 >nul
title ceramic-agent recorder
cd /d "%~dp0"

echo ============================================
echo   ceramic-agent recorder
echo   Connects to Golem on 127.0.0.1:9876
echo   Records commands + screenshots while you model
echo ============================================
echo   Keep this window open while modeling.
echo   Stop: Ctrl+C or close this window.
echo.

rem 优先用 Rhino 自带的 Python(Rhino 8 的 .rhinocode 目录), 没有则退回 PATH 上的 python
set "PY=%USERPROFILE%\.rhinocode\py39-rh8\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "recorder\autopilot.py" run

echo.
echo Recorder exited.
pause
