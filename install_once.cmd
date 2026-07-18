@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist "%~dp0logs" mkdir "%~dp0logs" >nul 2>nul
set "LOGFILE=%~dp0logs\install.log"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

echo ============================================================
echo Stock Decision System V5 - Installer
echo ============================================================

set "BASEPY="
where py >nul 2>nul && set "BASEPY=py -3"
if not defined BASEPY where python >nul 2>nul && set "BASEPY=python"
if not defined BASEPY (
  echo [ERROR] Python 3 was not found.
  echo Install Python 3.10 or newer and enable Add Python to PATH.
  if /I not "%~1"=="--auto" pause
  exit /b 9009
)

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [1/3] Creating .venv...
  %BASEPY% -m venv "%~dp0.venv" >>"%LOGFILE%" 2>&1
  if errorlevel 1 goto :fail
) else (
  echo [1/3] Existing .venv found.
)

echo [2/3] Upgrading pip...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :fail

echo [3/3] Installing requirements...
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :fail

"%~dp0.venv\Scripts\python.exe" -c "import pandas,requests; print('Dependency check OK')" >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :fail

echo [OK] Installation completed.
if /I not "%~1"=="--auto" pause
exit /b 0

:fail
echo [ERROR] Installation failed. Open logs\install.log
if /I not "%~1"=="--auto" pause
exit /b 1
