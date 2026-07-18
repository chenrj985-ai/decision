@echo off
setlocal EnableExtensions
title Stock Decision System V6 - Local Runner
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0\.."

echo ============================================================
echo Stock Decision System V6 - Local Runner
echo Project: %CD%
echo ============================================================

set "PY_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo [ERROR] Python was not found.
    echo Install Python 3.10 or later and enable Add Python to PATH.
    pause
    exit /b 1
)

echo [1/4] Checking virtual environment...
if not exist ".venv\Scripts\python.exe" (
    echo Creating .venv...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :failed
)

echo [2/4] Activating virtual environment...
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :failed

echo [3/4] Installing required packages...
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

echo [4/4] Running V6...
python cloud_runner.py
if errorlevel 1 goto :failed

echo.
echo [SUCCESS] V6 finished successfully.
echo Report file: site\index.html
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] V6 stopped because a command failed.
echo Please take a screenshot of the lines above.
echo.
pause
exit /b 1
