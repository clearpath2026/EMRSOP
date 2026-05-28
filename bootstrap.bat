@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: EMRSOP Bootstrap — downloads and installs from GitHub
:: Run as Administrator on each agent GCP Windows VM
:: ============================================================

echo.
echo  =========================================
echo   EMRSOP Bootstrap Installer
echo  =========================================
echo.

:: --- Admin check ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  ERROR: Run as Administrator.
    echo  Right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)

set "REPO_URL=https://github.com/clearpath2026/EMRSOP.git"
set "INSTALL_DIR=C:\EMRTracker"

:: --- Check Python ---
where python >nul 2>&1
if %errorLevel% neq 0 (
    echo  ERROR: Python not found. Install Python 3.11+ from https://python.org
    echo  Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

:: --- Clone or update repo ---
if exist "%INSTALL_DIR%\.git" (
    echo  [1/2] Updating existing installation...
    cd /d "%INSTALL_DIR%"
    git pull --quiet
) else (
    where git >nul 2>&1
    if %errorLevel% neq 0 (
        echo  Git not found. Downloading via PowerShell instead...
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
            "Invoke-WebRequest -Uri 'https://github.com/clearpath2026/EMRSOP/archive/refs/heads/main.zip' -OutFile '$env:TEMP\EMRSOP.zip'; Expand-Archive -Path '$env:TEMP\EMRSOP.zip' -DestinationPath 'C:\' -Force; Rename-Item 'C:\EMRSOP-main' '%INSTALL_DIR%' -Force 2>$null"
        if %errorLevel% neq 0 (
            echo  ERROR: Download failed. Check your internet connection.
            pause
            exit /b 1
        )
    ) else (
        echo  [1/2] Cloning repository to %INSTALL_DIR%...
        git clone "%REPO_URL%" "%INSTALL_DIR%" --quiet
        if %errorLevel% neq 0 (
            echo  ERROR: Git clone failed.
            pause
            exit /b 1
        )
    )
)

echo        Done.

:: --- Run the main installer ---
echo  [2/2] Running installer...
echo.
cd /d "%INSTALL_DIR%"
call install.bat

