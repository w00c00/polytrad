#!/bin/bash
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "用法: $0 user@host:/opt/polytrad/"
    echo "示例: $0 root@1.2.3.4:/opt/polytrad/"
    exit 1
fi

target="$1"
cd "$(dirname "$0")/.."

echo "同步代码到: $target"
echo "保护: .env / *.db / data/ / venv / node_modules / dist"

rsync -az --delete \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='*.db' \
    --exclude='*.db-wal' \
    --exclude='*.db-shm' \
    --exclude='data/' \
    --exclude='backups/' \
    --exclude='venv/' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='frontend/node_modules/' \
    --exclude='frontend/dist/' \
    --exclude='.git/' \
    --exclude='.DS_Store' \
    --exclude='*.log' \
    --exclude='.rsync-filter' \
    --exclude='scripts/' \
    ./ "$target"

echo "同步完成。生产数据库和 .env 未被覆盖。"
