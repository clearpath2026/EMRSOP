@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ============================================================
:: EMRSOP Full Setup - installs Python, Tesseract, all deps,
:: downloads repo, and registers the Windows service.
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
set "TESS_URL=https://github.com/UB-Mannheim/tesseract/releases/download/v5.3.3.20231005/tesseract-ocr-w64-setup-5.3.3.20231005.exe"
set "VCREDIST_URL=https://aka.ms/vs/17/release/vc_redist.x64.exe"
set "TEMP_DIR=%TEMP%\emrsop_setup"

mkdir "%TEMP_DIR%" 2>nul

:: -------------------------------------------------------
:: Self-update: always pull latest setup.bat from GitHub
:: -------------------------------------------------------
echo.

:: -------------------------------------------------------
echo  Step 1/7 - Checking Python...
:: -------------------------------------------------------

python --version >nul 2>&1
if %errorLevel% equ 0 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
    echo         Found Python !PY_VER! - skipping install.
    set PYTHON_EXE=python
    goto :python_done
)

py -3 --version >nul 2>&1
if %errorLevel% equ 0 (
    for /f "tokens=2 delims= " %%v in ('py -3 --version 2^>^&1') do set PY_VER=%%v
    echo         Found Python !PY_VER! via py launcher - skipping install.
    set PYTHON_EXE=py -3
    goto :python_done
)

echo         Python not found. Downloading Python 3.11.9...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%PYTHON_URL%', '%TEMP_DIR%\python_installer.exe'); Write-Host '        Download complete.'"
if not exist "%TEMP_DIR%\python_installer.exe" (
    echo  ERROR: Failed to download Python. Check internet connection.
    pause
    exit /b 1
)

echo         Installing Python (this takes about 1 minute)...
"%TEMP_DIR%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=1
if %errorLevel% neq 0 (
    echo  ERROR: Python installation failed.
    pause
    exit /b 1
)

:: Refresh PATH for this session
for /f "usebackq tokens=2*" %%A in (`reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul`) do set SYS_PATH=%%B
set PATH=%SYS_PATH%;%PATH%

python --version >nul 2>&1
if %errorLevel% equ 0 (
    set PYTHON_EXE=python
    echo         Python installed successfully.
    goto :python_done
)

:: Last resort - search common install locations
for %%d in (
    "C:\Program Files\Python311"
    "C:\Program Files\Python312"
    "C:\Program Files\Python313"
    "%LOCALAPPDATA%\Programs\Python\Python311"
    "%LOCALAPPDATA%\Programs\Python\Python312"
    "%LOCALAPPDATA%\Programs\Python\Python313"
) do (
    if exist "%%~d\python.exe" (
        set "PYTHON_EXE=%%~d\python.exe"
        echo         Python found at %%~d
        goto :python_done
    )
)

echo  ERROR: Python installed but cannot be found. Please reboot and re-run setup.
pause
exit /b 1

:python_done
echo.

:: -------------------------------------------------------
echo  Step 2/7 - Checking Tesseract OCR...
:: -------------------------------------------------------

set "TESS_EXE=C:\Program Files\Tesseract-OCR\tesseract.exe"
if exist "%TESS_EXE%" (
    echo         Tesseract already installed - skipping.
    goto :tess_done
)

echo         Tesseract not found. Trying winget...
where winget >nul 2>&1
if %errorLevel% equ 0 (
    winget source update --name winget >nul 2>&1
    winget install --id UB-Mannheim.TesseractOCR --silent --accept-package-agreements --accept-source-agreements
    if exist "%TESS_EXE%" (
        echo         Tesseract installed via winget.
        setx TESSERACT_CMD "%TESS_EXE%" /M >nul
        goto :tess_done
    )
    echo         winget did not install Tesseract. Trying Chocolatey...
) else (
    echo         winget not found. Trying Chocolatey...
)

