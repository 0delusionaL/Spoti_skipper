@echo off
chcp 65001 >nul
cd /d "%~dp0listener"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" listener.py %*
) else (
  python listener.py %*
)
pause
