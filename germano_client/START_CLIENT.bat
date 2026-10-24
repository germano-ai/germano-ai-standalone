@echo off
setlocal EnableExtensions DisableDelayedExpansion
REM Testi in UTF-8; all'uscita si ripristina la tabella codici che la console aveva prima
set "GERMANO_OLDCP="
for /f "tokens=2 delims=:." %%a in ('chcp') do set "GERMANO_OLDCP=%%a"
chcp 65001 >nul 2>&1
REM pushd (invece di cd) funziona anche se il Client si trova su una cartella di rete \\server\condivisione
pushd "%~dp0" || (echo Impossibile accedere alla cartella del client. & pause & exit /b 1)

set "GERMANO_CVER=0.02"
if exist "VERSION" set /p GERMANO_CVER=<VERSION
title Germano Client v%GERMANO_CVER% - Harness LAN per le AI

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
REM Nessun file .pyc nella cartella del Client (che puo' anche essere in sola lettura)
set "PYTHONDONTWRITEBYTECODE=1"
set "PATH=%CD%\runtime;%PATH%"

if not exist "runtime\python.exe" (
    echo ERRORE: manca runtime\python.exe - il pacchetto del client e' incompleto. Estrai di nuovo lo ZIP completo.
    set "RC=1"
    pause
    goto :end
)

REM Con argomenti esegue il comando (discover, status, launch, send, config); senza, apre il menu interattivo.
"runtime\python.exe" client.py %*
set "RC=%ERRORLEVEL%"
REM Dal menu (doppio clic) la finestra resta aperta in caso di errore, per leggere il messaggio.
if "%~1"=="" if not "%RC%"=="0" (
    echo.
    pause
)

:end
popd
if defined GERMANO_OLDCP chcp %GERMANO_OLDCP% >nul 2>&1
exit /b %RC%
