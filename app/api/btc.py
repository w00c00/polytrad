import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User
from app.deps import get_current_user
from app.schemas import OrderReq, MarketOrderReq, SellReq, CancelOrderReq
from app.services.polymarket import gamma_api, clob_api, to_beijing_time, translate_title
from app.services.trading import place_limit_order, place_market_order, sell_position, cancel_order, get_open_orders, cancel_all_orders, get_usdc_balance
from app.services.scanner import scan_btc_short_markets

router = APIRouter(prefix="/api/btc", tags=["BTC短周期"])


@router.get("/markets")
async def list_btc_markets(user: User = Depends(get_current_user)):
    """搜索 BTC 相关市场（含短周期 5m/15m）"""
    short_markets = await scan_btc_short_markets(None)

    markets = await gamma_api.get_markets(active=True, closed=False, limit=100)
    btc_markets = [
        m for m in markets
        if any(kw in (m.get("question", "") + m.get("slug", "")).lower() for kw in ["btc", "bitcoin"])
    ]
    return {"short_markets": short_markets, "markets": btc_markets}


@router.get("/market/{slug}")
async def get_btc_market(slug: str, user: User = Depends(get_current_user)):
    """获取单个 BTC 市场详情 + 订单簿"""
    market = await gamma_api.get_market_by_slug(slug)
    if not market:
        # 可能是 event slug，尝试从 event 获取
        event = await gamma_api.get_event(slug)
        if not event:
            raise HTTPException(404, "市场不存在")
        # 取 event 的第一个 market
        markets = event.get("markets", [])
        if not markets:
            raise HTTPException(404, "市场不存在")
        market = markets[0]

    token_ids = market.get("clobTokenIds", [])
    if isinstance(token_ids, str):
        token_ids = json.loads(token_ids)

    orderbook = {}
    spread_info = {}
    for i, tid in enumerate(token_ids):
        label = "YES" if i == 0 else "NO"
        try:
            orderbook[label] = await clob_api.get_orderbook(tid)
            spread_info[label] = await clob_api.get_spread(tid)
        except Exception:
            pass

    return {"market": market, "orderbook": orderbook, "spread": spread_info}


