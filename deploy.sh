#!/bin/bash
# VPS 部署脚本
set -e

echo "=== PolyTrad VPS 部署 ==="

# 1. 安装系统依赖
if command -v apt-get &> /dev/null; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv nginx certbot python3-certbot-nginx
elif command -v yum &> /dev/null; then
    yum install -y python3 python3-pip nginx
fi

# 2. 设置项目
cd /opt/polytrad || cd "$(dirname "$0")"

# 生产数据保护：数据库和密钥不应该跟随代码同步被覆盖。
mkdir -p /var/lib/polytrad /etc/polytrad /opt/polytrad/backups
chown -R www-data:www-data /var/lib/polytrad 2>/dev/null || true

if [ -f /opt/polytrad/polytrad.db ] && [ ! -f /var/lib/polytrad/polytrad.db ]; then
    echo "迁移现有数据库到 /var/lib/polytrad/polytrad.db"
    cp /opt/polytrad/polytrad.db /var/lib/polytrad/polytrad.db
    chown www-data:www-data /var/lib/polytrad/polytrad.db 2>/dev/null || true
fi

if [ -f /var/lib/polytrad/polytrad.db ]; then
    ts=$(date +%Y%m%d-%H%M%S)
    cp /var/lib/polytrad/polytrad.db "/opt/polytrad/backups/polytrad-$ts.db"
    echo "已备份生产数据库: /opt/polytrad/backups/polytrad-$ts.db"
fi

if [ ! -f /etc/polytrad/polytrad.env ]; then
    if [ -f /opt/polytrad/.env ]; then
        cp /opt/polytrad/.env /etc/polytrad/polytrad.env
        echo "已复制现有 .env 到 /etc/polytrad/polytrad.env"
    else
        cat > /etc/polytrad/polytrad.env << EOF
POLYTRAD_MASTER_KEY=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$(openssl rand -hex 12)
DATABASE_URL=sqlite+aiosqlite:////var/lib/polytrad/polytrad.db
POLYMARKET_CHAIN_ID=137
EOF
        echo "已创建 /etc/polytrad/polytrad.env，请保存其中的初始 ADMIN_PASSWORD"
    fi
fi

if ! grep -q '^DATABASE_URL=' /etc/polytrad/polytrad.env; then
    echo "DATABASE_URL=sqlite+aiosqlite:////var/lib/polytrad/polytrad.db" >> /etc/polytrad/polytrad.env
fi

# 创建 venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -q

# 3. 构建前端
cd frontend
npm install
npm run build
cd ..

# 4. 创建 systemd 服务
cat > /etc/systemd/system/polytrad.service << 'EOF'
[Unit]
Description=PolyTrad Trading Tool
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/polytrad
EnvironmentFile=/etc/polytrad/polytrad.env
ExecStart=/opt/polytrad/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 5. Nginx 配置
cat > /etc/nginx/sites-available/polytrad << 'EOF'
server {
    listen 80;
    server_name YOUR_DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

ln -sf /etc/nginx/sites-available/polytrad /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 6. 启用服务
systemctl daemon-reload
systemctl enable polytrad
systemctl start polytrad
systemctl restart nginx

echo "=== 部署完成 ==="
echo "1. 编辑生产环境变量: nano /etc/polytrad/polytrad.env"
echo "2. 生产数据库: /var/lib/polytrad/polytrad.db"
echo "3. 修改 nginx 配置中的 YOUR_DOMAIN"
echo "4. 运行 certbot --nginx 获取 SSL 证书"
echo "5. 访问 http://YOUR_DOMAIN 或 http://YOUR_DOMAIN/m"
