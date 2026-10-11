@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo Установите Python 3.11+ с python.org & pause & exit /b 1)
if not exist ".deps-ok" (
  echo Первый запуск: устанавливаю зависимости...
  python -m pip install -r requirements.txt || (pause & exit /b 1)
  python app\setup_tools.py || (pause & exit /b 1)
  echo ok> .deps-ok
)
python app\server.py
pause
