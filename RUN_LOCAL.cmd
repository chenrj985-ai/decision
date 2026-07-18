@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Stock Decision V5.1.1 GitHub Core
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo ==========================================
echo Stock Decision V5.1.1 GitHub Core
echo ==========================================

python --version >nul 2>nul
if errorlevel 1 (
    echo ERROR: The command "python" is not available.
    echo Open CMD and confirm that python can run.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :failed
)

set "VPY=%CD%\.venv\Scripts\python.exe"
echo Installing packages...
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 echo WARNING: pip install failed; existing packages will be used.

echo Running original V5.1.1 core...
"%VPY%" cloud_runner.py
if errorlevel 1 goto :failed

if exist "site\index.html" start "" "site\index.html"
echo SUCCESS.
pause
exit /b 0

:failed
echo ERROR: Execution failed.
echo Check logs\last_error.txt and logs files.
pause
exit /b 1
