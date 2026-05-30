# PolyTrad - Polymarket 综合快速交易工具

一站式 Polymarket 预测市场交易工具，集成 BTC 短周期、体育赛事、政治打新、热门尾盘、事件套利等多维度交易功能，支持 AI 智能分析、Binance 技术指标、自动通知推送。

## 功能概览

### 交易模块

| 模块 | 说明 |
|------|------|
| **BTC 短周期** | 5m/15m/1h/4h/1d 多周期市场，实时盘口价下单，本地动量模型 + Binance 技术指标 + AI 综合预测 |
| **体育赛事** | NBA/NFL/网球/F1/UFC 等赛事冠军 + 单场比赛，按赛事分类浏览，快速买入 |
| **政治打新** | 自动扫描新创建的政治类市场（14 天内），按创建时间排序，过滤过期内容 |
| **热门尾盘** | 扫描即将到期（1-168h）的高成交量市场，支持 YES/NO 双向交易 |
| **事件套利** | 扫描多结果事件中 YES 价格之和偏离 1.0 的套利机会，一键执行 |
| **AI 分析** | 接入多种 AI 模型（MiniMax/OpenRouter/GLM/火山引擎等），综合市场数据给出交易建议 |
| **持仓管理** | 实时查看持仓、盈亏、USDC 余额，支持快速卖出 |
| **通知推送** | ServerChan（方糖）+ Telegram 推送，交易报告、持仓报告、扫描提醒 |

### AI 预测增强

- **本地技术分析**：动量模型、RSI、EMA、波动率，计算上涨/下跌概率
- **Binance 实时指标**：RSI(15m/1h)、EMA(9/21/50)、MACD、布林带、成交量比、支撑阻力位
- **加密货币专用 Prompt**：结构化输出趋势判断、概率预测、目标价位、止损位、交易建议
- **多数据源融合**：Polymarket 本地信号 + Binance 技术指标 + 市场报价，三源综合分析

### 移动端

访问 `/m` 路径即可使用移动端版本，与桌面版共存：

- 底部 Tab 栏导航（首页/BTC/体育/持仓/更多）
- 全宽卡片布局，触摸友好（44px 最小点击区域）
- 下单/卖出使用底部弹窗
- 涵盖所有核心功能

## 技术栈

### 后端

| 组件 | 技术 |
|------|------|
| 框架 | FastAPI + Uvicorn (async) |
| ORM | SQLAlchemy 2.0 (async) + aiosqlite |
| 数据库 | SQLite（默认，可切换 PostgreSQL） |
| 认证 | JWT (python-jose) + bcrypt |
| 加密 | Fernet (AES-128-CBC) + PBKDF2-HMAC-SHA256 |
| Polymarket | py-clob-client-v2（CLOB 交易）、Gamma API（市场发现）、Data API（持仓/交易） |
| AI | OpenAI 兼容 SDK，支持多提供商 |
| 定时任务 | APScheduler |
| HTTP 客户端 | httpx |

### 前端

| 组件 | 技术 |
|------|------|
| 框架 | Vue 3.5 (Composition API) + TypeScript |
| 构建 | Vite 6 |
| UI 库 | Element Plus 2.9 |
| 状态管理 | Pinia 2.2 |
| 路由 | Vue Router 4.4 |
| HTTP | Axios 1.7 |

## 项目结构

```
polytrad/
├── app/                          # Python 后端
│   ├── api/                      # 路由模块
│   │   ├── auth.py               # 注册、登录、JWT
│   │   ├── admin.py              # 用户管理、AI 配置
│   │   ├── wallet.py             # 钱包配置
│   │   ├── btc.py                # BTC 短周期交易
│   │   ├── sports.py             # 体育赛事
│   │   ├── hot.py                # 热门尾盘
│   │   ├── political.py          # 政治打新
│   │   ├── arbitrage.py          # 事件套利
│   │   ├── ai.py                 # AI 分析
│   │   └── notify.py             # 通知推送
│   ├── services/                 # 业务逻辑
│   │   ├── trading.py            # CLOB 交易（下单/撤单/卖出/同步）
│   │   ├── scanner.py            # 市场扫描器
│   │   ├── polymarket.py         # Polymarket API 客户端 + 标题翻译
│   │   ├── binance.py            # Binance API + 技术指标计算
│   │   ├── btc_signal.py         # BTC 本地信号分析
│   │   ├── ai_service.py         # AI 分析服务
│   │   ├── notification.py       # 推送通知
│   │   └── scheduler.py          # 定时任务
│   ├── models.py                 # 数据库模型
│   ├── schemas.py                # Pydantic 请求/响应模型
│   ├── crypto.py                 # 钱包/密钥加密
│   ├── config.py                 # 配置管理
│   ├── db.py                     # 数据库连接
│   ├── deps.py                   # FastAPI 依赖注入
│   └── main.py                   # 应用入口
├── frontend/                     # Vue 3 前端
│   ├── src/
│   │   ├── views/                # 桌面端页面（14 个）
│   │   ├── views/mobile/         # 移动端页面（11 个）
│   │   ├── api/index.ts          # API 封装
│   │   ├── stores/auth.ts        # 认证状态
│   │   └── router.ts             # 路由配置
│   └── vite.config.ts
├── requirements.txt              # Python 依赖
├── .env.example                  # 环境变量模板
├── deploy.sh                     # VPS 部署脚本
├── start-dev.sh                  # 开发环境启动
└── start.sh                      # 生产环境启动
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- npm 或 pnpm

### 1. 克隆项目

```bash
git clone https://github.com/w00c00/polytrad.git
cd polytrad
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少修改以下变量：

