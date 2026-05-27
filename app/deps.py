from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.config import get_settings
from app.models import User

security = HTTPBearer()


async def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(cred.credentials, get_settings().jwt_secret, algorithms=[get_settings().jwt_algorithm])
        uid: int = payload.get("sub")
        if uid is None:
            raise HTTPException(status_code=401, detail="无效 token")
    except JWTError:
        raise HTTPException(status_code=401, detail="无效 token")

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user or user.status != "approved":
        raise HTTPException(status_code=401, detail="用户未审核或不存在")
    return user


async def get_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
