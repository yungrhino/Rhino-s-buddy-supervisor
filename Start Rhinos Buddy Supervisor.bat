@echo off
rem Starts Rhino's Buddy Supervisor straight from the source code (no .exe needed). Requires Python.
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  echo Python not found. Install it from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
start "" pythonw run_app.py
