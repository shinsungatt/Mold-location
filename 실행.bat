@echo off
chcp 65001 > nul
title 신성오토텍 금형위치 관리 시스템

cd /d "%~dp0"

:: 기존 포트 8765 프로세스 종료
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765 " 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: Python HTTP 서버 백그라운드 실행
start /min "" cmd /c "python -m http.server 8765"

:: 잠시 대기 후 브라우저 열기
ping 127.0.0.1 -n 2 -w 500 > nul
start "" "http://localhost:8765"
