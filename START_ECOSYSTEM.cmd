@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run SETUP.ps1 first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m rednexus.platform.cli launch --ecosystem --concurrency 2
pause
