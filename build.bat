@echo off
rem Сборка Vozvrat.exe (PyInstaller) и инсталлятора dist\VozvratSetup.exe (Inno Setup 6)
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller pywebview || exit /b 1
if not exist bin\ipatool.exe python app\setup_tools.py || exit /b 1
python -m PyInstaller --noconfirm --clean --windowed --name Vozvrat --icon "%CD%\packaging\icon.ico" ^
  --add-data "%CD%\app\ui;ui" --add-data "%CD%\app\catalog.json;." --add-binary "%CD%\bin\ipatool.exe;bin" ^
  --collect-all pymobiledevice3 --collect-submodules webview --paths "%CD%\app" ^
  --distpath build\dist --workpath build\work --specpath build app\main.py || exit /b 1
set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
"%ISCC%" packaging\installer.iss || exit /b 1
echo Готово: dist\VozvratSetup.exe
