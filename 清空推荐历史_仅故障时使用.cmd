@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "data\recommendation_history.csv" (
  copy /y "data\recommendation_history.csv" "data\recommendation_history_backup.csv" >nul
  del /q "data\recommendation_history.csv"
  echo 已备份为 data\recommendation_history_backup.csv
  echo 原推荐历史已清空。
) else (
  echo 未发现推荐历史文件。
)
pause
