@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "LOGFILE=%~dp0logs\launcher.log"
if not exist "%~dp0logs" mkdir "%~dp0logs" >nul 2>nul

echo ============================================================
echo Stock Decision System V5.1.1 AutoRisk - Rate Limit Fixed
echo Folder: %CD%
echo ============================================================

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [INFO] First run detected. Installing local environment...
  call "%~dp0install_once.cmd" --auto
  if errorlevel 1 (
    echo [ERROR] Installation failed. Read logs\install.log
    pause
    exit /b 1
  )
)

set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
  echo [ERROR] Local Python environment is missing.
  echo Please run install_once.cmd again.
  pause
  exit /b 9009
)

echo [STEP 1/2] Updating risk data (with cache and rate-limit protection)...
"%PYEXE%" -X utf8 "%~dp0update_risk_data.py"
set "RISKRC=%ERRORLEVEL%"
if not "%RISKRC%"=="0" (
  echo [WARN] Automatic risk update was incomplete. Main analysis will continue.
  echo [WARN] Read logs\risk_update.log and logs\risk_update_last_error.txt
)

echo [STEP 2/2] Running market and stock decision engine...
"%PYEXE%" -X utf8 "%~dp0main.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [ERROR] Program failed with code %RC%.
  echo Please open: logs\last_error.txt
  echo [%date% %time%] main.py failed, code=%RC%>>"%LOGFILE%"
  pause
  exit /b %RC%
)

echo.
echo [OK] Completed successfully.
echo Output: output\mobile_latest.html
echo Risk  : data\global_risk_auto.csv
echo Events: data\event_risk_auto.csv
start "" "%~dp0output\mobile_latest.html" >nul 2>nul
pause
exit /b 0
