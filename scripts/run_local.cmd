@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
if not exist .venv py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -U pip
pip install -r requirements.txt
python cloud_runner.py
if errorlevel 1 (
  echo 运行失败，请查看上方错误。
  pause
  exit /b 1
)
echo 运行完成：site\index.html
pause
