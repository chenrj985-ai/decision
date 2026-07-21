@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Install V7 Pro
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE if exist "%USERPROFILE%\anaconda3\python.exe" set "PYEXE=%USERPROFILE%\anaconda3\python.exe"
if not defined PYEXE if exist "D:\anaconda3\python.exe" set "PYEXE=D:\anaconda3\python.exe"
if not defined PYEXE (
  echo 未找到Python。请安装Python 3.10以上或Anaconda。
  pause
  exit /b 1
)
"%PYEXE%" -m pip install -r requirements.txt
echo 安装完成。
pause
