from pydantic import BaseModel
from datetime import datetime


# === Auth ===
class RegisterReq(BaseModel):
    username: str
    password: str


class LoginReq(BaseModel):
    username: str
    password: str


class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResp(BaseModel):
    id: int
    username: str
    role: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# === Wallet ===
class WalletSetupReq(BaseModel):
    private_key: str
    funder_address: str
    chain_id: int = 137


class WalletResp(BaseModel):
    id: int
    wallet_address: str
    funder_address: str | None = None
    chain_id: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# === Trading ===
class OrderReq(BaseModel):
    token_id: str
    price: float = 0
    size: float = 0
    side: str  # BUY / SELL
    order_type: str = "GTC"  # GTC / FOK / FAK
    tick_size: str = "0.01"
    neg_risk: bool = False
    usdc_amount: float = 0  # > 0 时自动从 CLOB 读盘口价计算 size
    market_slug: str = ""
    condition_id: str = ""


class MarketOrderReq(BaseModel):
    token_id: str
    amount: float  # 美元金额
    side: str  # BUY / SELL
    order_type: str = "FOK"
    tick_size: str = "0.01"
    neg_risk: bool = False
    market_slug: str = ""
    condition_id: str = ""


class SellReq(BaseModel):
    """卖出持仓：后端自动从 CLOB 读 best bid 并 clamp"""
    token_id: str
    size: float
    tick_size: str = "0.01"
    neg_risk: bool = False
    market_slug: str = ""
    condition_id: str = ""


class CancelOrderReq(BaseModel):
    order_id: str


class TradeResp(BaseModel):
    id: int
    market_slug: str
    side: str
    order_type: str
    price: float
    size: float
    filled: float
    status: str
    order_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# === Notification ===
class NotifyConfigReq(BaseModel):
    channel: str  # serverchan / telegram
    config: dict  # serverchan: {sendkey}, telegram: {bot_token, chat_id}


class NotifyTestReq(BaseModel):
    channel: str
    message: str = "PolyTrad 推送测试"


# === AI ===
class AIAnalyzeReq(BaseModel):
    ai_config_id: int
    prompt: str
    system_prompt: str = "你是一个 Polymarket 交易分析师，给出简洁的概率判断和交易建议。"


class AIMarketAnalyzeReq(BaseModel):
    ai_config_id: int
    market_slug: str
    question: str = "分析这个市场的走势和交易机会"


class AIConfigReq(BaseModel):
    name: str
    provider: str
    api_key: str
    model_name: str
    base_url: str | None = None


class AIConfigResp(BaseModel):
    id: int
    name: str
    provider: str
    model_name: str
    base_url: str | None
    is_active: bool

    model_config = {"from_attributes": True}


# === Scanner ===
class ScanResultResp(BaseModel):
    id: int
    scan_type: str
    market_data: str
    ai_analysis: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# === Admin ===
class AdminActionResp(BaseModel):
    success: bool
    message: str


class ChangePasswordReq(BaseModel):
    new_password: str


class SelfChangePasswordReq(BaseModel):
    old_password: str
    new_password: str
