@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Stock Decision System V6 Tencent
set "PY="
for %%P in ("%USERPROFILE%\anaconda3\python.exe" "%USERPROFILE%\miniconda3\python.exe" "D:\Anaconda3\python.exe" "C:\Anaconda3\python.exe" "D:\anaconda3\python.exe" "C:\anaconda3\python.exe") do (
  if exist "%%~P" if not defined PY set "PY=%%~P"
)
if not defined PY (where py >nul 2>nul && set "PY=py -3")
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo Python was not found.
  pause
  exit /b 1
)
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
%PY% main.py
if errorlevel 1 (
  echo.
  echo Run failed. Please open logs\last_error.txt
  pause
  exit /b 1
)
if exist "output\mobile_latest.html" start "" "output\mobile_latest.html"
pause
