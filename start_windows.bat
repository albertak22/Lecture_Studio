@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
  goto end
)
if defined VIRTUAL_ENV (
  "%VIRTUAL_ENV%\Scripts\python.exe" app.py
  goto end
)
if exist "C:\whisper\whisper_env\Scripts\python.exe" (
  "C:\whisper\whisper_env\Scripts\python.exe" app.py
  goto end
)
echo No environment found. Read README_ko.md or run setup_windows.bat
pause
exit /b 1
:end
if errorlevel 1 (
  echo Application failed. Read the error above and run check_environment.py.
  pause
)
