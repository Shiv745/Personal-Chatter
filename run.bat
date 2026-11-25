@echo off
title PulseAI Chat Agent
if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Running setup.bat first...
    call setup.bat
)
call .venv\Scripts\activate.bat
python main.py %*
pause
