@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" jarvis.py --voice --wake --greet
) else (
  python jarvis.py --voice --wake --greet
)
pause
