@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Rhino's Buddy Supervisor - update / uninstall
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"
set "DATADIR=%APPDATA%\RhinosBuddySupervisor"
set "OLDDATA=%APPDATA%\Subscreen"
set "PORT=8765"
set "PACKAGED="
if exist "%APPDIR%\RhinosBuddySupervisor.exe" set "PACKAGED=1"
cd /d "%TEMP%"
echo.
echo === Rhino's Buddy Supervisor: update / uninstall ===
echo.
echo Program folder : %APPDIR%
echo Your data      : %DATADIR%
echo                     (layout, images and settings: kept OUTSIDE the program folder)
echo.
echo   [1] Update    - closes the program, removes autostart and deletes the program
echo                  folder. Your data is KEPT. Then just extract the new zip.
echo   [2] Uninstall - the same, and asks whether to delete your data too.
echo   [3] Cancel
echo.
choice /C 123 /N /M "Choose 1, 2 or 3: "
if errorlevel 3 goto cancel
set "MODE=update"
if errorlevel 2 set "MODE=uninstall"

echo.
echo [1/4] Closing the program...
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Method Post -Uri 'http://127.0.0.1:%PORT%/api/quit' -Headers @{'X-Rhinos-Buddy'='1'} -ContentType 'application/json' -Body '{}' -TimeoutSec 4 | Out-Null } catch {}" >nul 2>nul
timeout /t 2 /nobreak >nul
taskkill /F /IM RhinosBuddySupervisor.exe >nul 2>nul

echo [2/4] Removing autostart with Windows...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v RhinosBuddySupervisor /f >nul 2>nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Subscreen /f >nul 2>nul

if "%MODE%"=="update" goto folder
echo.
echo [3/4] Personal data
choice /C YN /M "Also delete your data (layout, images and settings)"
if errorlevel 2 goto keepdata
rmdir /s /q "%DATADIR%" >nul 2>nul
if exist "%OLDDATA%" rmdir /s /q "%OLDDATA%" >nul 2>nul
echo Data deleted.
goto folder
:keepdata
echo Data kept in %DATADIR%

:folder
echo.
echo [4/4] Program folder
if not defined PACKAGED goto nosource
choice /C YN /M "Delete the program folder (%APPDIR%)"
if errorlevel 2 goto fim
set "RB_APPDIR=%APPDIR%"
start "" powershell -NoProfile -WindowStyle Hidden -Command "if (Test-Path -LiteralPath (Join-Path $env:RB_APPDIR 'RhinosBuddySupervisor.exe')) { for ($i = 0; $i -lt 40 -and (Test-Path -LiteralPath $env:RB_APPDIR); $i++) { Start-Sleep -Seconds 2; Remove-Item -LiteralPath $env:RB_APPDIR -Recurse -Force -ErrorAction SilentlyContinue } }"
echo The folder will be deleted as soon as this window is closed.
goto fim
:nosource
echo RhinosBuddySupervisor.exe is not here (this folder is the source code), so it will NOT be deleted.

:fim
echo.
echo Done.
if "%MODE%"=="update" echo To install the new version, extract the new zip anywhere and open RhinosBuddySupervisor.exe. Your data is still there.
pause
exit /b 0

:cancel
echo Nothing was changed.
pause
exit /b 0
