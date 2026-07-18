@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "TASKNAME=StockDecisionV5_1440"
set "RUNNER=%~dp0run_silent.cmd"
if not exist "%RUNNER%" (
  echo [ERROR] run_silent.cmd not found.
  pause
  exit /b 1
)
schtasks /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 14:40 /TN "%TASKNAME%" /TR "\"%RUNNER%\"" >nul
if errorlevel 1 (
  echo [ERROR] Could not create scheduled task. Try Run as administrator.
  pause
  exit /b 1
)
echo [OK] Task created: %TASKNAME% at 14:40 on trading weekdays.
pause
