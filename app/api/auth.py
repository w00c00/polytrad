from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.config import get_settings
from app.models import User
from app.schemas import RegisterReq, LoginReq, TokenResp, UserResp, SelfChangePasswordReq, AdminActionResp
from app.deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["认证"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/register", response_model=UserResp)
async def register(req: RegisterReq, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        raise HTTPException(400, "用户名已存在")
    user = User(
        username=req.username,
        password_hash=pwd_ctx.hash(req.password),
        role="user",
        status="pending",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 通知管理员有新用户注册
    try:
        admins = (await db.execute(select(User).where(User.role == "admin", User.status == "approved"))).scalars().all()
        from app.services.notification import notify_user
        for admin in admins:
            await notify_user(db, admin, "新用户注册", f"用户名: {req.username}\n状态: 待审核\n请及时处理。")
    except Exception:
        pass

    return user


@router.post("/login", response_model=TokenResp)
async def login(req: LoginReq, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not pwd_ctx.verify(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if user.status != "approved":
        raise HTTPException(403, f"账户状态: {user.status}，等待管理员审核")
    expire = datetime.now(timezone.utc) + timedelta(minutes=get_settings().jwt_expire_minutes)
    token = jwt.encode({"sub": str(user.id), "exp": expire}, get_settings().jwt_secret, algorithm=get_settings().jwt_algorithm)
    return TokenResp(access_token=token)


@router.get("/me", response_model=UserResp)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", response_model=AdminActionResp)
async def change_password(req: SelfChangePasswordReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not pwd_ctx.verify(req.old_password, user.password_hash):
        raise HTTPException(400, "原密码错误")
    user.password_hash = pwd_ctx.hash(req.new_password)
    await db.commit()
    return AdminActionResp(success=True, message="密码修改成功")
