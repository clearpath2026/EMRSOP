@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: EMRSOP — EMR Workflow Tracker  |  Install Script
:: Run as Administrator on each agent GCP Windows VM
:: ============================================================

echo.
echo  =========================================
echo   EMRSOP — EMR Workflow Tracker Installer
echo  =========================================
echo.

:: --- Admin check ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  ERROR: This script must be run as Administrator.
    echo  Right-click install.bat and choose "Run as administrator".
    pause
    exit /b 1
)

:: --- Locate Python ---
where python >nul 2>&1
if %errorLevel% neq 0 (
    echo  ERROR: Python not found in PATH.
    echo  Install Python 3.11+ from https://python.org and add it to PATH.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Python detected: %PY_VER%

:: --- Locate Tesseract ---
set TESS_PATH=
for %%p in (
    "C:\Program Files\Tesseract-OCR\tesseract.exe"
    "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
) do (
    if exist %%p (
        set TESS_PATH=%%~p
    )
)

if "%TESS_PATH%"=="" (
    echo.
    echo  WARNING: Tesseract OCR not found.
    echo  Screenshot text-blur will be disabled until Tesseract is installed.
    echo  Download: https://github.com/UB-Mannheim/tesseract/wiki
    echo  Install to: C:\Program Files\Tesseract-OCR\
    echo.
    set SKIP_TESS=1
) else (
    echo  Tesseract detected: %TESS_PATH%
    set SKIP_TESS=0
)

:: --- Determine install directory ---
set "INSTALL_DIR=%~dp0"
set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
set "CONFIG_DIR=C:\ProgramData\EMRTracker\config"
set "DATA_DIR=C:\ProgramData\EMRTracker\data"

echo.
echo  Install directory : %INSTALL_DIR%
echo  Config directory  : %CONFIG_DIR%
echo  Data directory    : %DATA_DIR%
echo.

:: --- Create data directories ---
echo  [1/6] Creating data directories...
mkdir "%CONFIG_DIR%" 2>nul
mkdir "%DATA_DIR%\workflows" 2>nul
mkdir "%DATA_DIR%\screenshots" 2>nul
echo        Done.

:: --- Copy config if not already present ---
echo  [2/6] Deploying config...
if not exist "%CONFIG_DIR%\config.yaml" (
    copy "%INSTALL_DIR%\config\config.yaml" "%CONFIG_DIR%\config.yaml" >nul
    echo        Config deployed to %CONFIG_DIR%\config.yaml
    echo        Edit this file to customise agent_id, paths, and EMR module keywords.
) else (
    echo        Config already exists — skipping to preserve your settings.
    echo        Location: %CONFIG_DIR%\config.yaml
)

:: --- Install Python dependencies ---
echo  [3/6] Installing Python dependencies...
python -m pip install --upgrade pip --quiet
python -m pip install -r "%INSTALL_DIR%\agent\requirements.txt" --quiet
if %errorLevel% neq 0 (
    echo  ERROR: pip install failed. Check your internet connection and try again.
    pause
    exit /b 1
)
echo        Done.

:: --- Download spaCy model ---
echo  [4/6] Downloading spaCy language model (en_core_web_lg, ~560 MB)...
python -m spacy download en_core_web_lg --quiet
if %errorLevel% neq 0 (
    echo  ERROR: spaCy model download failed.
    echo  Run manually:  python -m spacy download en_core_web_lg
    pause
    exit /b 1
)
echo        Done.

:: --- Set Tesseract path in environment if found ---
if "%SKIP_TESS%"=="0" (
    echo  [5/6] Registering Tesseract path...
    setx TESSERACT_CMD "%TESS_PATH%" /M >nul
    echo        Set TESSERACT_CMD = %TESS_PATH%
) else (
    echo  [5/6] Skipping Tesseract registration (not installed).
)

:: --- Install and start Windows service ---
echo  [6/6] Installing EMRTrackerService...
cd /d "%INSTALL_DIR%"
python agent\service\install_service.py install
if %errorLevel% neq 0 (
    echo  ERROR: Service installation failed.
    pause
    exit /b 1
)

python agent\service\install_service.py start
if %errorLevel% neq 0 (
    echo  WARNING: Service installed but failed to start.
    echo  Start manually from Services (services.msc) or run:
    echo    python agent\service\install_service.py start
) else (
    echo        Service started successfully.
)

echo.
echo  =========================================
echo   Installation complete!
echo  =========================================
echo.
echo  Service name : EMRTrackerService
echo  Data output  : %DATA_DIR%\workflows\
echo  Audit log    : %DATA_DIR%\audit.log
echo  Config file  : %CONFIG_DIR%\config.yaml
echo.
echo  To verify the service is running:
echo    sc query EMRTrackerService
echo.
echo  To view the Windows Event Log for service messages:
echo    eventvwr  (look under Windows Logs > Application)
echo.
if "%SKIP_TESS%"=="1" (
    echo  REMINDER: Install Tesseract OCR for screenshot blur to work.
    echo    https://github.com/UB-Mannheim/tesseract/wiki
    echo.
)
pause
