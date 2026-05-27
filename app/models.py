from datetime import datetime
from sqlalchemy import Integer, String, Float, Boolean, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(10), default="user")  # admin / user
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending/approved/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    credentials: Mapped[list["Credential"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list["NotificationConfig"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    trades: Mapped[list["Trade"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    wallet_address: Mapped[str] = mapped_column(String(42), nullable=False)
    funder_address: Mapped[str | None] = mapped_column(String(42))
    encrypted_private_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_secret: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_passphrase: Mapped[str] = mapped_column(Text, nullable=False)
    chain_id: Mapped[int] = mapped_column(Integer, default=137)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="credentials")


class NotificationConfig(Base):
    __tablename__ = "notification_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # serverchan / telegram
    encrypted_config: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="notifications")


class AIConfig(Base):
    __tablename__ = "ai_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    market_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    condition_id: Mapped[str] = mapped_column(String(66), nullable=False, default="")
    token_id: Mapped[str] = mapped_column(String(100), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY/SELL
    order_type: Mapped[str] = mapped_column(String(10), default="GTC")
    price: Mapped[float] = mapped_column(Float)
    size: Mapped[float] = mapped_column(Float)
    filled: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    order_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="trades")


class ScanResult(Base):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_type: Mapped[str] = mapped_column(String(20), nullable=False)  # hot/new_political/arbitrage
    market_data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    ai_analysis: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
