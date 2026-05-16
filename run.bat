@echo off
title Japanese OCR App

REM -- Check venv exists --
if not exist venv\Scripts\activate.bat (
    echo.
    echo  [ERROR] Virtual environment not found.
    echo  Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

REM -- Activate venv and launch app --
call venv\Scripts\activate.bat
python app.py

REM -- Show error if app crashed --
if %errorlevel% neq 0 (
    echo.
    echo  App exited with error code: %errorlevel%
    pause
)
