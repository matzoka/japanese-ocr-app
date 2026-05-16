@echo off
title OCR App - PaddleOCR-VL Setup

echo.
echo  ============================================
echo   Optional Setup - PaddleOCR-VL
echo  ============================================
echo.
echo  PaddleOCR-VL is a large local document parsing model.
echo  It may require GPU / WSL / Docker depending on your environment.
echo  If installation or execution fails, use RapidOCR or Mistral OCR instead.
echo.

if not exist venv\Scripts\activate.bat (
    echo [ERROR] Virtual environment not found.
    echo Please run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [1/2] Installing PaddlePaddle runtime...
python -m pip install -U paddlepaddle
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] PaddlePaddle installation failed.
    echo Please check the official PaddlePaddle installation guide for your environment.
    pause
    exit /b 1
)

echo.
echo [2/2] Installing PaddleOCR-VL dependencies...
python -m pip install -U "paddleocr[doc-parser]"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] PaddleOCR-VL installation failed.
    echo Please check the official PaddleOCR-VL environment requirements.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   PaddleOCR-VL Setup Complete!
echo  ============================================
echo.
pause
