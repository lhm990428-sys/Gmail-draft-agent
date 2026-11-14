@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "frontend\dist-api\index.html" (
  echo API console build missing. Run: cd frontend ^& npm run build:api
  pause
  exit /b 1
)
"backend\.venv\Scripts\python.exe" -m mail_tools.cli serve --open --gateway
if errorlevel 1 (
  echo.
  echo 앱 시작에 실패했습니다. 위 오류를 확인하세요. 이 창에서 기다려도 자동으로 다시 시작되지 않습니다.
)
pause
