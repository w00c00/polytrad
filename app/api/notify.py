import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User, NotificationConfig
from app.deps import get_current_user
from app.schemas import NotifyConfigReq, NotifyTestReq
from app.crypto import encrypt_secret, decrypt_secret
from app.services.notification import test_serverchan, test_telegram

router = APIRouter(prefix="/api/notify", tags=["推送"])


@router.get("/config")
async def get_notify_config(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取推送配置 (隐藏敏感信息)"""
    result = await db.execute(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id)
    )
    configs = result.scalars().all()
    return [
        {
            "id": c.id,
            "channel": c.channel,
            "is_active": c.is_active,
            "masked": True,  # 不返回明文 token
        }
        for c in configs
    ]


@router.post("/config")
async def save_notify_config(req: NotifyConfigReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """保存推送配置"""
    # 验证配置格式
    if req.channel == "serverchan" and "sendkey" not in req.config:
        raise HTTPException(400, "方糖配置需要 sendkey")
    if req.channel == "telegram" and ("bot_token" not in req.config or "chat_id" not in req.config):
        raise HTTPException(400, "Telegram 配置需要 bot_token 和 chat_id")

    # 检查是否已有同渠道配置
    result = await db.execute(
        select(NotificationConfig).where(
            NotificationConfig.user_id == user.id,
            NotificationConfig.channel == req.channel,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.encrypted_config = encrypt_secret(json.dumps(req.config))
        existing.is_active = True
    else:
        cfg = NotificationConfig(
            user_id=user.id,
            channel=req.channel,
            encrypted_config=encrypt_secret(json.dumps(req.config)),
            is_active=True,
        )
        db.add(cfg)

    await db.commit()
    return {"success": True, "message": f"{req.channel} 推送配置已保存"}


@router.delete("/config/{cid}")
async def delete_notify_config(cid: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """删除推送配置"""
    result = await db.execute(
        select(NotificationConfig).where(NotificationConfig.id == cid, NotificationConfig.user_id == user.id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, "配置不存在")
    await db.delete(cfg)
    await db.commit()
    return {"success": True}


@router.post("/test")
async def test_notify(req: NotifyTestReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """测试推送"""
    result = await db.execute(
        select(NotificationConfig).where(
            NotificationConfig.user_id == user.id,
            NotificationConfig.channel == req.channel,
            NotificationConfig.is_active == True,
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, f"未配置 {req.channel} 推送")

    config_data = json.loads(decrypt_secret(cfg.encrypted_config))

    if req.channel == "serverchan":
        resp = await test_serverchan(config_data["sendkey"])
    elif req.channel == "telegram":
        resp = await test_telegram(config_data["bot_token"], config_data["chat_id"])
    else:
        raise HTTPException(400, f"不支持的渠道: {req.channel}")

    return resp
