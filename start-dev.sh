#!/bin/bash
set -e

cd "$(dirname "$0")"

# 安装 Python 依赖
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q

# 安装前端依赖
cd frontend
if [ ! -d "node_modules" ]; then
    npm install
fi
cd ..

# 同时启动前后端
echo "启动 PolyTrad 开发模式..."
(uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &) && \
cd frontend && npm run dev
