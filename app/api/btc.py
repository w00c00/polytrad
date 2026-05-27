import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User
from app.deps import get_current_user
from app.schemas import OrderReq, MarketOrderReq, SellReq, CancelOrderReq
from app.services.polymarket import gamma_api, clob_api, data_api
from app.services.trading import place_limit_order, place_market_order, cancel_order, get_open_orders, cancel_all_orders

router = APIRouter(prefix="/api/btc", tags=["BTC短周期"])


@router.get("/markets")
async def list_btc_markets(user: User = Depends(get_current_user)):
    """搜索 BTC 相关市场"""
    events = await gamma_api.search("bitcoin BTC")
    # 也搜索 slug 中含 btc/bitcoin 的活跃市场
    markets = await gamma_api.get_markets(active=True, closed=False, limit=100)
    btc_markets = [
        m for m in markets
        if any(kw in (m.get("question", "") + m.get("slug", "")).lower() for kw in ["btc", "bitcoin"])
    ]
    return {"events": events, "markets": btc_markets}


@router.get("/market/{slug}")
async def get_btc_market(slug: str, user: User = Depends(get_current_user)):
    """获取单个 BTC 市场详情 + 订单簿"""
    market = await gamma_api.get_market_by_slug(slug)
    if not market:
        raise HTTPException(404, "市场不存在")

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
    """下限价单"""
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
        )
        return result
    except Exception as e:
        raise HTTPException(400, f"下单失败: {e}")


@router.post("/sell")
async def btc_sell(req: SellReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """快速卖出"""
    try:
        result = await place_market_order(
            user, db,
            token_id=req.token_id,
            amount=req.amount,
            side="SELL",
            order_type=req.order_type,
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

    positions = await data_api.get_positions(cred.wallet_address)
    value = await data_api.get_value(cred.wallet_address)
    return {"positions": positions, "portfolio_value": value}


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
        raise HTTPException(400, f"撤单失败: {e}")
