import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import update as sa_update
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
_Side = None
_BalanceAllowanceParams = None
_AssetType = None


# CLOB 调用默认超时 (秒)
CLOB_TIMEOUT = 25


def _load_clob_libs():
    global _ClobClient, _ApiCreds, _OrderArgs, _OrderType, _MarketOrderArgs, _PartialCreateOrderOptions, _Side, _BalanceAllowanceParams, _AssetType
    if _ClobClient is not None:
        return
    from py_clob_client_v2.client import ClobClient
    from py_clob_client_v2.clob_types import ApiCreds, OrderArgs, OrderType, MarketOrderArgs, PartialCreateOrderOptions, BalanceAllowanceParams, AssetType
    from py_clob_client_v2 import Side
    _ClobClient = ClobClient
    _ApiCreds = ApiCreds
    _OrderArgs = OrderArgs
    _OrderType = OrderType
    _MarketOrderArgs = MarketOrderArgs
    _PartialCreateOrderOptions = PartialCreateOrderOptions
    _Side = Side
    _BalanceAllowanceParams = BalanceAllowanceParams
    _AssetType = AssetType


async def _run_clob(func, *args, timeout: float = CLOB_TIMEOUT, **kwargs):
    """包装同步的 CLOB client 方法为异步并加超时"""
    return await asyncio.wait_for(asyncio.to_thread(func, *args, **kwargs), timeout=timeout)


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

    kwargs = {
        "host": get_settings().polymarket_clob_host,
        "chain_id": cred.chain_id,
        "key": private_key,
        "creds": _ApiCreds(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
        ),
        "retry_on_error": True,
    }
    if cred.funder_address:
        kwargs["signature_type"] = 3
        kwargs["funder"] = cred.funder_address
    return _ClobClient(**kwargs)


async def setup_wallet(private_key: str, chain_id: int = 137, funder_address: str = "") -> dict:
    """从私钥派生 API 三件套 (首次配置)"""
    _load_clob_libs()
    from eth_account import Account
    account = Account.from_key(private_key)
    address = account.address

    temp_client = _ClobClient(
        host=get_settings().polymarket_clob_host,
        chain_id=chain_id,
        key=private_key,
        retry_on_error=True,
    )
    creds = temp_client.derive_api_key()

    return {
        "wallet_address": address,
        "api_key": creds.api_key,
        "api_secret": creds.api_secret,
        "api_passphrase": creds.api_passphrase,
    }


def _price_decimals(tick_size: str) -> int:
    """从 tick_size 字符串获取小数位数，避免 float 精度问题"""
    if "." not in tick_size:
        return 0
    return len(tick_size.rstrip("0").split(".", 1)[1])


def _clamp_price(price: float, tick_size: str) -> float:
    """将价格对齐到 tick_size"""
    tick = float(tick_size)
    decimals = _price_decimals(tick_size)
    return round(min(max(price, tick), 1.0 - tick), decimals)


def _best_price_from_book(book: dict, side: str) -> tuple[float | None, str]:
    """从订单簿获取 best ask (BUY) 或 best bid (SELL)，返回 (价格, tick_size)"""
    raw_levels = book.get("asks" if side == "BUY" else "bids", [])
    tick_size = str(book.get("tick_size", "0.01"))
    prices = []
    for level in raw_levels:
        p = level.get("price") if isinstance(level, dict) else getattr(level, "price", None)
        if p is not None:
            try:
                prices.append(float(p))
            except (ValueError, TypeError):
                pass
    if not prices:
        return None, tick_size
    return (min(prices) if side == "BUY" else max(prices)), tick_size


def _orderbook_to_dict(orderbook) -> dict:
    """将 CLOB orderbook 对象或字典统一为字典"""
    if isinstance(orderbook, dict):
        return orderbook
    return {
        "asks": getattr(orderbook, "asks", []),
        "bids": getattr(orderbook, "bids", []),
        "tick_size": getattr(orderbook, "tick_size", "0.01"),
    }


