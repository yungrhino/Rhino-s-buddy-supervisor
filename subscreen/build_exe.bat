@echo off
setlocal
cd /d "%~dp0"
title Subscreen - gerar executavel
echo.
echo === Subscreen: gerando o executavel (Subscreen.exe) ===
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale em python.org e marque "Add python.exe to PATH".
  pause
  exit /b 1
)
echo [1/3] Instalando dependencias...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto erro
echo.
echo [2/3] Instalando recursos do modulo Musica (opcional)...
python -m pip install -r requirements-musica.txt
if errorlevel 1 echo Aviso: o modulo Musica ficara sem audio/titulo; o resto funciona normalmente.
echo.
echo [3/3] Empacotando (leva 1 a 3 minutos)...
python -m PyInstaller --noconfirm --clean --noconsole --name Subscreen --icon subscreen.ico --add-data "subscreen\web;subscreen\web" --collect-submodules serial --collect-all soundcard --collect-submodules winrt run_app.py
if errorlevel 1 goto erro
echo.
echo ============================================================
echo  Pronto!  Executavel em:  %CD%\dist\Subscreen\Subscreen.exe
echo  (mantenha a pasta "Subscreen" inteira; pode mover para onde quiser)
echo ============================================================
echo.
choice /C SN /M "Criar um atalho na Area de Trabalho"
if errorlevel 2 goto fim
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath(Desktop)+\Subscreen.lnk);$s.TargetPath=%CD%\dist\Subscreen\Subscreen.exe;$s.WorkingDirectory=%CD%\dist\Subscreen;$s.Save()"
echo Atalho criado.
:fim
pause
exit /b 0
:erro
echo.
echo Algo deu errado. Copie as mensagens acima e envie para obter ajuda.
pause
exit /b 1
