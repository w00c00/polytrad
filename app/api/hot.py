from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User
from app.deps import get_current_user
from app.schemas import OrderReq
from app.services.scanner import scan_hot_markets, scan_sports_markets
from app.services.trading import place_limit_order, place_market_order

router = APIRouter(prefix="/api/hot", tags=["热门尾盘"])


@router.get("/scan")
async def hot_scan(
    hours: int = Query(24, ge=1, le=168),
    min_volume: float = Query(10000, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """扫描即将到期的热门市场"""
    return await scan_hot_markets(db, hours_until_expiry=hours, min_volume=min_volume)


@router.get("/results")
async def hot_results(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取最近的扫描结果"""
    from sqlalchemy import select
    from app.models import ScanResult
    import json

    result = await db.execute(
        select(ScanResult).where(ScanResult.scan_type == "hot")
        .order_by(ScanResult.id.desc()).limit(limit)
    )
    scans = result.scalars().all()
    return [{"id": s.id, "data": json.loads(s.market_data), "created_at": s.created_at} for s in scans]


@router.get("/sports")
async def hot_sports(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """体育类尾盘"""
    return await scan_sports_markets(db)


@router.post("/order")
async def hot_order(req: OrderReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """快速下单"""
    try:
        if req.order_type == "FOK":
            return await place_market_order(
                user, db,
                token_id=req.token_id, amount=req.size * req.price,
                side=req.side, order_type="FOK",
            )
        return await place_limit_order(
            user, db,
            token_id=req.token_id, price=req.price, size=req.size,
            side=req.side, order_type=req.order_type,
            tick_size=req.tick_size, neg_risk=req.neg_risk,
        )
    except Exception as e:
        raise HTTPException(400, f"下单失败: {e}")
