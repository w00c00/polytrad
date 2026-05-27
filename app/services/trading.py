import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import User, Credential, Trade
from app.crypto import decrypt_secret
from app.config import get_settings

logger = logging.getLogger(__name__)

# py-clob-client-v2 的导入在运行时动态处理，避免导入失败影响其他功能
_ClobClient = None
_ApiCreds = None
_OrderArgs = None
_OrderType = None
_MarketOrderArgs = None
_PartialCreateOrderOptions = None
_BUY = None
_SELL = None


def _load_clob_libs():
    global _ClobClient, _ApiCreds, _OrderArgs, _OrderType, _MarketOrderArgs, _PartialCreateOrderOptions, _BUY, _SELL
    if _ClobClient is not None:
        return
    from py_clob_client_v2.client import ClobClient
    from py_clob_client_v2.clob_types import ApiCreds, OrderArgs, OrderType, MarketOrderArgs, PartialCreateOrderOptions
    from py_clob_client_v2.order_builder.constants import BUY, SELL
    _ClobClient = ClobClient
    _ApiCreds = ApiCreds
    _OrderArgs = OrderArgs
    _OrderType = OrderType
    _MarketOrderArgs = MarketOrderArgs
    _PartialCreateOrderOptions = PartialCreateOrderOptions
    _BUY = BUY
    _SELL = SELL


async def get_clob_client(user: User, db: AsyncSession):
    """为用户创建已认证的 ClobClient"""
    _load_clob_libs()
    result = await db.execute(
        select(Credential).where(Credential.user_id == user.id, Credential.is_active == True)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise ValueError("用户未配置钱包")

    private_key = decrypt_secret(cred.encrypted_private_key)
    api_key = decrypt_secret(cred.encrypted_api_key)
    api_secret = decrypt_secret(cred.encrypted_api_secret)
    api_passphrase = decrypt_secret(cred.encrypted_api_passphrase)

    return _ClobClient(
        host=get_settings().polymarket_clob_host,
        chain_id=cred.chain_id,
        key=private_key,
        creds=_ApiCreds(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
        ),
        signature_type=2 if cred.funder_address else 0,
        funder=cred.funder_address,
    )


async def setup_wallet(private_key: str, chain_id: int = 137) -> dict:
    """从私钥生成 API 三件套 (首次配置)"""
    _load_clob_libs()
    client = _ClobClient(
        host=get_settings().polymarket_clob_host,
        chain_id=chain_id,
        key=private_key,
    )
    creds = client.create_or_derive_api_key()
    # 从私钥推导地址 (eth_account 是 py-clob-client-v2 的依赖)
    from eth_account import Account
    account = Account.from_key(private_key)
    address = account.address
    return {
        "wallet_address": address,
        "api_key": creds.api_key,
        "api_secret": creds.api_secret,
        "api_passphrase": creds.api_passphrase,
    }


async def place_limit_order(
    user: User, db: AsyncSession,
    token_id: str, price: float, size: float,
    side: str, order_type: str = "GTC",
    tick_size: str = "0.01", neg_risk: bool = False,
    market_slug: str = "", condition_id: str = "",
) -> dict:
    """下限价单"""
    client = await get_clob_client(user, db)

    side_const = _BUY if side == "BUY" else _SELL
    otype = getattr(_OrderType, order_type, _OrderType.GTC)

    order_args = _OrderArgs(
        token_id=token_id,
        price=price,
        size=size,
        side=side_const,
    )
    options = _PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)

    resp = client.create_and_post_order(order_args, options=options, order_type=otype)

    trade = Trade(
        user_id=user.id,
        market_slug=market_slug,
        condition_id=condition_id,
        token_id=token_id,
        side=side,
        order_type=order_type,
        price=price,
        size=size,
        status="pending",
        order_id=resp.get("orderID") if isinstance(resp, dict) else None,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    return {"trade_id": trade.id, "order_id": trade.order_id, "response": resp}


async def place_market_order(
    user: User, db: AsyncSession,
    token_id: str, amount: float, side: str,
    order_type: str = "FOK", market_slug: str = "", condition_id: str = "",
) -> dict:
    """下市价单 (按美元金额)"""
    client = await get_clob_client(user, db)

    side_const = _BUY if side == "BUY" else _SELL
    otype = getattr(_OrderType, order_type, _OrderType.FOK)

    order = _MarketOrderArgs(
        token_id=token_id,
        amount=amount,
        side=side_const,
        order_type=otype,
    )
    resp = client.create_and_post_market_order(order)

    trade = Trade(
        user_id=user.id,
        market_slug=market_slug,
        condition_id=condition_id,
        token_id=token_id,
        side=side,
        order_type=order_type,
        price=0,  # 市价单无固定价格
        size=amount,
        status="filled",
        order_id=resp.get("orderID") if isinstance(resp, dict) else None,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    return {"trade_id": trade.id, "order_id": trade.order_id, "response": resp}


async def cancel_order(user: User, db: AsyncSession, order_id: str) -> dict:
    """撤单"""
    client = await get_clob_client(user, db)
    resp = client.cancel(order_id)
    return {"cancelled": True, "response": resp}


async def get_open_orders(user: User, db: AsyncSession) -> list:
    """获取当前挂单"""
    client = await get_clob_client(user, db)
    from py_clob_client_v2.clob_types import OpenOrderParams
    return client.get_orders(OpenOrderParams())


async def cancel_all_orders(user: User, db: AsyncSession) -> dict:
    """撤销所有挂单"""
    client = await get_clob_client(user, db)
    resp = client.cancel_all()
    return {"cancelled_all": True, "response": resp}