async def place_limit_order(
    user: User, db: AsyncSession,
    token_id: str, price: float, size: float,
    side: str, order_type: str = "GTC",
    tick_size: str = "0.01",
    market_slug: str = "", condition_id: str = "",
    usdc_amount: float = 0,
) -> dict:
    """下限价单。若传 usdc_amount > 0，则从 CLOB 实时读盘口价并自动计算 size"""
    _load_clob_libs()
    client = await get_clob_client(user, db)

    # 市价模式：从 CLOB 实时读盘口价
    if usdc_amount > 0:
        orderbook = await _run_clob(client.get_order_book, token_id)
        book_dict = _orderbook_to_dict(orderbook)
        best_price, real_tick = _best_price_from_book(book_dict, side)
        if best_price is None:
            raise ValueError("订单簿没有可买卖价")
        tick_size = real_tick or tick_size
        price = _clamp_price(best_price, tick_size)
        size = usdc_amount / price
        if size < 5.0:
            raise ValueError(f"金额太小，按价格 {price:.4f} 至少需要 {price * 5:.2f} USDC")
        logger.info("实时盘口价: %s price=%.4f size=%.4f tick=%s", side, price, size, tick_size)

    side_const = _Side.BUY if side == "BUY" else _Side.SELL
    otype = getattr(_OrderType, order_type, _OrderType.GTC)

    order_args = _OrderArgs(
        token_id=token_id,
        price=float(price),
        size=float(size),
        side=side_const,
    )
    options = _PartialCreateOrderOptions(tick_size=tick_size)

    resp = await _run_clob(client.create_and_post_order, order_args, options=options, order_type=otype)

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

    return {"trade_id": trade.id, "order_id": trade.order_id, "price": price, "size": size, "response": resp}


