@echo off
setlocal
cd /d "%~dp0"
title Rhino's Buddy Supervisor - gerar executavel
echo.
echo === Rhino's Buddy Supervisor: gerando o executavel (RhinosBuddySupervisor.exe) ===
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale em python.org e marque "Add python.exe to PATH".
  pause
  exit /b 1
)
echo [1/4] Instalando dependencias...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto erro
echo.
echo [2/4] Instalando recursos do modulo Musica (opcional)...
python -m pip install -r requirements-extras.txt
if errorlevel 1 echo Aviso: o modulo Musica ficara sem audio/titulo; o resto funciona normalmente.
echo.
echo [3/4] Empacotando (leva 1 a 3 minutos)...
python -m PyInstaller --noconfirm --clean --noconsole --name RhinosBuddySupervisor --icon rhinos_buddy.ico --add-data "rhinos_buddy\web;rhinos_buddy\web" --collect-submodules serial --collect-all soundcard --collect-submodules winrt run_app.py
if errorlevel 1 goto erro
echo.
echo [4/4] Reunindo licencas, README e desinstalador (devem acompanhar o programa)...
python tools\collect_licenses.py dist\RhinosBuddySupervisor
if errorlevel 1 goto erro
copy /Y "Desinstalar Rhinos Buddy Supervisor.bat" "dist\RhinosBuddySupervisor\" >nul
copy /Y README.md "dist\RhinosBuddySupervisor\" >nul
for %%F in (README_v*.md) do copy /Y "%%F" "dist\RhinosBuddySupervisor\" >nul
echo.
echo ============================================================
echo  Pronto!  Executavel em:  %CD%\dist\RhinosBuddySupervisor\RhinosBuddySupervisor.exe
echo  (mantenha a pasta "RhinosBuddySupervisor" inteira; pode mover para onde quiser)
echo ============================================================
echo.
choice /C SN /M "Criar um atalho na Area de Trabalho"
if errorlevel 2 goto fim
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Rhinos Buddy Supervisor.lnk');$s.TargetPath='%CD%\dist\RhinosBuddySupervisor\RhinosBuddySupervisor.exe';$s.WorkingDirectory='%CD%\dist\RhinosBuddySupervisor';$s.Save()"
echo Atalho criado.
:fim
pause
exit /b 0
:erro
echo.
echo Algo deu errado. Copie as mensagens acima e envie para obter ajuda.
pause
exit /b 1