@router.post("/order")
async def btc_place_order(req: OrderReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """下限价单。传 usdc_amount > 0 时自动从 CLOB 读盘口价"""
    try:
        result = await place_limit_order(
            user, db,
            token_id=req.token_id,
            price=req.price,
            size=req.size,
            side=req.side,
            order_type=req.order_type,
            tick_size=req.tick_size,
            neg_risk=req.neg_risk,
            market_slug=req.market_slug,
            condition_id=req.condition_id,
            usdc_amount=req.usdc_amount,
        )
        return result
    except Exception as e:
        raise HTTPException(400, f"下单失败: {e}")


@router.post("/market-order")
async def btc_market_order(req: MarketOrderReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """下市价单"""
    try:
        result = await place_market_order(
            user, db,
            token_id=req.token_id,
            amount=req.amount,
            side=req.side,
            order_type=req.order_type,
            tick_size=req.tick_size,
            neg_risk=req.neg_risk,
            market_slug=req.market_slug,
            condition_id=req.condition_id,
        )
        return result
    except Exception as e:
        raise HTTPException(400, f"下单失败: {e}")


@router.post("/sell")
async def btc_sell(req: SellReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """卖出持仓：自动读 CLOB best bid 并 clamp（避免前端用错价格）"""
    try:
        result = await sell_position(
            user, db,
            token_id=req.token_id,
            size=req.size,
            tick_size=req.tick_size,
            neg_risk=req.neg_risk,
            market_slug=req.market_slug,
            condition_id=req.condition_id,
        )
        return result
    except Exception as e:
        raise HTTPException(400, f"卖出失败: {e}")


@router.get("/positions")
async def btc_positions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """查看有效持仓"""
    from sqlalchemy import select
    from app.models import Credential
    from app.crypto import decrypt_secret

    result = await db.execute(select(Credential).where(Credential.user_id == user.id, Credential.is_active == True))
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(400, "未配置钱包")

    # 使用 funder 地址查询持仓（与上个项目一致，signature_type=3 时持仓归在 funder 下）
    addr = cred.funder_address or cred.wallet_address
    positions = await data_api.get_positions(addr)

    # 过滤已结算/已赎回的持仓
    def _float_or_zero(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    positions = [
        p for p in positions
        if _float_or_zero(p.get("size")) > 0.000001
        and not p.get("redeemable")
        and not p.get("redeemed")
    ]

    # 转换时间字段为北京时间 + 翻译标题
    for p in positions:
        if p.get("title"):
            p["title_zh"] = translate_title(p["title"])
        for key in ["createdAt", "updatedAt", "startDate", "endDate", "endDateIso"]:
            if key in p and p[key]:
                p[f"{key}_bj"] = to_beijing_time(str(p[key]))

    # 获取 USDC 余额
    try:
        balance = await get_usdc_balance(user, db)
    except Exception:
        balance = {}

    return {"positions": positions, "balance": balance}


@router.get("/orders")
async def btc_orders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """查看当前挂单"""
    try:
        orders = await get_open_orders(user, db)
        return {"orders": orders}
    except Exception as e:
        raise HTTPException(400, f"查询失败: {e}")


@router.delete("/order/{order_id}")
async def btc_cancel(order_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """撤单"""
    try:
        return await cancel_order(user, db, order_id)
    except Exception as e:
        raise HTTPException(400, f"撤单失败: {e}")


@router.post("/cancel-all")
async def btc_cancel_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """撤销所有挂单"""
    try:
        return await cancel_all_orders(user, db)
    except Exception as e:
        raise HTTPException(400, f"撤销失败: {e}")


@router.post("/predict")
async def btc_predict(
    ai_config_id: int,
    horizon_minutes: int = 15,
    market_question: str = "",
    up_price: float = 0.5,
    down_price: float = 0.5,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """BTC 短周期预测：本地技术分析 + Binance数据 + AI 综合判断"""
    from app.services.btc_signal import analyze_btc_signal
    from app.services.binance import binance_api
    from app.services.ai_service import get_active_ai_config, analyze

    # 1. 本地技术分析（Polymarket 动量模型）
    signal = await analyze_btc_signal(horizon_minutes)

    # 2. Binance 技术指标（RSI, EMA, MACD, 布林带等）
    binance_indicators = {}
    try:
        binance_indicators = await binance_api.get_market_indicator("BTCUSDT")
    except Exception as e:
        binance_indicators = {"error": f"Binance数据获取失败: {e}"}

    # 3. 本地结构化决策
    prob_up = signal["prob_up"]
    prob_down = signal["prob_down"]
    confidence_value = signal["confidence_value"]
    up_edge = prob_up - up_price
    down_edge = prob_down - down_price

    local_action = "不交易"
    local_edge = ""
    min_edge = 0.04
    if up_edge >= min_edge and confidence_value >= 0.25:
        local_action = "买UP"
        local_edge = f"UP概率高于买价约 {up_edge * 100:.1f}%"
    elif down_edge >= min_edge and confidence_value >= 0.25:
        local_action = "买DOWN"
        local_edge = f"DOWN概率高于买价约 {down_edge * 100:.1f}%"

    # 4. AI 综合分析（使用加密货币专用 prompt）
    ai_result = ""
    try:
        config = await get_active_ai_config(db, ai_config_id)

        # 构建加密货币专用分析 prompt
        market_info = {
            "horizon_minutes": horizon_minutes,
            "question": market_question,
            "up_price": up_price,
            "down_price": down_price,
        }

        from app.services.ai_service import build_crypto_prompt, CRYPTO_ANALYSIS_PROMPT
        enhanced_prompt = build_crypto_prompt(signal, binance_indicators, market_info)

        # 传入加密货币专用 system prompt
        ai_result = await analyze(config, enhanced_prompt, system_prompt=CRYPTO_ANALYSIS_PROMPT)
    except Exception as e:
        ai_result = f"AI 分析失败: {e}"

    return {
        "signal": signal,
        "binance": binance_indicators,
        "local": {
            "action": local_action,
            "edge": local_edge,
            "prob_up": prob_up,
            "prob_down": prob_down,
            "confidence": signal["confidence"],
        },
        "ai": ai_result,
    }


from app.services.polymarket import data_api
