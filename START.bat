@echo off
TITLE germano.ai Server Locale
cd /d "%~dp0"

echo Verifica dei prerequisiti di sistema in corso...
REG QUERY "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v Version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo =========================================================
    echo ATTENZIONE: Driver base di Windows mancanti.
    echo Sto installando le librerie Visual C++ necessarie...
    echo L'operazione richiedera' circa un minuto.
    echo =========================================================
    start /wait prerequisites\vc_redist.x64.exe /install /quiet /norestart
    echo Installazione completata!
)

echo.
echo ==============================================
echo                 GERMANO.AI
echo ==============================================
echo.
echo Avvio del Server Locale...
runtime\python.exe server.py
pause
