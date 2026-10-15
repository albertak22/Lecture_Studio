@echo off
setlocal
cd /d "%~dp0"
echo KNU Lecture Studio v2.3 - NEW environment setup
echo If Whisper already works, use README_ko.md existing-environment steps.
echo This creates .venv in this folder and leaves C:\whisper\whisper_env unchanged.
where py >nul 2>nul
if errorlevel 1 (
  echo Install 64-bit Python 3.11 first: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv
  if errorlevel 1 goto failed
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto failed
echo Choose a PyTorch build: [1] NVIDIA RTX GPU CUDA 12.8 [2] CPU
choice /c 12 /n /m "Enter 1 or 2: "
if errorlevel 2 goto cpu
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 goto failed
goto packages
:cpu
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto failed
:packages
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
python -m playwright install chromium
if errorlevel 1 goto failed
python check_environment.py
if errorlevel 1 goto incomplete
echo.
echo If FFmpeg is missing, follow README_ko.md. Restart CMD after PATH changes.
echo Then double-click start_windows.bat
pause
exit /b 0
:incomplete
echo Packages installed, but environment checks need attention.
echo Open START_HERE.html and fix the listed requirements before starting.
pause
exit /b 1
:failed
echo Setup failed. See the error above and README_ko.md.
pause
exit /b 1
