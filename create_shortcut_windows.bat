@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"
if errorlevel 1 (
  echo Shortcut creation failed. Run setup first or read the error above.
  pause
  exit /b 1
)
echo Done. Use Lecture Studio on your desktop.
echo Recreate the shortcut if you move the program folder.
pause
