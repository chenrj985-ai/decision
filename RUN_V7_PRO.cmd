@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Stock Decision System V7 Pro
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE if exist "%USERPROFILE%\anaconda3\python.exe" set "PYEXE=%USERPROFILE%\anaconda3\python.exe"
if not defined PYEXE if exist "D:\anaconda3\python.exe" set "PYEXE=D:\anaconda3\python.exe"
if not defined PYEXE if exist "C:\ProgramData\anaconda3\python.exe" set "PYEXE=C:\ProgramData\anaconda3\python.exe"
if not defined PYEXE (
  echo [错误] 未找到Python。
  echo 请先运行 INSTALL_V7_PRO.cmd
  pause
  exit /b 1
)
echo 正在运行 V7 Pro，请稍候...
"%PYEXE%" main.py
if errorlevel 1 (
  echo.
  echo 运行失败，请查看 logs\last_error.txt
  pause
  exit /b 1
)
echo.
echo 已生成 output\mobile_latest.html
start "" "output\mobile_latest.html"
pause
