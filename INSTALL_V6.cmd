@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Install V6 Dependencies
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
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
%PY% -m pip install -r requirements.txt
pause
