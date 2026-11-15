@echo off
rem Start Moyo (or just open its window if it's already running).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo First run: setting up Moyo's Python environment...
  uv sync --python 3.13 || (echo Setup failed. Is uv installed? & pause & exit /b 1)
)
start "" ".venv\Scripts\pythonw.exe" -m moyo %*
