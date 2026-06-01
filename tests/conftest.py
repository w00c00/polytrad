# PolyTrad 测试配置
import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 设置测试环境变量（必须在导入 app 之前）
os.environ["POLYTRAD_MASTER_KEY"] = "test-master-key-for-ci-only-32chars!"
os.environ["JWT_SECRET"] = "test-jwt-secret-for-ci-only-32chars!"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["POLYMARKET_CHAIN_ID"] = "80002"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.db import Base
from app.main import app, pwd_ctx


# 测试数据库 URL（使用内存 SQLite）
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# 创建测试引擎
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def setup_db():
    """创建测试数据库表"""
    # 导入所有模型以确保它们被注册
    from app.models import User, Credential, Trade, AIConfig, ScanResult, NotificationConfig

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(setup_db) -> AsyncGenerator[AsyncClient, None]:
    """提供测试 HTTP 客户端"""

    from app.db import get_db

    async def override_get_db_async():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db_async

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


async def _ensure_user(username: str, password: str, role: str = "user", status: str = "approved"):
    """确保用户存在且状态正确"""
    from sqlalchemy import select
    from app.models import User

    async with TestSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                username=username,
                password_hash=pwd_ctx.hash(password),
                role=role,
                status=status,
            )
            session.add(user)
        else:
            user.role = role
            user.status = status
            user.password_hash = pwd_ctx.hash(password)

        await session.commit()
        return user


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient, setup_db) -> str:
    """获取管理员 Token"""
    username = "testadmin"
    password = "testpass123"

    # 确保用户存在且状态正确
    await _ensure_user(username, password, role="admin", status="approved")

    # 登录
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def user_token(client: AsyncClient, setup_db) -> str:
    """获取普通用户 Token"""
    username = "testuser"
    password = "testpass123"

    # 确保用户存在且状态正确
    await _ensure_user(username, password, role="user", status="approved")

    # 登录
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def admin_headers(admin_token: str) -> dict:
    """获取管理员请求头"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def user_headers(user_token: str) -> dict:
    """获取普通用户请求头"""
    return {"Authorization": f"Bearer {user_token}"}
