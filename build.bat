@echo off
rem Сборка Vozvrat.exe и инсталлятора dist\VozvratSetup.exe (нужны Python и Inno Setup 6)
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install --only-binary cryptography -r requirements.txt pyinstaller || exit /b 1
python packaging\build.py || exit /b 1
