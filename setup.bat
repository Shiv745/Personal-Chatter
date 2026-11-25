@echo off
title PulseAI Agent - Setup
echo ============================================
echo   PulseAI Chat Agent - Windows Setup
echo ============================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.10+ not found in PATH!
    echo Please install Python from https://www.python.org/downloads/
    echo and check "Add Python to PATH".
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment (.venv)...
python -m venv .venv
call .venv\Scripts\activate.bat

echo [2/4] Upgrading pip...
python -m pip install --upgrade pip

echo [3/4] Installing Python dependencies...
pip install -r requirements.txt

echo [4/4] Installing Playwright Chromium browser...
playwright install chromium

echo.
echo ============================================
echo   Setup Complete!
echo   1. Add your Gemini API key in config.json
echo      (or inside the App Settings tab).
echo   2. Double-click run.bat to launch the app!
echo ============================================
pause
