@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE if exist "%USERPROFILE%\anaconda3\python.exe" set "PYEXE=%USERPROFILE%\anaconda3\python.exe"
if not defined PYEXE if exist "D:\anaconda3\python.exe" set "PYEXE=D:\anaconda3\python.exe"
if not defined PYEXE if exist "C:\ProgramData\anaconda3\python.exe" set "PYEXE=C:\ProgramData\anaconda3\python.exe"
if not defined PYEXE (
  echo 未找到Python
  pause
  exit /b 1
)
"%PYEXE%" "修复已有推荐历史.py"
