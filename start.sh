#!/bin/bash
set -e

cd "$(dirname "$0")"

# 安装 Python 依赖
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q

# 启动后端
echo "启动 PolyTrad 后端..."
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --reload
