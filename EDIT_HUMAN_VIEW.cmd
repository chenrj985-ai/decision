@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE if exist "%USERPROFILE%\anaconda3\python.exe" set "PYEXE=%USERPROFILE%\anaconda3\python.exe"
if not defined PYEXE if exist "D:\anaconda3\python.exe" set "PYEXE=D:\anaconda3\python.exe"
if not defined PYEXE if exist "C:\ProgramData\anaconda3\python.exe" set "PYEXE=C:\ProgramData\anaconda3\python.exe"
if not defined PYEXE (
  echo 未找到Python，请先运行 INSTALL_V7_PRO.cmd
  pause
  exit /b 1
)
"%PYEXE%" EDIT_HUMAN_VIEW.py
