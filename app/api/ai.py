from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User, AIConfig
from app.deps import get_current_user
from app.schemas import AIAnalyzeReq, AIMarketAnalyzeReq, AIConfigResp
from app.services.ai_service import get_active_ai_config, analyze, analyze_market, analyze_arbitrage
from app.services.polymarket import gamma_api

router = APIRouter(prefix="/api/ai", tags=["AI分析"])


@router.get("/providers", response_model=list[AIConfigResp])
async def list_providers(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取可用 AI 提供商"""
    result = await db.execute(select(AIConfig).where(AIConfig.is_active == True))
    return result.scalars().all()


@router.post("/analyze")
async def ai_analyze(req: AIAnalyzeReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """通用 AI 分析"""
    config = await get_active_ai_config(db, req.ai_config_id)
    result = await analyze(config, req.prompt, req.system_prompt)
    return {"result": result}


@router.post("/analyze-market")
async def ai_analyze_market(req: AIMarketAnalyzeReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """市场专用分析"""
    market = await gamma_api.get_market_by_slug(req.market_slug)
    if not market:
        # 尝试作为 event slug
        market = await gamma_api.get_event(req.market_slug)
    if not market:
        raise HTTPException(404, "市场不存在")

    config = await get_active_ai_config(db, req.ai_config_id)
    result = await analyze_market(config, market, req.question)
    return {"slug": req.market_slug, "analysis": result}


@router.post("/analyze-arbitrage")
async def ai_analyze_arbitrage(
    ai_config_id: int,
    event_slug: str,
    yes_sum: float,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """套利风险分析"""
    event = await gamma_api.get_event(event_slug)
    if not event:
        raise HTTPException(404, "事件不存在")

    config = await get_active_ai_config(db, ai_config_id)
    result = await analyze_arbitrage(config, event, yes_sum)
    return {"slug": event_slug, "analysis": result}
