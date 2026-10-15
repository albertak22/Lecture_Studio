$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$projectRoot = $PSScriptRoot
$candidates = @((Join-Path $projectRoot '.venv\Scripts\pythonw.exe'))
if ($env:VIRTUAL_ENV) { $candidates += (Join-Path $env:VIRTUAL_ENV 'Scripts\pythonw.exe') }
$candidates += 'C:\whisper\whisper_env\Scripts\pythonw.exe'
$pythonPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonPath) { throw 'No Python environment found. Run setup_windows.bat or activate your Whisper environment first.' }
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktopPath 'Lecture Studio.lnk'))
$shortcut.TargetPath = $pythonPath
$shortcut.Arguments = '"' + (Join-Path $projectRoot 'app.py') + '"'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = 'Lecture Studio - Canvas and microphone transcription'
$iconPath = Join-Path $projectRoot 'lecture_studio.ico'
if (Test-Path -LiteralPath $iconPath) { $shortcut.IconLocation = $iconPath }
$shortcut.Save()
Write-Output 'Desktop shortcut created: Lecture Studio'
