from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User
from app.deps import get_current_user
from app.schemas import OrderReq
from app.services.scanner import scan_new_political_markets
from app.services.trading import place_limit_order
from fastapi import HTTPException

router = APIRouter(prefix="/api/political", tags=["政治打新"])


@router.get("/scan")
async def political_scan(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """扫描新创建的政治类市场"""
    return await scan_new_political_markets(db)


@router.get("/results")
async def political_results(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取扫描结果"""
    from sqlalchemy import select
    from app.models import ScanResult
    import json

    result = await db.execute(
        select(ScanResult).where(ScanResult.scan_type == "new_political")
        .order_by(ScanResult.id.desc()).limit(limit)
    )
    scans = result.scalars().all()
    return [{"id": s.id, "data": json.loads(s.market_data), "created_at": s.created_at} for s in scans]


@router.post("/order")
async def political_order(req: OrderReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """下单"""
    try:
        if req.usdc_amount > 0 or req.order_type == "FOK":
            # 市价路径：优先使用 usdc_amount
            usdc = req.usdc_amount if req.usdc_amount > 0 else (req.size * req.price)
            if usdc <= 0:
                raise HTTPException(400, "下单金额必须大于 0")
            return await place_limit_order(
                user, db,
                token_id=req.token_id, price=0, size=0,
                side=req.side, order_type="GTC",
                tick_size=req.tick_size,
                neg_risk=req.neg_risk,
                market_slug=req.market_slug,
                condition_id=req.condition_id,
                usdc_amount=usdc,
            )
        return await place_limit_order(
            user, db,
            token_id=req.token_id, price=req.price, size=req.size,
            side=req.side, order_type=req.order_type,
            tick_size=req.tick_size,
            neg_risk=req.neg_risk,
            market_slug=req.market_slug,
            condition_id=req.condition_id,
            usdc_amount=req.usdc_amount,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"下单失败: {e}")