echo         winget unavailable or failed. Trying Chocolatey...
where choco >nul 2>&1
if %errorLevel% neq 0 (
    echo         Installing Chocolatey...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; iex ((New-Object Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
    :: Refresh PATH to pick up choco
    for /f "usebackq tokens=2*" %%A in (`reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul`) do set PATH=%%B;%PATH%
)

where choco >nul 2>&1
if %errorLevel% equ 0 (
    choco install tesseract --yes --no-progress
    if exist "%TESS_EXE%" (
        echo         Tesseract installed via Chocolatey.
        setx TESSERACT_CMD "%TESS_EXE%" /M >nul
        goto :tess_done
    )
)

echo         Trying direct download (~50 MB)...
del "%TEMP_DIR%\tesseract_installer.exe" 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%TESS_URL%', '%TEMP_DIR%\tesseract_installer.exe')"

if not exist "%TEMP_DIR%\tesseract_installer.exe" (
    echo  WARNING: All Tesseract install methods failed. Screenshots will not be blurred.
    echo           Install manually: https://github.com/UB-Mannheim/tesseract/wiki
    goto :tess_done
)

for %%f in ("%TEMP_DIR%\tesseract_installer.exe") do set TESS_SIZE=%%~zf
if !TESS_SIZE! LSS 1000000 (
    echo  WARNING: Tesseract download incomplete. Skipping.
    goto :tess_done
)

"%TEMP_DIR%\tesseract_installer.exe" /S
timeout /t 10 /nobreak >nul

if exist "%TESS_EXE%" (
    echo         Tesseract installed from direct download.
    setx TESSERACT_CMD "%TESS_EXE%" /M >nul
) else (
    echo  WARNING: Tesseract install failed. Screenshots will not be blurred.
)

:tess_done
echo.

:: -------------------------------------------------------
echo  Step 3/7 - Downloading EMRSOP from GitHub...
:: -------------------------------------------------------

if exist "%INSTALL_DIR%\agent\service\main.py" (
    echo         Already installed at %INSTALL_DIR% - skipping download.
    :: Always update setup.bat in the install dir
    copy /y "%~f0" "%INSTALL_DIR%\setup.bat" >nul 2>&1
    goto :clone_done
)

echo         Downloading from GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%REPO_URL%', '%TEMP_DIR%\emrsop.zip')"

if not exist "%TEMP_DIR%\emrsop.zip" (
    echo  ERROR: GitHub download failed. Check internet connection.
    pause
    exit /b 1
)

echo         Extracting...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Expand-Archive -Path '%TEMP_DIR%\emrsop.zip' -DestinationPath '%TEMP_DIR%' -Force"

if exist "%TEMP_DIR%\EMRSOP-main" (
    if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"
    move "%TEMP_DIR%\EMRSOP-main" "%INSTALL_DIR%" >nul
    echo         Installed to %INSTALL_DIR%
) else (
    echo  ERROR: Extraction failed.
    pause
    exit /b 1
)

:clone_done
echo.

:: -------------------------------------------------------
echo  Step 4/7 - Creating data directories...
:: -------------------------------------------------------

set "CONFIG_DIR=C:\ProgramData\EMRTracker\config"
set "DATA_DIR=C:\ProgramData\EMRTracker\data"
mkdir "%CONFIG_DIR%" 2>nul
mkdir "%DATA_DIR%\workflows" 2>nul
mkdir "%DATA_DIR%\screenshots" 2>nul

if not exist "%CONFIG_DIR%\config.yaml" (
    copy "%INSTALL_DIR%\config\config.yaml" "%CONFIG_DIR%\config.yaml" >nul
    echo         Config deployed to %CONFIG_DIR%\config.yaml
) else (
    echo         Config already exists - keeping your settings.
)
echo.

:: -------------------------------------------------------
echo  Step 5/7 - Installing Python packages...
:: -------------------------------------------------------

:: Install Visual C++ Redistributable (required by numpy/spaCy on Windows)
echo         Checking Visual C++ Redistributable...
call :install_vcredist
echo.

echo         Upgrading pip...
%PYTHON_EXE% -m pip install --upgrade pip --quiet --no-warn-script-location

echo         Removing spacy/thinc/numpy for clean reinstall (fixes DLL issues)...
%PYTHON_EXE% -m pip uninstall spacy thinc numpy -y --quiet 2>nul

echo         Installing numpy first...
%PYTHON_EXE% -m pip install "numpy>=1.24,<2.0" --quiet --no-warn-script-location

echo         Installing spaCy (must come after numpy)...
%PYTHON_EXE% -m pip install "spacy>=3.8" --quiet --no-warn-script-location

echo         Installing remaining packages...
%PYTHON_EXE% -m pip install ^
    "numpy>=1.24,<2.0" ^
    "presidio-analyzer>=2.2.362" ^
    "presidio-anonymizer>=2.2.362" ^
    "pydantic>=2.0,<3.0" ^
    "pyyaml>=6.0" ^
    "mss>=9.0" ^
    "Pillow>=10.0" ^
    "pytesseract>=0.3.10" ^
    "pywin32>=306" ^
    "psutil>=5.9" ^
    "pandas>=2.0,<3.0" ^
    --quiet --no-warn-script-location

if %errorLevel% neq 0 (
    echo  ERROR: Package installation failed.
    echo  Try running manually: pip install -r %INSTALL_DIR%\agent\requirements.txt
    pause
    exit /b 1
)
echo         All packages installed.
echo.

:: -------------------------------------------------------
echo  Step 6/7 - Downloading spaCy language model (~560 MB)...
:: -------------------------------------------------------

:: Verify spaCy loads before attempting download
%PYTHON_EXE% -c "import spacy" >nul 2>&1
if %errorLevel% neq 0 (
    echo  ERROR: spaCy failed to import. The DLL error is still present.
    echo.
    echo  Fix: Open a NEW Administrator command prompt and run:
    echo    pip uninstall spacy thinc numpy -y
    echo    pip install numpy
    echo    pip install spacy
    echo    python -m spacy download en_core_web_lg
    echo.
    pause
    exit /b 1
)

echo         This may take several minutes...
%PYTHON_EXE% -m spacy download en_core_web_lg
if %errorLevel% neq 0 (
    echo  ERROR: spaCy model download failed.
    echo  Run manually: python -m spacy download en_core_web_lg
    pause
    exit /b 1
)
echo.

:: -------------------------------------------------------
echo  Step 7/7 - Installing Windows service...
:: -------------------------------------------------------

cd /d "%INSTALL_DIR%"
%PYTHON_EXE% agent\service\install_service.py install
if %errorLevel% neq 0 (
    echo  ERROR: Service installation failed.
    pause
    exit /b 1
)

%PYTHON_EXE% agent\service\install_service.py start
if %errorLevel% neq 0 (
    echo  WARNING: Service installed but did not start automatically.
    echo           Open services.msc and start EMRTrackerService manually.
) else (
    echo         Service installed and started.
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
echo  Check service status:
echo    sc query EMRTrackerService
echo.
echo  Watch the audit log live:
echo    powershell Get-Content %DATA_DIR%\audit.log -Wait
echo.
if not exist "%TESS_EXE%" (
    echo  REMINDER: Tesseract was not installed - screenshots will not be blurred.
    echo  Download: https://github.com/UB-Mannheim/tesseract/wiki
    echo.
)
pause
exit /b 0

:: -------------------------------------------------------
:install_vcredist
:: -------------------------------------------------------
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v Installed >nul 2>&1
if not errorlevel 1 (
    echo         Visual C++ Redistributable already installed.
    exit /b 0
)
echo         Not found. Downloading VC++ Redistributable (~25 MB)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%VCREDIST_URL%', '%TEMP_DIR%\vc_redist.exe')"
if not exist "%TEMP_DIR%\vc_redist.exe" (
    echo  WARNING: VC++ download failed. spaCy may fail on this machine.
    exit /b 0
)
echo         Installing VC++ Redistributable (required for spaCy/numpy)...
"%TEMP_DIR%\vc_redist.exe" /quiet /norestart
timeout /t 5 /nobreak >nul
echo         VC++ installed.
exit /b 0
