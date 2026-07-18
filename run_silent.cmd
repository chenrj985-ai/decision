@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0logs" mkdir "%~dp0logs" >nul 2>nul
if not exist "%~dp0.venv\Scripts\python.exe" exit /b 2
"%~dp0.venv\Scripts\python.exe" -X utf8 "%~dp0update_risk_data.py" >>"%~dp0logs\scheduled_risk.log" 2>&1
"%~dp0.venv\Scripts\python.exe" -X utf8 "%~dp0main.py" >>"%~dp0logs\scheduled_run.log" 2>&1
exit /b %ERRORLEVEL%
