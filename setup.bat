@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: EMRSOP Full Setup — installs Python, Tesseract, all deps,
:: clones repo, and registers the Windows service.
:: Run as Administrator.
:: ============================================================

echo.
echo  =========================================
echo   EMRSOP Full Setup
echo  =========================================
echo.

:: --- Admin check ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  ERROR: Right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)

set "INSTALL_DIR=C:\EMRTracker"
set "REPO_URL=https://github.com/clearpath2026/EMRSOP/archive/refs/heads/main.zip"
set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "TESS_URL=https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.3.20231005.exe"
set "TEMP_DIR=%TEMP%\emrsop_setup"

mkdir "%TEMP_DIR%" 2>nul

echo  Step 1/7 — Checking Python...
:: Check if python 3.11+ is already available
python --version >nul 2>&1
if %errorLevel% equ 0 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
    echo         Found Python !PY_VER! — skipping install.
    set PYTHON_EXE=python
    goto :python_done
)

:: Try py launcher
py -3 --version >nul 2>&1
if %errorLevel% equ 0 (
    for /f "tokens=2 delims= " %%v in ('py -3 --version 2^>^&1') do set PY_VER=%%v
    echo         Found Python !PY_VER! via py launcher — skipping install.
    set PYTHON_EXE=py -3
    goto :python_done
)

echo         Python not found. Downloading Python 3.11.9...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Write-Host '        Downloading...'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%TEMP_DIR%\python_installer.exe' -UseBasicParsing"
if %errorLevel% neq 0 (
    echo  ERROR: Failed to download Python. Check internet connection.
    pause
    exit /b 1
)

echo         Installing Python (this takes ~1 minute)...
"%TEMP_DIR%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=1
if %errorLevel% neq 0 (
    echo  ERROR: Python installation failed.
    pause
    exit /b 1
)

:: Refresh PATH so python is visible in this session
for /f "usebackq tokens=2*" %%A in (`reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul`) do set SYS_PATH=%%B
set PATH=%SYS_PATH%;%PATH%

python --version >nul 2>&1
if %errorLevel% neq 0 (
    :: Fallback: look for Python in common install dirs
    for %%d in (
        "C:\Program Files\Python311"
        "C:\Program Files\Python312"
        "C:\Program Files\Python313"
        "%LOCALAPPDATA%\Programs\Python\Python311"
        "%LOCALAPPDATA%\Programs\Python\Python312"
        "%LOCALAPPDATA%\Programs\Python\Python313"
    ) do (
        if exist "%%~d\python.exe" (
            set PYTHON_EXE=%%~d\python.exe
            goto :python_done
        )
    )
    echo  ERROR: Python installed but not found in PATH. Please reboot and re-run.
    pause
    exit /b 1
)
set PYTHON_EXE=python
echo         Python installed successfully.

:python_done
echo.

echo  Step 2/7 — Checking Tesseract OCR...
set TESS_EXE=C:\Program Files\Tesseract-OCR\tesseract.exe
if exist "%TESS_EXE%" (
    echo         Tesseract found — skipping install.
    goto :tess_done
)

echo         Tesseract not found. Downloading...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%TESS_URL%' -OutFile '%TEMP_DIR%\tesseract_installer.exe' -UseBasicParsing"
if %errorLevel% neq 0 (
    echo  WARNING: Tesseract download failed. Screenshots will not be blurred.
    echo           Install manually later: https://github.com/UB-Mannheim/tesseract/wiki
    goto :tess_done
)

echo         Installing Tesseract...
"%TEMP_DIR%\tesseract_installer.exe" /S
timeout /t 5 /nobreak >nul

if exist "%TESS_EXE%" (
    echo         Tesseract installed successfully.
    setx TESSERACT_CMD "%TESS_EXE%" /M >nul
) else (
    echo  WARNING: Tesseract installer finished but exe not found. Screenshots may not be blurred.
)

:tess_done
echo.

