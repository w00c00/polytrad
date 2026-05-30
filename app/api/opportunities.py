from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services.notification import notify_user
from app.services.opportunities import (
    basket_precheck,
    btc_momentum_alerts,
    hedge_suggestions,
    scan_cross_event_spreads,
    scan_low_slippage_markets,
    scan_resolution_watch,
    scan_reward_making_markets,
)

router = APIRouter(prefix="/api/opportunities", tags=["机会扫描"])


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
    user: User = Depends(get_current_user),
):
    return await scan_cross_event_spreads(min_spread, max_candidates)


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
