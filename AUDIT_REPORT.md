# PolyTrad 项目全面审计报告

## 严重 Bug（必须修复）

### 1. Positions.vue 使用旧的响应格式
- **文件**: `frontend/src/views/Positions.vue:50`
- **问题**: `portfolio.value = data.portfolio_value` — 后端已改为返回 `data.balance`，这里还在读 `portfolio_value`，导致持仓总价值显示为空
- **同时**: 模板里用 `portfolio.value` 但新的 balance 格式是 `{balance: 123.45}` 结构，需要解析

### 2. Dashboard.vue 使用旧的响应格式
- **文件**: `frontend/src/views/Dashboard.vue:65`
- **问题**: `positions.value = data.positions || []` 这行没问题，但 Dashboard 没有显示余额/总价值信息，且没有过滤已结算持仓（虽然后端已过滤）

### 3. 定时持仓报告用 wallet_address 而非 funder_address
- **文件**: `app/services/scheduler.py:66`
- **问题**: `data_api.get_positions(cred.wallet_address)` — 应该用 `cred.funder_address or cred.wallet_address`，和 btc.py 保持一致。signature_type=3 时用 wallet_address 查不到持仓

### 4. 定时持仓报告解析 value 格式错误
- **文件**: `app/services/scheduler.py:68`
- **问题**: `float(value.get("value", 0))` — Polymarket Data API 的 `/value` 返回的是数组 `[{value: 0.5}]`，不是 dict。会直接报 AttributeError 崩溃

### 5. Positions.vue 显示 `pnl` 字段但 API 返回 `cashPnl`
- **文件**: `frontend/src/views/Positions.vue:27`
- **问题**: 模板用 `row.pnl`，但 Polymarket Data API 返回的字段名是 `cashPnl`。导致盈亏列永远显示 $0.00

### 6. WalletResp schema 缺少 funder_address 字段
- **文件**: `app/schemas.py:38-45`
- **问题**: Settings 页面的钱包表格尝试显示 `funder_address` 列，但 `WalletResp` 没有这个字段，所以永远显示空

---

## 中等问题（应该修复）

### 7. 套利执行端点传了 neg_risk 给 PartialCreateOrderOptions
- **文件**: `app/api/arbitrage.py:59`
- **问题**: `neg_risk=neg_risk` 传给了 `place_limit_order`，虽然 `place_limit_order` 内部没用它（已经不传给 `PartialCreateOrderOptions`），但参数签名容易误导。应清理掉 `neg_risk` 参数或在函数内完全忽略

### 8. ScanResult 表无限增长，无清理机制
- **文件**: `app/services/scanner.py` (所有 scan 函数)
- **问题**: 每次扫描都 INSERT 一条 ScanResult，没有 TTL 或清理。长时间运行后表会非常大
- **建议**: 定时清理超过 7 天的记录，或限制每个 scan_type 只保留最近 N 条

### 9. Admin restart 用 SIGHUP 信号，uvicorn 默认不处理
- **文件**: `app/api/admin.py:75`
- **问题**: `os.kill(os.getpid(), signal.SIGHUP)` — uvicorn 默认不响应 SIGHUP，重启按钮实际上不会重启服务
- **建议**: 改为 `os.kill(os.getpid(), signal.SIGTERM)` 配合 systemd 的 `Restart=always`，或用 uvicorn 的 reload 机制

### 10. CORS 配置 allow_origins=["*"] + allow_credentials=True
- **文件**: `app/main.py:51-57`
- **问题**: CORS 规范不允许 `Allow-Origin: *` 和 `Allow-Credentials: true` 同时存在。目前前后端同源所以没问题，但如果将来分离部署会出错

### 11. AIAnalysis.vue slug 输入没有说明文字
- **文件**: `frontend/src/views/AIAnalysis.vue:13-14`
- **问题**: "市场 Slug" 输入框没有说明 slug 从哪里获取。应该加 tooltip 或 placeholder 说明

### 12. AIAnalysis.vue 没有 watch 自动选中逻辑
- **文件**: `frontend/src/views/AIAnalysis.vue:81`
- **问题**: 其他 5 个页面都加了 `watch(aiProviders, ...)` 自动选中逻辑，但 AIAnalysis.vue 是在 onMounted 里直接 `if (data.length > 0) form.ai_config_id = data[0].id`。功能上能工作但逻辑不一致

### 13. Dashboard 最近交易不加载
- **文件**: `frontend/src/views/Dashboard.vue:63-68`
- **问题**: `trades` ref 初始化为空数组，但 onMounted 只加载了 positions，没有加载 trades。"最近交易"表格永远为空
- **后端也没有列出交易历史的 API 端点**

### 14. scan_sports_markets 不保存 ScanResult
- **文件**: `app/services/scanner.py:259-300`
- **问题**: 其他 scan 函数都 `db.add(ScanResult(...))` 并 commit，但 `scan_sports_markets` 没有。不一致

---

## 轻微问题（可选修复）

### 15. Trade.condition_id 是 NOT NULL 但经常传空字符串
- **文件**: `app/models.py:70`, `app/services/trading.py:123`
- **问题**: model 定义 `condition_id: NOT NULL`，但下单时经常传 `condition_id=""`。SQLite 允许但 PostgreSQL 会报错

### 16. 没有登录速率限制
- **文件**: `app/api/auth.py:34`
- **问题**: 登录接口没有防暴力破解机制

### 17. 前端空 catch 块吞掉所有错误
- **文件**: 几乎所有 Vue 组件的 `catch {}`
- **问题**: API 调用失败时用户看不到任何错误提示（虽然 axios interceptor 会弹 ElMessage.error，但某些场景可能不够）

### 18. BTC 短周期扫描串行请求 Gamma API
- **文件**: `app/services/scanner.py:58-62`
- **问题**: 2 个 series × 7 个 offset = 14 次串行 HTTP 请求，扫描速度慢
- **建议**: 用 `asyncio.gather` 并发请求

### 19. hot/political/sports 下单 FOK 路径金额计算
- **文件**: `app/api/hot.py:54`, `app/api/political.py:44`, `app/api/sports.py:61`
- **问题**: `amount=req.size * req.price` — 前端已经把 USDC 转成了 shares（size = usdc / price），所以 `size * price` ≈ 原始 USDC 金额。数学上是对的，但语义上 confusing

### 20. Settings 页面 funder_address 输入框没有说明
- **文件**: `frontend/src/views/Settings.vue:27-28`
- **问题**: "Funder 地址" 输入框没有说明这是什么、从哪里获取。新用户可能不知道要填 MetaMask 的充值地址

---

## 总结

| 级别 | 数量 | 说明 |
|------|------|------|
| 严重 | 6 | 功能不可用或数据错误 |
| 中等 | 8 | 功能缺陷或潜在问题 |
| 轻微 | 6 | 体验/一致性问题 |

**最优先修复**: #1, #3, #4, #5 — 这几个会导致持仓页面完全不能用
