@echo off
chcp 65001 >nul 2>&1
TITLE Germano AI v0.50-alpha - Local Privacy Engine ^& API Proxy
cd /d "%~dp0"

REM Configurazione ambiente 100% Offline e UTF-8 per Windows 11 Vanilla
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "DO_NOT_TRACK=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PATH=%~dp0runtime;%~dp0runtime\Scripts;%PATH%"

echo ==============================================================
echo                      GERMANO.AI v0.50-alpha
echo        Suite Locale di Anonimizzazione Documentale ^& IA
echo              100%% Offline  ^|  Standalone  ^|  GDPR
echo ==============================================================
echo.

echo [1/2] Verifica dei prerequisiti di sistema Windows...
if exist "runtime\msvcp140.dll" (
    echo       Librerie C++ Runtime portatili integrate rilevate [OK]
) else (
    REG QUERY "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v Version >nul 2>&1
    if %errorlevel% neq 0 (
        echo       Installazione librerie Microsoft Visual C++ Redistributable...
        if exist "prerequisites\vc_redist.x64.exe" (
            start /wait prerequisites\vc_redist.x64.exe /install /quiet /norestart
            echo       Installazione completata [OK]
        )
    ) else (
        echo       Librerie di sistema Visual C++ rilevate [OK]
    )
)

echo [2/2] Avvio del Server Locale e della Dashboard Web...
echo       Dashboard URL : http://127.0.0.1:8000
echo       API Proxy URL : http://127.0.0.1:8000/v1
echo.
runtime\python.exe server.py
pause