```env
# 加密主密钥（生成后不可更改，否则已加密数据无法解密）
POLYTRAD_MASTER_KEY=$(openssl rand -hex 32)

# JWT 密钥
JWT_SECRET=$(openssl rand -hex 32)

# 管理员账户
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password

# VPS 生产环境建议把数据库放到代码目录外，避免同步代码时覆盖用户/钱包数据
DATABASE_URL=sqlite+aiosqlite:////var/lib/polytrad/polytrad.db

# Polymarket 链 ID（137=主网，80002=测试网）
POLYMARKET_CHAIN_ID=137
```

### 3. 安装后端依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. 安装前端依赖并构建

```bash
cd frontend
npm install
npm run build
cd ..
```

### 5. 启动服务

**开发模式**（前后端分离，支持热重载）：

```bash
./start-dev.sh
# 后端: http://localhost:8000
# 前端: http://localhost:3000（自动代理 /api 到后端）
```

**生产模式**：

```bash
./start.sh
# 访问: http://localhost:8000
```

### VPS 同步注意事项

不要直接把本地项目目录完整覆盖到 VPS，否则本地的 `polytrad.db`、`.env` 可能覆盖生产库和生产密钥，导致用户、密码、钱包配置“重置”。推荐使用内置同步脚本：

```bash
./scripts/sync-to-vps.sh root@YOUR_SERVER:/opt/polytrad/
```

该脚本会排除 `.env`、`*.db`、`data/`、`venv/`、`frontend/node_modules/`、`frontend/dist/` 等运行时文件。VPS 生产数据库建议固定在 `/var/lib/polytrad/polytrad.db`，生产环境变量放在 `/etc/polytrad/polytrad.env`。

桌面版和移动版是同一个前端应用的两套路由：桌面版访问 `/`，移动版访问 `/m`。后端会把 `/m/*` 也返回同一个 `index.html`，由前端路由加载移动版页面。

首次启动会自动：
- 创建数据库表
- 创建管理员账户（从 .env 读取）

## 部署到 VPS

### 使用部署脚本

```bash
# 在 VPS 上执行
chmod +x deploy.sh
./deploy.sh
```

部署脚本会自动：
1. 安装系统依赖（Python、Nginx、Certbot）
2. 创建 Python 虚拟环境并安装依赖
3. 构建前端
4. 创建 systemd 服务（`polytrad.service`）
5. 配置 Nginx 反向代理

### 手动部署

```bash
# 1. 同步代码到 VPS
rsync -avz --exclude node_modules --exclude .git -e 'ssh -p PORT' ./ user@server:/opt/polytrad/

# 2. 在 VPS 上构建前端
ssh -p PORT user@server
cd /opt/polytrad/frontend && npm install && npm run build

# 3. 重启服务
systemctl restart polytrad
```

### SSL 证书

```bash
# 在 VPS 上执行
certbot --nginx -d your-domain.com
```

## API 端点

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册（需管理员审批） |
| POST | `/api/auth/login` | 登录，返回 JWT |
| GET | `/api/auth/me` | 获取当前用户信息 |
| POST | `/api/auth/change-password` | 修改密码 |

### BTC 短周期

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/btc/markets` | 获取 BTC 短周期市场列表 |
| GET | `/api/btc/market/{slug}` | 市场详情 + 订单簿 |
| POST | `/api/btc/order` | 下限价单（支持 usdc_amount 市价模式） |
| POST | `/api/btc/sell` | 卖出持仓（自动读 CLOB best bid） |
| POST | `/api/btc/predict` | AI 预测（本地信号 + Binance 指标 + AI） |
| GET | `/api/btc/positions` | 查看持仓 |
| GET | `/api/btc/orders` | 查看挂单 |
| DELETE | `/api/btc/order/{id}` | 撤单 |
| POST | `/api/btc/cancel-all` | 撤销所有挂单 |

### 体育赛事

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sports/events` | 获取赛事列表 |
| POST | `/api/sports/predict` | AI 赛事预测 |
| POST | `/api/sports/order` | 下单 |

### 热门尾盘 / 政治打新 / 事件套利

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/hot/scan` | 扫描热门尾盘 |
| POST | `/api/hot/order` | 尾盘下单 |
| GET | `/api/political/scan` | 扫描政治新盘 |
| POST | `/api/political/order` | 政治下单 |
| GET | `/api/arbitrage/scan` | 扫描套利机会 |
| POST | `/api/arbitrage/execute` | 执行套利 |

### AI 分析

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ai/providers` | 获取可用 AI 模型列表 |
| POST | `/api/ai/analyze` | 通用 AI 分析 |
| POST | `/api/ai/analyze-market` | 市场分析 |
| POST | `/api/ai/analyze-arbitrage` | 套利风险分析 |

