@echo off
rem Abre o Rhino's Buddy Supervisor direto do codigo-fonte (sem gerar o .exe). Requer Python instalado.
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale em python.org e marque "Add python.exe to PATH".
  pause
  exit /b 1
)
start "" pythonw run_app.py
