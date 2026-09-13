@echo off
REM UniLLM Platform 一键启动（Windows）
REM 流程：创建虚拟环境 -^> 安装依赖 -^> 启动服务
REM 启动后：控制台 http://127.0.0.1:8000/console/ ，访问 Token 会在启动日志中醒目打印。
setlocal
cd /d "%~dp0"

echo ============================================================
echo  UniLLM Platform 一键启动
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
  echo 找不到 python 命令。请先安装 Python 3.9 - 3.13 并加入 PATH。
  exit /b 1
)

if not exist ".venv" (
  echo [1/3] 创建虚拟环境 .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo 创建虚拟环境失败。
    exit /b 1
  )
) else (
  echo [1/3] 复用已有虚拟环境 .venv
)

call ".venv\Scripts\activate.bat"

echo [2/3] 安装依赖（requirements.txt）...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo 安装依赖失败。
  exit /b 1
)

echo [3/3] 启动服务（读取 config.yaml 的 host/port）...
echo       控制台地址：http://127.0.0.1:8000/console/
echo       下方会打印访问 Token；未配置时自动生成并写入 .\data\.api_token
echo ------------------------------------------------------------
python -m app.main

endlocal
