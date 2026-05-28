@echo off
setlocal

:: ============================================================
:: EMRSOP — EMR Workflow Tracker  |  Uninstall Script
:: Run as Administrator
:: ============================================================

echo.
echo  ============================================
echo   EMRSOP — EMR Workflow Tracker Uninstaller
echo  ============================================
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  ERROR: This script must be run as Administrator.
    pause
    exit /b 1
)

set "INSTALL_DIR=%~dp0"
set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"

echo  [1/3] Stopping service...
python "%INSTALL_DIR%\agent\service\install_service.py" stop 2>nul
timeout /t 2 /nobreak >nul

echo  [2/3] Removing service...
python "%INSTALL_DIR%\agent\service\install_service.py" remove 2>nul
echo        Done.

echo  [3/3] Data preserved at C:\ProgramData\EMRTracker\data\
echo        Delete manually if you want to remove all records.

echo.
echo  Uninstall complete. Python packages were NOT removed.
echo  To remove them: pip uninstall presidio-analyzer presidio-anonymizer spacy pywin32
echo.
pause
