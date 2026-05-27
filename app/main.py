import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from passlib.context import CryptContext
from sqlalchemy import select
from app.config import get_settings
from app.db import init_db, SessionLocal
from app.models import User
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def ensure_admin():
    """确保管理员账户存在"""
    settings = get_settings()
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.username == settings.admin_username))
        admin = result.scalar_one_or_none()
        if not admin:
            admin = User(
                username=settings.admin_username,
                password_hash=pwd_ctx.hash(settings.admin_password),
                role="admin",
                status="approved",
            )
            db.add(admin)
            await db.commit()
            logger.info(f"管理员账户已创建: {settings.admin_username}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await ensure_admin()
    start_scheduler()
    logger.info("PolyTrad 启动完成")
    yield
    stop_scheduler()
    logger.info("PolyTrad 已停止")


app = FastAPI(title="PolyTrad", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from app.api import auth, admin, wallet, btc, sports, hot, political, arbitrage, ai, notify

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(wallet.router)
app.include_router(btc.router)
app.include_router(sports.router)
app.include_router(hot.router)
app.include_router(political.router)
app.include_router(arbitrage.router)
app.include_router(ai.router)
app.include_router(notify.router)

# 前端静态文件
import os
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
