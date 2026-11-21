@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Rhino's Buddy Supervisor - atualizar / desinstalar
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"
set "DATADIR=%APPDATA%\RhinosBuddySupervisor"
set "OLDDATA=%APPDATA%\Subscreen"
set "PORT=8765"
set "PACKAGED="
if exist "%APPDIR%\RhinosBuddySupervisor.exe" set "PACKAGED=1"
cd /d "%TEMP%"
echo.
echo === Rhino's Buddy Supervisor: atualizar / desinstalar ===
echo.
echo Pasta do programa : %APPDIR%
echo Seus dados        : %DATADIR%
echo                     (layout, imagens e configuracoes: ficam FORA da pasta do programa)
echo.
echo   [1] Atualizar    - fecha o programa, remove o inicio automatico e apaga a pasta
echo                      do programa. Seus dados sao MANTIDOS. Depois e so extrair o zip novo.
echo   [2] Desinstalar  - o mesmo, e pergunta se voce quer apagar tambem os seus dados.
echo   [3] Cancelar
echo.
choice /C 123 /N /M "Escolha 1, 2 ou 3: "
if errorlevel 3 goto cancelar
set "MODO=atualizar"
if errorlevel 2 set "MODO=desinstalar"

echo.
echo [1/4] Fechando o programa...
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Method Post -Uri 'http://127.0.0.1:%PORT%/api/quit' -Headers @{'X-Rhinos-Buddy'='1'} -ContentType 'application/json' -Body '{}' -TimeoutSec 4 | Out-Null } catch {}" >nul 2>nul
timeout /t 2 /nobreak >nul
taskkill /F /IM RhinosBuddySupervisor.exe >nul 2>nul

echo [2/4] Removendo o inicio automatico com o Windows...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v RhinosBuddySupervisor /f >nul 2>nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Subscreen /f >nul 2>nul

if "%MODO%"=="atualizar" goto pasta
echo.
echo [3/4] Dados pessoais
choice /C SN /M "Apagar tambem os seus dados (layout, imagens e configuracoes)"
if errorlevel 2 goto manterdados
rmdir /s /q "%DATADIR%" >nul 2>nul
if exist "%OLDDATA%" rmdir /s /q "%OLDDATA%" >nul 2>nul
echo Dados apagados.
goto pasta
:manterdados
echo Dados mantidos em %DATADIR%

:pasta
echo.
echo [4/4] Pasta do programa
if not defined PACKAGED goto semexe
choice /C SN /M "Apagar a pasta do programa (%APPDIR%)"
if errorlevel 2 goto fim
set "RB_APPDIR=%APPDIR%"
start "" powershell -NoProfile -WindowStyle Hidden -Command "if (Test-Path -LiteralPath (Join-Path $env:RB_APPDIR 'RhinosBuddySupervisor.exe')) { for ($i = 0; $i -lt 40 -and (Test-Path -LiteralPath $env:RB_APPDIR); $i++) { Start-Sleep -Seconds 2; Remove-Item -LiteralPath $env:RB_APPDIR -Recurse -Force -ErrorAction SilentlyContinue } }"
echo A pasta sera apagada assim que esta janela for fechada.
goto fim
:semexe
echo Aqui nao ha o RhinosBuddySupervisor.exe (esta pasta e o codigo-fonte), entao ela NAO sera apagada.

:fim
echo.
echo Concluido.
if "%MODO%"=="atualizar" echo Para instalar a versao nova, extraia o zip novo onde quiser e abra o RhinosBuddySupervisor.exe. Seus dados continuam la.
pause
exit /b 0

:cancelar
echo Nada foi alterado.
pause
exit /b 0
