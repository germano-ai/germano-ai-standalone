@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM pushd (invece di cd) funziona anche se il programma si trova su una cartella di rete \\server\condivisione
pushd "%~dp0" || (echo Impossibile accedere alla cartella del programma. & pause & exit /b 1)

set "GERMANO_VER=0.51-alpha"
if exist "VERSION" set /p GERMANO_VER=<VERSION
TITLE Germano AI v%GERMANO_VER% - Local Privacy Engine ^& API Proxy

REM Ambiente 100% offline e portatile (nessuna cache nel profilo utente, nessuna telemetria)
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "DO_NOT_TRACK=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PATH=%CD%\runtime;%CD%\runtime\Scripts;%PATH%"

echo ==============================================================
echo                      GERMANO.AI v%GERMANO_VER%
echo        Suite Locale di Anonimizzazione Documentale ^& IA
echo              100%% Offline  ^|  Standalone  ^|  GDPR
echo ==============================================================
echo.

echo [1/3] Verifica dei file del programma...
if not exist "runtime\python.exe" (
    echo       ERRORE: manca runtime\python.exe - il pacchetto e' incompleto.
    echo       Estrai di nuovo l'archivio ZIP completo prima di avviare Germano.
    goto :fail
)
if not exist "models\privacy-filter\model.safetensors" (
    echo       ERRORE: mancano i modelli IA nella cartella "models".
    echo       Estrai di nuovo l'archivio ZIP completo prima di avviare Germano.
    goto :fail
)
set "GERMANO_DIR=%CD%"
if not "%GERMANO_DIR:~105,1%"=="" (
    echo       ATTENZIONE: il percorso della cartella e' molto lungo:
    echo       %GERMANO_DIR%
    echo       Se compaiono errori, sposta la cartella in un percorso piu' corto, ad esempio C:\GermanoAI
)
echo       File del programma presenti [OK]

echo [2/3] Verifica dei prerequisiti di Windows...
if exist "runtime\msvcp140.dll" (
    echo       Librerie Microsoft Visual C++ integrate [OK]
) else (
    reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v Version >nul 2>&1
    if errorlevel 1 (
        if exist "prerequisites\vc_redist.x64.exe" (
            echo       Installazione librerie Microsoft Visual C++ Redistributable...
            start "" /wait "prerequisites\vc_redist.x64.exe" /install /quiet /norestart
        )
    ) else (
        echo       Librerie di sistema Visual C++ rilevate [OK]
    )
)
set "GERMANO_SAC="
for /f "tokens=3" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy" /v VerifiedAndReputablePolicyState 2^>nul ^| find "0x"') do set "GERMANO_SAC=%%A"
if "%GERMANO_SAC%"=="0x1" (
    echo       ATTENZIONE: "Smart App Control" di Windows e' attivo e potrebbe bloccare i componenti IA.
    echo       Se l'avvio fallisce: Sicurezza di Windows ^> Controllo delle app e del browser ^> Smart App Control.
)

REM Aggiornamento gia' scaricato e verificato (update\ready.json): si installa prima dell'avvio
if exist "update\ready.json" (
    echo [*] Installazione dell'aggiornamento gia' scaricato...
    "runtime\python.exe" server.py --install-update
    if errorlevel 10 if not errorlevel 11 goto :updating
)

echo [3/3] Avvio del Server Locale e della Dashboard Web...
echo       La Dashboard si apre nel browser (http://127.0.0.1:8181).
echo       Per chiudere Germano AI chiudi questa finestra.
echo.
"runtime\python.exe" server.py
set "GERMANO_EXIT=%ERRORLEVEL%"
if "%GERMANO_EXIT%"=="0" goto :end
REM 10 = chiusura per installare un aggiornamento (prosegue in un'altra finestra)
if "%GERMANO_EXIT%"=="10" goto :end

echo.
echo  Germano AI si e' chiuso con un errore (codice %GERMANO_EXIT%).
if "%GERMANO_EXIT%"=="2" (
    echo  La porta usata da Germano e' occupata da un altro programma.
) else (
    echo  - Se compare "DLL load failed" o "Application Control": controlla antivirus / Smart App Control.
    echo  - Il registro dettagliato del motore IA e' nel file daemon.log in questa cartella.
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
