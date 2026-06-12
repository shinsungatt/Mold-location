@echo off
chcp 65001 > nul
title 신성오토텍 금형 INDEX

cd /d "%~dp0"

:: ── 가상환경 확인 및 생성 ──────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo [초기 설정] 가상환경 생성 중...
    python -m venv venv
    if errorlevel 1 (
        echo [오류] Python이 설치되어 있지 않습니다.
        echo Python 3.10 이상을 설치한 후 다시 실행하세요.
        pause
        exit /b 1
    )
)

:: ── 가상환경 활성화 ────────────────────────────────────────
call venv\Scripts\activate.bat

:: ── 패키지 설치 확인 ───────────────────────────────────────
python -c "import flask" 2>nul
if errorlevel 1 (
    echo [초기 설정] 패키지 설치 중...
    pip install -r requirements.txt -q
)

:: ── data 폴더 생성 ─────────────────────────────────────────
if not exist "data" mkdir data

:: ── 기존 포트 5000 프로세스 종료 ──────────────────────────
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000 " 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: ── 서버 실행 (백그라운드) ────────────────────────────────
start /min "" cmd /c "python app.py"

:: ── 잠시 대기 후 브라우저 열기 ────────────────────────────
ping 127.0.0.1 -n 3 -w 500 > nul
start "" "http://localhost:5000"

echo.
echo 서버가 시작되었습니다: http://localhost:5000
echo 같은 네트워크에서 접속: http://[이 PC의 IP]:5000
echo.
echo 창을 닫으면 서버가 종료됩니다.
pause
