@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "KNU_UI_PYTHON=%~dp0.venv\Scripts\python.exe"
  goto install
)
if defined VIRTUAL_ENV (
  set "KNU_UI_PYTHON=%VIRTUAL_ENV%\Scripts\python.exe"
  goto install
)
if exist "C:\whisper\whisper_env\Scripts\python.exe" (
  set "KNU_UI_PYTHON=C:\whisper\whisper_env\Scripts\python.exe"
  goto install
)
echo No existing environment found.
echo Activate your Whisper environment first, or run setup_windows.bat.
pause
exit /b 1
:install
echo Installing the Qt interface in this environment:
echo %KNU_UI_PYTHON%
"%KNU_UI_PYTHON%" -m pip install -r requirements-ui.txt
if errorlevel 1 goto failed
"%KNU_UI_PYTHON%" -c "from PySide6.QtWidgets import QApplication; print('Qt interface ready.')"
if errorlevel 1 goto failed
"%KNU_UI_PYTHON%" -m playwright install chromium
if errorlevel 1 goto failed
echo Done. Double-click start_windows.bat to launch.
pause
exit /b 0
:failed
echo Installation failed. Read the error above.
pause
exit /b 1
