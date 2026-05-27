import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User, AIConfig
from app.deps import get_current_user
from app.schemas import OrderReq
from app.services.polymarket import gamma_api, clob_api
from app.services.trading import place_limit_order, place_market_order
from app.services.scanner import scan_sports_markets
from app.services.ai_service import get_active_ai_config, analyze_market

router = APIRouter(prefix="/api/sports", tags=["体育赛事"])


@router.get("/events")
async def list_sports_events(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取体育赛事列表"""
    return await scan_sports_markets(db)


@router.get("/event/{slug}")
async def get_sports_event(slug: str, user: User = Depends(get_current_user)):
    """获取单个赛事详情"""
    event = await gamma_api.get_event(slug)
    if not event:
        raise HTTPException(404, "赛事不存在")

    for m in event.get("markets", []):
        token_ids = m.get("clobTokenIds", [])
        if isinstance(token_ids, str):
            token_ids = json.loads(token_ids)
        for i, tid in enumerate(token_ids):
            try:
                mid = await clob_api.get_midpoint(tid)
                label = "YES" if i == 0 else "NO"
                m[f"{label}_mid"] = mid
            except Exception:
                pass

    return event


@router.post("/predict")
async def predict(ai_config_id: int, slug: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AI 概率预测"""
    event = await gamma_api.get_event(slug)
    if not event:
        raise HTTPException(404, "赛事不存在")

    config = await get_active_ai_config(db, ai_config_id)
    result = await analyze_market(config, event, "分析这场体育赛事各结果的胜率，给出概率预测和下注建议。")
    return {"slug": slug, "analysis": result}


@router.post("/order")
async def sports_order(req: OrderReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """赛事下单"""
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