async def place_market_order(
    user: User, db: AsyncSession,
    token_id: str, amount: float, side: str,
    order_type: str = "FOK", market_slug: str = "", condition_id: str = "",
) -> dict:
    """下市价单 (按美元金额)，并尝试回填成交价"""
    _load_clob_libs()
    client = await get_clob_client(user, db)

    side_const = _Side.BUY if side == "BUY" else _Side.SELL
    otype = getattr(_OrderType, order_type, _OrderType.FOK)

    order = _MarketOrderArgs(
        token_id=token_id,
        amount=amount,
        side=side_const,
        order_type=otype,
    )
    resp = await _run_clob(client.create_and_post_market_order, order)

    # 尝试从响应或 CLOB 获取成交价
    filled_price = 0.0
    if isinstance(resp, dict):
        # 部分版本响应中带 price 或 avgPrice
        for key in ("price", "avgPrice", "average_price"):
            if resp.get(key):
                try:
                    filled_price = float(resp[key])
                    break
                except (ValueError, TypeError):
                    pass
    if filled_price == 0.0:
        try:
            from app.services.polymarket import clob_api
            last = await clob_api.get_last_trade(token_id)
            if isinstance(last, dict) and last.get("price"):
                filled_price = float(last["price"])
        except Exception:
            pass

    trade = Trade(
        user_id=user.id,
        market_slug=market_slug,
        condition_id=condition_id,
        token_id=token_id,
        side=side,
        order_type=order_type,
        price=filled_price,
        size=amount,
        status="filled",
        order_id=resp.get("orderID") if isinstance(resp, dict) else None,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    return {"trade_id": trade.id, "order_id": trade.order_id, "price": filled_price, "response": resp}


async def sell_position(
    user: User, db: AsyncSession,
    token_id: str, size: float,
    tick_size: str = "0.01",
    market_slug: str = "", condition_id: str = "",
) -> dict:
    """从 CLOB 实时读 best bid，挂卖出限价单"""
    _load_clob_libs()
    client = await get_clob_client(user, db)

    orderbook = await _run_clob(client.get_order_book, token_id)
    book_dict = _orderbook_to_dict(orderbook)
    # 卖出取 best bid
    best_bid, real_tick = _best_price_from_book(book_dict, "SELL")
    if best_bid is None:
        raise ValueError("订单簿没有买单，无法卖出")
    tick_size = real_tick or tick_size
    price = _clamp_price(best_bid, tick_size)

    side_const = _Side.SELL
    order_args = _OrderArgs(
        token_id=token_id,
        price=float(price),
        size=float(size),
        side=side_const,
    )
    options = _PartialCreateOrderOptions(tick_size=tick_size)

    resp = await _run_clob(
        client.create_and_post_order,
        order_args,
        options=options,
        order_type=_OrderType.GTC,
    )

    trade = Trade(
        user_id=user.id,
        market_slug=market_slug,
        condition_id=condition_id,
        token_id=token_id,
        side="SELL",
        order_type="GTC",
        price=price,
        size=size,
        status="pending",
        order_id=resp.get("orderID") if isinstance(resp, dict) else None,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    return {
        "trade_id": trade.id,
        "order_id": trade.order_id,
        "price": price,
        "size": size,
        "usdc_amount": round(price * size, 4),
        "response": resp,
    }


async def cancel_order(user: User, db: AsyncSession, order_id: str) -> dict:
    """撤单并同步本地 DB"""
    _load_clob_libs()
    client = await get_clob_client(user, db)
    from py_clob_client_v2.clob_types import OrderPayload
    resp = await _run_clob(client.cancel_order, OrderPayload(orderID=order_id))

    # 同步本地 Trade 表
    await db.execute(
        sa_update(Trade).where(Trade.order_id == order_id, Trade.user_id == user.id)
        .values(status="cancelled")
    )
    await db.commit()

    return {"cancelled": True, "response": resp}


async def get_open_orders(user: User, db: AsyncSession) -> list:
    """获取当前挂单"""
    client = await get_clob_client(user, db)
    return await _run_clob(client.get_open_orders)


async def cancel_all_orders(user: User, db: AsyncSession) -> dict:
    """撤销所有挂单，并同步本地 DB"""
    client = await get_clob_client(user, db)
    resp = await _run_clob(client.cancel_all)

    # 同步本地：将所有 pending 改为 cancelled
    await db.execute(
        sa_update(Trade).where(Trade.user_id == user.id, Trade.status == "pending")
        .values(status="cancelled")
    )
    await db.commit()

    return {"cancelled_all": True, "response": resp}


async def get_usdc_balance(user: User, db: AsyncSession) -> dict:
    """获取 USDC 余额（通过 CLOB get_balance_allowance）"""
    _load_clob_libs()
    client = await get_clob_client(user, db)
    params = _BalanceAllowanceParams(asset_type=_AssetType.COLLATERAL)
    raw = await _run_clob(client.get_balance_allowance, params)
    if not isinstance(raw, dict):
        return {"raw": str(raw)}
    result = {}
    for key in ["balance", "allowance", "available", "available_balance"]:
        if key in raw:
            try:
                result[key] = round(int(raw[key]) / 1_000_000, 6)
            except (TypeError, ValueError):
                result[key] = raw[key]
    return result or raw


async def sync_order_status(user: User, db: AsyncSession):
    """同步本地 Trade 状态到 CLOB 实际状态（定时任务调用）"""
    client = await get_clob_client(user, db)
    try:
        open_orders = await _run_clob(client.get_open_orders)
    except Exception as e:
        logger.warning(f"sync_order_status get_open_orders failed user={user.id}: {e}")
        return 0

    open_ids: set[str] = set()
    filled_map: dict[str, dict] = {}
    for o in (open_orders or []):
        if isinstance(o, dict):
            oid = o.get("id") or o.get("orderID")
            if oid:
                open_ids.add(str(oid))
            filled = o.get("filled_size") or o.get("filledSize") or o.get("size_matched")
            if filled is not None:
                try:
                    filled_map[str(oid)] = {"filled": float(filled)}
                except (ValueError, TypeError):
                    pass
        else:
            oid = getattr(o, "id", None) or getattr(o, "orderID", None)
            if oid:
                open_ids.add(str(oid))

    if not open_ids and not filled_map:
        # 如果 CLOB 返回空，可能所有挂单都已成交/撤销，但我们不能武断把本地 pending 全改 filled
        return 0

    # 1. 更新 filled_size
    for oid, info in filled_map.items():
        await db.execute(
            sa_update(Trade)
            .where(Trade.order_id == oid, Trade.user_id == user.id)
            .values(filled=info["filled"])
        )

    # 2. 本地 pending 的 trade，但 CLOB open_orders 不在了 → filled
    result = await db.execute(
        select(Trade.order_id).where(
            Trade.user_id == user.id,
            Trade.status == "pending",
            Trade.order_id.isnot(None),
        )
    )
    local_pending = [r[0] for r in result.all()]
    to_fill = [oid for oid in local_pending if oid not in open_ids]
    if to_fill:
        await db.execute(
            sa_update(Trade)
            .where(Trade.order_id.in_(to_fill), Trade.user_id == user.id)
            .values(status="filled", filled=Trade.size)
        )

    await db.commit()
    return len(to_fill)
