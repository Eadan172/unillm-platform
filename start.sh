#!/usr/bin/env bash
# UniLLM Platform 一键启动（Linux / macOS）
#
# 流程：创建虚拟环境 → 安装依赖 → 启动服务
# 启动后：控制台 http://127.0.0.1:8000/console/ ，访问 Token 会在启动日志中醒目打印。
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
VENV_DIR=".venv"

echo "============================================================"
echo " UniLLM Platform 一键启动"
echo "============================================================"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "找不到 Python（$PY）。请先安装 Python 3.9 – 3.13，或设置环境变量 PYTHON 指向解释器。" >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[1/3] 创建虚拟环境 $VENV_DIR ..."
  "$PY" -m venv "$VENV_DIR"
else
  echo "[1/3] 复用已有虚拟环境 $VENV_DIR"
fi

# shellcheck disable=SC1091
. "$VENV_DIR/bin/activate"

echo "[2/3] 安装依赖（requirements.txt）..."
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

echo "[3/3] 启动服务（读取 config.yaml 的 host/port）..."
echo "      控制台地址：http://127.0.0.1:8000/console/"
echo "      下方会打印访问 Token；未配置时自动生成并写入 ./data/.api_token"
echo "------------------------------------------------------------"
exec python -m app.main
