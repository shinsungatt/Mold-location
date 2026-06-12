@echo off
title Mold INDEX Server

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Python not found. Please install Python 3.10+
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

python -c "import flask" 2>nul
if errorlevel 1 (
    echo Installing packages...
    pip install -r requirements.txt -q
)

if not exist "data" mkdir data

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000 " 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)

start /min "" cmd /c "python app.py"

ping 127.0.0.1 -n 3 -w 500 > nul
start "" "http://localhost:5000"

echo.
echo Server started: http://localhost:5000
echo.
pause
