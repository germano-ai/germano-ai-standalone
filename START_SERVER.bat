@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM pushd (invece di cd) funziona anche se il programma si trova su una cartella di rete \\server\condivisione
pushd "%~dp0" || (echo Impossibile accedere alla cartella del programma. & pause & exit /b 1)

set "GERMANO_VER=0.52-alpha"
if exist "VERSION" set /p GERMANO_VER=<VERSION
TITLE Germano SERVER v%GERMANO_VER% - Motore di privacy e Proxy IA in ascolto sulla LAN

REM Ambiente 100% offline e portatile
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "DO_NOT_TRACK=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PATH=%CD%\runtime;%CD%\runtime\Scripts;%PATH%"

REM --- Modalita' SERVER per QUESTO avvio (prevale su quella salvata nelle Impostazioni, che non viene modificata):
REM     ascolto sulla rete locale + rilevamento automatico UDP + motore condiviso con i client Germano.
REM     Per usarla sempre, scegli "Server" nelle Impostazioni della Dashboard e avvia con START.bat.
set "GERMANO_MODE=server"

echo ==============================================================
echo                 GERMANO.AI SERVER v%GERMANO_VER%
echo       Motore locale di anonimizzazione + Proxy IA su LAN
echo            100%% Offline  ^|  Standalone  ^|  GDPR
echo ==============================================================
echo.

if not exist "runtime\python.exe" (
    echo ERRORE: manca runtime\python.exe - il pacchetto e' incompleto. Estrai di nuovo lo ZIP completo.
    goto :fail
)
if not exist "models\privacy-filter\model.safetensors" (
    echo ERRORE: mancano i modelli IA nella cartella "models". Estrai di nuovo lo ZIP completo.
    goto :fail
)

REM Il firewall di Windows, al primo avvio, chiedera' di consentire Python sulle reti private:
echo NOTA: al primo avvio consenti l'accesso di Python alle reti PRIVATE quando Windows lo chiede,
echo       altrimenti i computer della rete locale non riusciranno a raggiungere il server.
echo.

REM Aggiornamento gia' scaricato e verificato: si installa prima dell'avvio
if exist "update\ready.json" (
    echo [*] Installazione dell'aggiornamento gia' scaricato...
    "runtime\python.exe" server.py --install-update
    if errorlevel 10 if not errorlevel 11 goto :updating
)

echo Avvio del server in ascolto sulla rete locale...
echo (l'indirizzo IP e il token per i client compaiono qui sotto)
echo.
"runtime\python.exe" server.py
set "GERMANO_EXIT=%ERRORLEVEL%"
if "%GERMANO_EXIT%"=="0" goto :end
if "%GERMANO_EXIT%"=="10" goto :end

echo.
echo  Germano Server si e' chiuso con un errore (codice %GERMANO_EXIT%).
if "%GERMANO_EXIT%"=="2" (
    echo  La porta e' occupata da un altro programma: cambia "port" in config.json.
) else (
    echo  Dettagli nel file daemon.log in questa cartella.
)
:fail
echo.
pause
popd
exit /b 1

:updating
echo     L'aggiornamento prosegue in una nuova finestra: Germano si riavviera' da solo.
popd
exit /b 0

:end
popd
exit /b 0
