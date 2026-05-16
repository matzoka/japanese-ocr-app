@echo off
title OCR App - Setup

echo.
echo  ============================================
echo   Japanese OCR App - Setup
echo   RapidOCR + Mistral OCR + Surya OCR
echo  ============================================
echo.

REM -- Check Python --
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    echo Please install Python 3.9+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
python --version
echo.

REM -- Create venv only when missing. Delete venv manually if a clean reinstall is needed. --
if exist venv\Scripts\activate.bat (
    echo [Info] Existing venv found. Reusing it.
)
echo.

REM -- Create virtual environment --
echo [1/4] Creating virtual environment (venv)...
if not exist venv\Scripts\activate.bat (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)
echo       Done!
echo.

REM -- Activate venv --
echo [2/4] Activating virtual environment...
call venv\Scripts\activate.bat
echo       Done!
echo.

REM -- Upgrade pip --
echo [3/4] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo       Done!
echo.

REM -- Install packages --
echo [4/4] Installing packages...
echo       RapidOCR + Mistral + Surya OCR. 数分かかります。
echo.
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Package installation failed.
    echo Please check your network and run setup.bat again.
    pause
    exit /b 1
)
echo.

echo  ============================================
echo   Setup Complete!
echo   Run run.bat to launch the app.
echo  ============================================
echo.
pause
