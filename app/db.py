from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "sqlite":
            columns = await conn.execute(text("PRAGMA table_info(credentials)"))
            names = {row[1] for row in columns}
            if "signature_type" not in names:
                await conn.execute(text("ALTER TABLE credentials ADD COLUMN signature_type INTEGER NOT NULL DEFAULT 0"))
        else:
            await conn.execute(text("ALTER TABLE credentials ADD COLUMN IF NOT EXISTS signature_type INTEGER NOT NULL DEFAULT 0"))


async def get_db():
    async with SessionLocal() as session:
        yield session
