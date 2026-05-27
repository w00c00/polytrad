from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User, Credential
from app.deps import get_current_user
from app.schemas import WalletSetupReq, WalletResp
from app.crypto import encrypt_secret
from app.services.trading import setup_wallet

router = APIRouter(prefix="/api/wallet", tags=["钱包"])


@router.post("/setup", response_model=WalletResp)
async def configure_wallet(req: WalletSetupReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # 检查是否已有活跃钱包
    result = await db.execute(
        select(Credential).where(Credential.user_id == user.id, Credential.is_active == True)
    )
    if result.scalar_one_or_none():
        raise HTTPException(400, "已有活跃钱包配置，请先停用后再新建")

    try:
        wallet_info = await setup_wallet(req.private_key, req.chain_id)
    except Exception as e:
        raise HTTPException(400, f"钱包初始化失败: {e}")

    cred = Credential(
        user_id=user.id,
        wallet_address=wallet_info["wallet_address"],
        funder_address=req.funder_address or wallet_info["wallet_address"],
        encrypted_private_key=encrypt_secret(req.private_key),
        encrypted_api_key=encrypt_secret(wallet_info["api_key"]),
        encrypted_api_secret=encrypt_secret(wallet_info["api_secret"]),
        encrypted_api_passphrase=encrypt_secret(wallet_info["api_passphrase"]),
        chain_id=req.chain_id,
        is_active=True,
    )
    db.add(cred)
    await db.commit()
    await db.refresh(cred)
    return cred


@router.get("/list", response_model=list[WalletResp])
async def list_wallets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Credential).where(Credential.user_id == user.id).order_by(Credential.id.desc())
    )
    return result.scalars().all()


@router.post("/{cid}/deactivate", response_model=WalletResp)
async def deactivate_wallet(cid: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Credential).where(Credential.id == cid, Credential.user_id == user.id)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(404, "钱包不存在")
    cred.is_active = False
    await db.commit()
    await db.refresh(cred)
    return cred


@router.post("/{cid}/activate", response_model=WalletResp)
async def activate_wallet(cid: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # 先停用所有其他钱包
    result = await db.execute(
        select(Credential).where(Credential.user_id == user.id, Credential.is_active == True)
    )
    for c in result.scalars().all():
        c.is_active = False

    result = await db.execute(
        select(Credential).where(Credential.id == cid, Credential.user_id == user.id)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(404, "钱包不存在")
    cred.is_active = True
    await db.commit()
    await db.refresh(cred)
    return cred