echo  Step 3/7 — Downloading EMRSOP from GitHub...
if exist "%INSTALL_DIR%\agent\service\main.py" (
    echo         Already installed at %INSTALL_DIR% — skipping download.
    goto :clone_done
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%REPO_URL%' -OutFile '%TEMP_DIR%\emrsop.zip' -UseBasicParsing"
if %errorLevel% neq 0 (
    echo  ERROR: Download failed. Check internet connection.
    pause
    exit /b 1
)

echo         Extracting...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Expand-Archive -Path '%TEMP_DIR%\emrsop.zip' -DestinationPath '%TEMP_DIR%' -Force"

:: The zip extracts to EMRSOP-main\
if exist "%TEMP_DIR%\EMRSOP-main" (
    if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"
    move "%TEMP_DIR%\EMRSOP-main" "%INSTALL_DIR%" >nul
) else (
    echo  ERROR: Could not find extracted folder. Check %TEMP_DIR%
    pause
    exit /b 1
)
echo         Downloaded to %INSTALL_DIR%

:clone_done
echo.

echo  Step 4/7 — Creating data directories...
set "CONFIG_DIR=C:\ProgramData\EMRTracker\config"
set "DATA_DIR=C:\ProgramData\EMRTracker\data"
mkdir "%CONFIG_DIR%" 2>nul
mkdir "%DATA_DIR%\workflows" 2>nul
mkdir "%DATA_DIR%\screenshots" 2>nul

if not exist "%CONFIG_DIR%\config.yaml" (
    copy "%INSTALL_DIR%\config\config.yaml" "%CONFIG_DIR%\config.yaml" >nul
    echo         Config deployed to %CONFIG_DIR%\config.yaml
) else (
    echo         Config already exists — preserved.
)
echo.

echo  Step 5/7 — Installing Python packages...
%PYTHON_EXE% -m pip install --upgrade pip --quiet --no-warn-script-location
%PYTHON_EXE% -m pip install ^
    "presidio-analyzer>=2.2.362" ^
    "presidio-anonymizer>=2.2.362" ^
    "spacy>=3.8" ^
    "pydantic>=2.0,<3.0" ^
    "pyyaml>=6.0" ^
    "mss>=9.0" ^
    "Pillow>=10.0" ^
    "pytesseract>=0.3.10" ^
    "pywin32>=306" ^
    "psutil>=5.9" ^
    "pandas>=2.0" ^
    "numpy>=1.24" ^
    --quiet --no-warn-script-location
if %errorLevel% neq 0 (
    echo  ERROR: Package install failed.
    pause
    exit /b 1
)
echo         Done.
echo.

echo  Step 6/7 — Downloading spaCy language model (~560 MB)...
%PYTHON_EXE% -m spacy download en_core_web_lg
if %errorLevel% neq 0 (
    echo  ERROR: spaCy model download failed.
    echo  Run manually: python -m spacy download en_core_web_lg
    pause
    exit /b 1
)
echo.

echo  Step 7/7 — Installing and starting Windows service...
cd /d "%INSTALL_DIR%"
%PYTHON_EXE% agent\service\install_service.py install
if %errorLevel% neq 0 (
    echo  ERROR: Service install failed.
    pause
    exit /b 1
)
%PYTHON_EXE% agent\service\install_service.py start
if %errorLevel% neq 0 (
    echo  WARNING: Service installed but did not start. Start via services.msc
) else (
    echo         Service started.
)

echo.
echo  =========================================
echo   Setup complete!
echo  =========================================
echo.
echo  Installed to  : %INSTALL_DIR%
echo  Config file   : %CONFIG_DIR%\config.yaml
echo  Data output   : %DATA_DIR%\workflows\
echo  Audit log     : %DATA_DIR%\audit.log
echo.
echo  Check service : sc query EMRTrackerService
echo  Watch log     : powershell Get-Content %DATA_DIR%\audit.log -Wait
echo.
pause
