import os
import signal
from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User, AIConfig
from app.deps import get_admin
from app.schemas import UserResp, AdminActionResp, AIConfigReq, AIConfigResp, ChangePasswordReq
from app.crypto import encrypt_secret

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/api/admin", tags=["管理员"])


@router.get("/users", response_model=list[UserResp])
async def list_users(status: str | None = None, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin)):
    q = select(User)
    if status:
        q = q.where(User.status == status)
    result = await db.execute(q.order_by(User.id))
    return result.scalars().all()


@router.post("/users/{uid}/approve", response_model=AdminActionResp)
async def approve_user(uid: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin)):
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    user.status = "approved"
    await db.commit()
    return AdminActionResp(success=True, message=f"已审核通过: {user.username}")


@router.post("/users/{uid}/reject", response_model=AdminActionResp)
async def reject_user(uid: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin)):
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    user.status = "rejected"
    await db.commit()
    return AdminActionResp(success=True, message=f"已拒绝: {user.username}")


@router.delete("/users/{uid}", response_model=AdminActionResp)
async def delete_user(uid: int, db: AsyncSession = Depends(get_db), admin: User = Depends(get_admin)):
    if uid == admin.id:
        raise HTTPException(400, "不能删除自己")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    await db.delete(user)
    await db.commit()
    return AdminActionResp(success=True, message=f"已删除: {user.username}")


@router.post("/users/{uid}/change-password", response_model=AdminActionResp)
async def admin_change_password(uid: int, req: ChangePasswordReq, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin)):
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    user.password_hash = pwd_ctx.hash(req.new_password)
    await db.commit()
    return AdminActionResp(success=True, message=f"已修改密码: {user.username}")


@router.post("/restart", response_model=AdminActionResp)
async def restart_service(_: User = Depends(get_admin)):
    os.kill(os.getpid(), signal.SIGHUP)
    return AdminActionResp(success=True, message="服务重启信号已发送")


# === AI 配置管理 ===
@router.get("/ai-configs", response_model=list[AIConfigResp])
async def list_ai_configs(db: AsyncSession = Depends(get_db), _: User = Depends(get_admin)):
    result = await db.execute(select(AIConfig).order_by(AIConfig.id))
    return result.scalars().all()


@router.post("/ai-configs", response_model=AIConfigResp)
async def create_ai_config(req: AIConfigReq, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin)):
    cfg = AIConfig(
        name=req.name,
        provider=req.provider,
        encrypted_api_key=encrypt_secret(req.api_key),
        model_name=req.model_name,
        base_url=req.base_url,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.put("/ai-configs/{cid}", response_model=AIConfigResp)
async def update_ai_config(cid: int, req: AIConfigReq, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin)):
    result = await db.execute(select(AIConfig).where(AIConfig.id == cid))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, "配置不存在")
    cfg.name = req.name
    cfg.provider = req.provider
    cfg.encrypted_api_key = encrypt_secret(req.api_key)
    cfg.model_name = req.model_name
    cfg.base_url = req.base_url
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.delete("/ai-configs/{cid}", response_model=AdminActionResp)
async def delete_ai_config(cid: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin)):
    result = await db.execute(select(AIConfig).where(AIConfig.id == cid))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, "配置不存在")
    await db.delete(cfg)
    await db.commit()
    return AdminActionResp(success=True, message=f"已删除 AI 配置: {cfg.name}")
