from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User
from app.deps import get_current_user
from app.services.scanner import scan_arbitrage
from app.services.trading import place_limit_order
from app.services.polymarket import gamma_api

router = APIRouter(prefix="/api/arbitrage", tags=["事件套利"])


@router.get("/scan")
async def arbitrage_scan(
    threshold: float = Query(0.03, ge=0.01, le=0.5),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """扫描事件套利机会"""
    return await scan_arbitrage(db, threshold=threshold)


@router.get("/results")
async def arbitrage_results(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取扫描结果"""
    from sqlalchemy import select
    from app.models import ScanResult
    import json

    result = await db.execute(
        select(ScanResult).where(ScanResult.scan_type == "arbitrage")
        .order_by(ScanResult.id.desc()).limit(limit)
    )
    scans = result.scalars().all()
    return [{"id": s.id, "data": json.loads(s.market_data), "created_at": s.created_at} for s in scans]


@router.post("/execute")
async def arbitrage_execute(
    token_id: str,
    price: float,
    size: float,
    side: str,
    tick_size: str = "0.01",
    neg_risk: bool = True,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """执行套利交易"""
    try:
        return await place_limit_order(
            user, db,
            token_id=token_id, price=price, size=size,
            side=side, order_type="GTC",
            tick_size=tick_size,
        )
    except Exception as e:
        raise HTTPException(400, f"套利下单失败: {e}")
