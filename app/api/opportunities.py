from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services.opportunity_advisor import build_opportunity_advice
from app.services.intelligence import scan_news_catalysts, scan_smart_money, scan_sports_schedule_radar
from app.services.notification import notify_user
from app.services.opportunities import (
    basket_precheck,
    btc_momentum_alerts,
    execute_basket_buy,
    execute_basket_shadow_orders,
    execute_cross_event_hedge,
    execute_hedge_close_batch,
    execute_slippage_batch_buy,
    hedge_suggestions,
    place_reward_maker_quote,
    quick_buy_token,
    quick_sell_token,
    scan_cross_event_spreads,
    scan_low_slippage_markets,
    scan_resolution_watch,
    scan_reward_making_markets,
)
from app.services.trading import cancel_all_orders

router = APIRouter(prefix="/api/opportunities", tags=["机会扫描"])


class QuickBuyReq(BaseModel):
    token_id: str
    amount: float = Field(0, ge=0, le=10000)
    size: float = Field(0, ge=0)
    limit_price: float = Field(0, ge=0, le=1)
    order_type: str = "FOK"
    tick_size: str = "0.01"
    neg_risk: bool = False
    market_slug: str = ""
    condition_id: str = ""


class QuickSellReq(BaseModel):
    token_id: str
    size: float = Field(..., ge=5)
    tick_size: str = "0.01"
    neg_risk: bool = False
    market_slug: str = ""
    condition_id: str = ""


class SlippageBatchBuyReq(BaseModel):
    items: list[dict]
    amount: float = Field(25, ge=1, le=1000)
    max_slippage_pct: float = Field(2.0, ge=0.1, le=20)


class HedgeCloseReq(BaseModel):
    items: list[dict]
    fraction: float = Field(1.0, gt=0, le=1)


class BasketBuyReq(BaseModel):
    event_slug: str
    budget: float = Field(100, ge=5, le=10000)
    min_profit_pct: float = Field(0.2, ge=0, le=50)


class BasketShadowReq(BaseModel):
    event_slug: str
    budget: float = Field(100, ge=5, le=10000)
    max_price: float = Field(0.03, gt=0, le=0.5)
    improve_ticks: int = Field(1, ge=0, le=10)


class CrossHedgeReq(BaseModel):
    buy_candidate: dict
    sell_reference: dict
    amount: float = Field(0, ge=0, le=10000)
    min_profit_pct: float = Field(0.2, ge=0, le=50)


class MakerQuoteReq(BaseModel):
    market_slug: str
    amount_per_side: float = Field(10, ge=1, le=10000)
    improve_ticks: int = Field(0, ge=0, le=5)


class OpportunityAdviceReq(BaseModel):
    kind: str
    item: dict
    amount: float = Field(0, ge=0, le=10000)
    context: dict = Field(default_factory=dict)


@router.post("/advice")
async def opportunity_advice(
    req: OpportunityAdviceReq,
    user: User = Depends(get_current_user),
):
    return build_opportunity_advice(req.kind, req.item, req.amount, req.context)


@router.get("/slippage")
async def slippage_scan(
    amount: float = Query(25, ge=1, le=1000),
    max_slippage_pct: float = Query(2.0, ge=0.1, le=20),
    min_volume_24h: float = Query(5000, ge=0),
    max_candidates: int = Query(120, ge=20, le=500),
    user: User = Depends(get_current_user),
):
    return await scan_low_slippage_markets(amount, max_slippage_pct, min_volume_24h, max_candidates)


@router.get("/cross-event")
async def cross_event_scan(
    min_spread: float = Query(0.08, ge=0.01, le=0.8),
    max_candidates: int = Query(300, ge=50, le=1000),
    budget: float = Query(100, ge=1, le=10000),
    user: User = Depends(get_current_user),
):
    return await scan_cross_event_spreads(min_spread, max_candidates, budget)


@router.get("/rewards")
async def rewards_scan(
    max_candidates: int = Query(300, ge=50, le=1000),
    user: User = Depends(get_current_user),
):
    return await scan_reward_making_markets(max_candidates)


@router.get("/resolution-watch")
async def resolution_watch(
    hours: int = Query(12, ge=1, le=168),
    min_volume_24h: float = Query(1000, ge=0),
    user: User = Depends(get_current_user),
):
    return await scan_resolution_watch(hours, min_volume_24h)


@router.get("/news-catalysts")
async def news_catalysts(
    category: str = Query("politics", pattern="^(all|politics|sports|crypto)$"),
    lookback_hours: int = Query(48, ge=6, le=168),
    max_candidates: int = Query(24, ge=5, le=80),
    user: User = Depends(get_current_user),
):
    return await scan_news_catalysts(category, lookback_hours, max_candidates)


@router.get("/sports-schedule")
async def sports_schedule(
    days_ahead: int = Query(7, ge=1, le=30),
    max_candidates: int = Query(120, ge=20, le=300),
    include_unsupported: bool = Query(True),
    user: User = Depends(get_current_user),
):
    return await scan_sports_schedule_radar(max_candidates, days_ahead, include_unsupported)