### 通知

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/notify/config` | 获取通知配置 |
| POST | `/api/notify/config` | 保存通知配置 |
| POST | `/api/notify/test` | 测试推送 |
| POST | `/api/notify/trade-report` | 手动推送交易报告 |

## 定时任务

| 任务 | 频率 | 说明 |
|------|------|------|
| 热门尾盘扫描 | 每 2 小时 | 扫描即将到期的高成交量市场 |
| 政治新盘扫描 | 每 6 小时 | 扫描新创建的政治类市场 |
| 套利机会扫描 | 每 2 小时 | 扫描多结果事件的价格偏差 |
| 持仓报告 | 每天 0:00 | 推送持仓概览 + 盈亏 |
| 扫描结果清理 | 每天 3:00 | 清理 7 天前的扫描记录 |
| 订单状态同步 | 每 3 分钟 | 同步 CLOB 订单状态到本地数据库 |

## 安全设计

- **钱包私钥**：使用 Fernet (AES-128-CBC) + PBKDF2-HMAC-SHA256 加密存储，600,000 次迭代
- **API 密钥**：同样加密存储，支持 Polymarket API Key/Secret/Passphrase
- **JWT 认证**：所有 API 端点需要 Bearer Token，24 小时过期
- **用户审批**：注册后需管理员审批才能使用
- **CLOB 交易**：所有 CLOB 调用包装在 `asyncio.to_thread` 中，25 秒超时，避免阻塞事件循环
- **订单同步**：每 3 分钟自动同步 CLOB 订单状态，确保本地数据库与链上一致

## Polymarket 集成

### 三层 API

| API | 用途 | 认证 |
|-----|------|------|
| **Gamma API** | 市场发现、元数据、搜索 | 无需认证 |
| **Data API** | 持仓、交易历史、资产价值 | 无需认证 |
| **CLOB API** | 订单簿、下单、撤单 | 需要钱包签名 |

### 交易流程

1. **市价买入**：从 CLOB 实时读取 best ask，计算 size = usdc_amount / price，提交 GTC 订单
2. **卖出持仓**：从 CLOB 读取 best bid，clamp 到 tick_size，提交 SELL GTC 订单
3. **订单同步**：定时轮询 CLOB open_orders，对比本地 pending 订单，更新状态

### 标题翻译

内置 300+ 常见实体翻译（NBA 球队、足球国家队、网球运动员、政治人物等），自动将英文市场标题翻译为中文。

## 配置说明

### 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `POLYTRAD_MASTER_KEY` | 是 | - | 加密主密钥，生成后不可更改 |
| `DATABASE_URL` | 否 | `sqlite+aiosqlite:///./polytrad.db` | 数据库连接字符串；VPS 推荐 `sqlite+aiosqlite:////var/lib/polytrad/polytrad.db` |
| `JWT_SECRET` | 是 | - | JWT 签名密钥 |
| `ADMIN_USERNAME` | 否 | `admin` | 初始管理员用户名 |
| `ADMIN_PASSWORD` | 是 | - | 初始管理员密码 |
| `POLYMARKET_CHAIN_ID` | 否 | `137` | 链 ID（137=主网，80002=测试网） |
| `PORT` | 否 | `8000` | 服务端口 |
| `POLYMARKET_CLOB_HOST` | 否 | `https://clob.polymarket.com` | CLOB API 地址 |
| `POLYMARKET_GAMMA_HOST` | 否 | `https://gamma-api.polymarket.com` | Gamma API 地址 |
| `POLYMARKET_DATA_HOST` | 否 | `https://data-api.polymarket.com` | Data API 地址 |

### AI 模型配置

管理员可在后台（`/admin/system`）添加多个 AI 提供商：

| 提供商 | Base URL | 说明 |
|--------|----------|------|
| MiniMax | `https://api.minimax.chat/v1` | MiniMax 大模型 |
| OpenRouter | `https://openrouter.ai/api/v1` | 多模型聚合 |
| GLM | `https://open.bigmodel.cn/api/paas/v4` | 智谱清言 |
| 火山引擎 | `https://ark.cn-beijing.volces.com/api/v3` | 字节跳动豆包 |
| 自定义 | 用户配置 | 任意 OpenAI 兼容 API |

## 开发

### 启动开发环境

```bash
# 终端 1：后端（热重载）
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2：前端（热重载）
cd frontend
npm run dev
```

前端开发服务器运行在 `http://localhost:3000`，自动将 `/api` 请求代理到后端 `http://localhost:8000`。

### 数据库迁移

项目使用 SQLAlchemy 自动建表，无需手动迁移。首次启动时自动创建所有表。

如需重置数据库：

```bash
rm polytrad.db  # 本地开发
# VPS 生产环境是 /var/lib/polytrad/polytrad.db，删除前务必先备份
systemctl restart polytrad  # 或重新启动服务
```

## License

MIT
