@echo off
setlocal
cd /d "%~dp0"
where ffmpeg >nul 2>nul
if errorlevel 1 goto install
where ffprobe >nul 2>nul
if errorlevel 1 goto install
echo FFmpeg and FFprobe are already available.
pause
exit /b 0
:install
where winget >nul 2>nul
if errorlevel 1 (
  echo WinGet is unavailable. Follow the manual FFmpeg steps in START_HERE.html.
  start "" "%~dp0START_HERE.html"
  pause
  exit /b 1
)
echo Installing FFmpeg using WinGet. Review any installer prompts.
winget install --id Gyan.FFmpeg --exact --source winget
if errorlevel 1 (
  echo Installation did not complete. See the output above or use the manual guide.
  pause
  exit /b 1
)
echo Close this window and open setup_windows.bat from a NEW terminal or Explorer.
echo If PATH is not refreshed, sign out of Windows and sign back in.
pause