@router.get("/smart-money")
async def smart_money(
    lookback_hours: int = Query(24, ge=1, le=168),
    limit: int = Query(2500, ge=50, le=5000),
    min_notional: float = Query(50, ge=1, le=100000),
    top_wallets: int = Query(30, ge=3, le=80),
    user: User = Depends(get_current_user),
):
    return await scan_smart_money(lookback_hours, limit, min_notional, top_wallets)


@router.get("/basket-precheck")
async def precheck_basket(
    event_slug: str,
    budget: float = Query(100, ge=5, le=10000),
    user: User = Depends(get_current_user),
):
    try:
        return await basket_precheck(event_slug, budget)
    except Exception as e:
        raise HTTPException(400, f"篮子预检失败: {e}")


@router.post("/basket-buy")
async def buy_basket(
    req: BasketBuyReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await execute_basket_buy(user, db, req.event_slug, req.budget, req.min_profit_pct)
    except Exception as e:
        raise HTTPException(400, f"篮子一键买入失败: {e}")


@router.post("/basket-shadow")
async def shadow_basket(
    req: BasketShadowReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await execute_basket_shadow_orders(
            user,
            db,
            req.event_slug,
            req.budget,
            req.max_price,
            req.improve_ticks,
        )
    except Exception as e:
        raise HTTPException(400, f"影子挂单失败: {e}")


@router.post("/slippage-batch-buy")
async def slippage_batch_buy(
    req: SlippageBatchBuyReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await execute_slippage_batch_buy(user, db, req.items, req.amount, req.max_slippage_pct)
    except Exception as e:
        raise HTTPException(400, f"盘口滑点批量买入失败: {e}")


@router.post("/cross-hedge-buy")
async def cross_hedge_buy(
    req: CrossHedgeReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await execute_cross_event_hedge(
            user,
            db,
            req.buy_candidate,
            req.sell_reference,
            req.amount,
            req.min_profit_pct,
        )
    except Exception as e:
        raise HTTPException(400, f"同题价差双边套利失败: {e}")


@router.post("/quick-buy")
async def quick_buy(
    req: QuickBuyReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await quick_buy_token(
            user, db,
            token_id=req.token_id,
            amount_usdc=req.amount,
            size=req.size,
            limit_price=req.limit_price,
            order_type=req.order_type,
            tick_size=req.tick_size,
            neg_risk=req.neg_risk,
            market_slug=req.market_slug,
            condition_id=req.condition_id,
        )
    except Exception as e:
        raise HTTPException(400, f"快捷买入失败: {e}")


@router.post("/quick-sell")
async def quick_sell(
    req: QuickSellReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await quick_sell_token(
            user, db,
            token_id=req.token_id,
            size=req.size,
            tick_size=req.tick_size,
            neg_risk=req.neg_risk,
            market_slug=req.market_slug,
            condition_id=req.condition_id,
        )
    except Exception as e:
        raise HTTPException(400, f"快捷卖出失败: {e}")


@router.post("/maker-quote")
async def maker_quote(
    req: MakerQuoteReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await place_reward_maker_quote(user, db, req.market_slug, req.amount_per_side, req.improve_ticks)
    except Exception as e:
        raise HTTPException(400, f"奖励做市委托失败: {e}")


@router.post("/cancel-all")
async def cancel_all_open_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await cancel_all_orders(user, db)
    except Exception as e:
        raise HTTPException(400, f"紧急撤单失败: {e}")


@router.post("/hedge-close")
async def hedge_close(
    req: HedgeCloseReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await execute_hedge_close_batch(user, db, req.items, req.fraction)
    except Exception as e:
        raise HTTPException(400, f"批量平仓失败: {e}")


@router.get("/btc-alerts")
async def btc_alerts(
    min_edge: float = Query(0.04, ge=0.01, le=0.5),
    user: User = Depends(get_current_user),
):
    return await btc_momentum_alerts(min_edge)


@router.post("/btc-alerts/notify")
async def notify_btc_alerts(
    min_edge: float = Query(0.04, ge=0.01, le=0.5),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alerts = await btc_momentum_alerts(min_edge)
    if not alerts:
        return {"success": True, "message": "暂无满足条件的 BTC 动量提醒", "count": 0}
    lines = []
    for a in alerts[:8]:
        lines.append(f"• {a['series_label']} {a['action']} edge {a['edge'] * 100:.1f}%")
        lines.append(f"  {a['title_zh']} 截止 {a.get('end_time_bj') or '-'}")
    await notify_user(db, user, f"BTC 动量提醒 - {len(alerts)} 个", "\n".join(lines))
    return {"success": True, "message": "已发送提醒", "count": len(alerts)}


@router.get("/hedges")
async def hedges(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await hedge_suggestions(user, db)
    except Exception as e:
        raise HTTPException(400, f"持仓对冲建议失败: {e}")
