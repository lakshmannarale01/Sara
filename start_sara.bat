@echo off
setlocal
cd /d "%~dp0"
title SARA AI
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if errorlevel 1 ( echo Python is not installed. Install Python 3.11+ and try again. & pause & exit /b 1 )
  py -m venv .venv
)
if not exist ".venv\sara-ready-v2" (
  echo Installing SARA dependencies for the first run...
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 ( echo Dependency installation failed. & pause & exit /b 1 )
  echo Installing Chromium runtime for semantic browser actions...
  .venv\Scripts\python.exe -m playwright install chromium
  if errorlevel 1 ( echo Chromium installation failed. & pause & exit /b 1 )
  type nul > ".venv\sara-ready-v2"
)
.venv\Scripts\python.exe sara_server.py
pause
