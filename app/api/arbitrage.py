from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User
from app.deps import get_current_user
from app.services.scanner import scan_arbitrage
from app.services.opportunities import quick_buy_token

router = APIRouter(prefix="/api/arbitrage", tags=["事件套利"])


@router.get("/scan")
async def arbitrage_scan(
    threshold: float = Query(0.03, ge=0.01, le=0.5),
    budget: float = Query(100, ge=5, le=10000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """扫描事件套利机会"""
    return await scan_arbitrage(db, threshold=threshold, budget_usdc=budget)


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
    price: float = 0,
    size: float = 0,
    side: str = "BUY",
    tick_size: str = "0.01",
    neg_risk: bool = True,
    usdc_amount: float = 0,
    market_slug: str = "",
    condition_id: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """执行套利交易"""
    try:
        if side.upper() != "BUY":
            raise ValueError("篮子套利旧执行入口只允许 BUY；卖出请使用持仓/对冲页面")
        if not market_slug:
            raise ValueError("缺少 market_slug，无法做市场安全检查")
        return await quick_buy_token(
            user, db,
            token_id=token_id,
            amount_usdc=usdc_amount,
            size=size,
            limit_price=price,
            order_type="FOK",
            tick_size=tick_size,
            neg_risk=neg_risk,
            market_slug=market_slug,
            condition_id=condition_id,
        )
    except Exception as e:
        raise HTTPException(400, f"套利下单失败: {e}")
