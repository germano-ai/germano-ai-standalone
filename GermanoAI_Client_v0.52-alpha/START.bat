@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "GERMANO_OLDCP="
for /f "tokens=2 delims=:." %%a in ('chcp') do set "GERMANO_OLDCP=%%a"
chcp 65001 >nul 2>&1
pushd "%~dp0" || (echo Impossibile accedere alla cartella del client. & pause & exit /b 1)

set "GERMANO_CVER=0.52-alpha"
if exist "VERSION" set /p GERMANO_CVER=<VERSION
title Germano Client v%GERMANO_CVER% - Harness LAN per le AI

REM ==============================================================
REM GESTIONE PRIVILEGI AMMINISTRATORE E FIREWALL RETE (Zero-Config)
REM ==============================================================
net session >nul 2>&1
if errorlevel 1 (
    if not "%~1"=="elevated_skip" (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%~f0\" elevated_skip %*\"' -Verb RunAs" 2>nul
        if not errorlevel 1 exit /b 0
    )
) else (
    netsh advfirewall firewall show rule name="Germano Client Discovery (UDP 8182)" >nul 2>&1
    if errorlevel 1 (
        netsh advfirewall firewall add rule name="Germano Client Discovery (UDP 8182)" dir=in action=allow protocol=UDP localport=8182 profile=any >nul 2>&1
        if exist "%CD%\runtime\python.exe" (
            netsh advfirewall firewall add rule name="Germano Client Python Runtime" dir=in action=allow program="%CD%\runtime\python.exe" enable=yes profile=any >nul 2>&1
        )
    )
)

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PATH=%CD%\runtime;%PATH%"

if not exist "runtime\python.exe" (
    echo ERRORE: manca runtime\python.exe - il pacchetto del client e' incompleto. Estrai di nuovo lo ZIP completo.
    set "RC=1"
    pause
    goto :end
)

REM Con argomenti esegue il comando (discover, status, launch, send, config); senza, apre il menu interattivo.
if "%~1"=="elevated_skip" (
    shift
    "runtime\python.exe" client.py %1 %2 %3 %4 %5 %6 %7 %8 %9
) else (
    "runtime\python.exe" client.py %*
)
set "RC=%ERRORLEVEL%"
if "%~1"=="" if not "%RC%"=="0" (
    echo.
    pause
)

:end
popd
if defined GERMANO_OLDCP chcp %GERMANO_OLDCP% >nul 2>&1
exit /b %RC%
