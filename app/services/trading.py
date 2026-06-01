import asyncio
import logging
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN
from math import gcd
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
_PostOrdersV2Args = None
_Side = None
_BalanceAllowanceParams = None
_AssetType = None


# CLOB 调用默认超时 (秒)
CLOB_TIMEOUT = 25
VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"GTC", "FOK", "FAK", "GTD"}


def _load_clob_libs():
    global _ClobClient, _ApiCreds, _OrderArgs, _OrderType, _MarketOrderArgs, _PartialCreateOrderOptions, _PostOrdersV2Args, _Side, _BalanceAllowanceParams, _AssetType
    if _ClobClient is not None:
        return
    from py_clob_client_v2.client import ClobClient
    from py_clob_client_v2.clob_types import ApiCreds, OrderArgs, OrderType, MarketOrderArgs, PartialCreateOrderOptions, PostOrdersV2Args, BalanceAllowanceParams, AssetType
    from py_clob_client_v2 import Side
    _ClobClient = ClobClient
    _ApiCreds = ApiCreds
    _OrderArgs = OrderArgs
    _OrderType = OrderType
    _MarketOrderArgs = MarketOrderArgs
    _PartialCreateOrderOptions = PartialCreateOrderOptions
    _PostOrdersV2Args = PostOrdersV2Args
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


def _clob_order_id(resp) -> str | None:
    if isinstance(resp, dict):
        return resp.get("orderID") or resp.get("orderId") or resp.get("id")
    return getattr(resp, "orderID", None) or getattr(resp, "orderId", None) or getattr(resp, "id", None)


def _ensure_clob_success(resp, action: str) -> None:
    if isinstance(resp, list):
        failed = [r for r in resp if isinstance(r, dict) and (r.get("success") is False or r.get("error") or r.get("message") == "error")]
        if failed:
            detail = failed[0].get("error") or failed[0].get("message") or failed[0]
            raise ValueError(f"{action}失败: {detail}")
        return
    if not isinstance(resp, dict):
        return
    if resp.get("success") is False or resp.get("error") or resp.get("message") == "error":
        detail = resp.get("error") or resp.get("message") or resp
        raise ValueError(f"{action}失败: {detail}")


def _clob_success(resp) -> bool:
    if isinstance(resp, dict):
        return not (resp.get("success") is False or resp.get("error") or resp.get("message") == "error")
    return True


def _batch_response_items(resp) -> list:
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for key in ("orders", "responses", "results", "data"):
            value = resp.get(key)
            if isinstance(value, list):
                return value
    return []


def _validate_order(side: str, order_type: str, price: float, size: float, usdc_amount: float) -> tuple[str, str]:
    side = side.upper()
    order_type = order_type.upper()
    if side not in VALID_SIDES:
        raise ValueError("side 必须是 BUY 或 SELL")
    if order_type not in VALID_ORDER_TYPES:
        raise ValueError("order_type 必须是 GTC、FOK、FAK 或 GTD")
    if usdc_amount <= 0:
        if price <= 0 or price >= 1:
            raise ValueError("限价单价格必须在 0 到 1 之间")
        if size < 5:
            raise ValueError("订单份额至少 5 份")
    return side, order_type


def _cancelled_ids(resp) -> set[str]:
    if not isinstance(resp, dict):
        return set()
    ids = resp.get("canceled") or resp.get("cancelled") or resp.get("cancelled_orders") or resp.get("canceled_orders") or []
    if isinstance(ids, str):
        return {ids}
    if isinstance(ids, list):
        return {str(x.get("id") or x.get("orderID") or x) for x in ids}
    return set()


def _not_cancelled_ids(resp) -> set[str]:
    if not isinstance(resp, dict):
        return set()
    ids = resp.get("not_canceled") or resp.get("not_cancelled") or resp.get("not_canceled_orders") or []
    if isinstance(ids, str):
        return {ids}
    if isinstance(ids, list):
        return {str(x.get("id") or x.get("orderID") or x) for x in ids}
    return set()


def _order_status_from_detail(order: dict, expected_size: float) -> tuple[str | None, float | None]:
    status = str(order.get("status") or order.get("state") or "").lower()
    filled_raw = (
        order.get("filled_size")
        or order.get("filledSize")
        or order.get("size_matched")
        or order.get("sizeMatched")
    )
    filled = None
    if filled_raw is not None:
        try:
            filled = float(filled_raw)
        except (TypeError, ValueError):
            filled = None

    if any(s in status for s in ("cancel", "canceled", "cancelled", "expired")):
        return "cancelled", filled
    if filled is not None and expected_size > 0 and filled >= expected_size - 1e-8:
        return "filled", filled
    if any(s in status for s in ("matched", "mined", "confirmed", "filled")):
        return "filled", filled
    if any(s in status for s in ("live", "open", "pending", "active")):
        return "pending", filled
    return None, filled


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


def _book_levels_from_book(book: dict, side: str) -> list[tuple[float, float]]:
    raw_levels = book.get("asks" if side == "BUY" else "bids", [])
    levels = []
    for level in raw_levels:
        price = level.get("price") if isinstance(level, dict) else getattr(level, "price", None)
        size = level.get("size") if isinstance(level, dict) else getattr(level, "size", None)
        try:
            p = float(price)
            s = float(size)
        except (TypeError, ValueError):
            continue
        if 0 < p < 1 and s > 0:
            levels.append((p, s))
    levels.sort(key=lambda x: x[0], reverse=(side == "SELL"))
    return levels


def _depth_for_usdc(book: dict, side: str, amount: float) -> dict:
    levels = _book_levels_from_book(book, side)
    if not levels:
        return {"fillable": False, "reason": "订单簿没有可买卖价"}

    remaining = amount
    filled = 0.0
    notional = 0.0
    worst_price = 0.0
    levels_used = 0
    for price, available in levels:
        if remaining <= 1e-9:
            break
        take = min(available, remaining / price)
        if take <= 1e-9:
            continue
        filled += take
        notional += take * price
        remaining -= take * price
        worst_price = price
        levels_used += 1

    if filled < 5:
        best = levels[0][0]
        return {
            "fillable": False,
            "reason": f"金额太小或盘口太薄，按当前价格至少需要约 {best * 5:.2f} USDC",
            "best_price": best,
            "worst_price": worst_price or best,
            "size": filled,
            "notional": notional,
        }
    return {
        "fillable": True,
        "best_price": levels[0][0],
        "worst_price": worst_price,
        "size": filled,
        "notional": notional,
        "unfilled_usdc": max(remaining, 0.0),
        "levels_used": levels_used,
    }


def _floor_decimal(value: float, decimals: int) -> float:
    quant = Decimal("1").scaleb(-decimals)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_DOWN))


def _ceil_price_to_tick(price: float, tick_size: str) -> Decimal:
    tick = Decimal(str(tick_size or "0.01"))
    if tick <= 0:
        tick = Decimal("0.01")
    price_dec = Decimal(str(price))
    steps = (price_dec / tick).to_integral_value(rounding=ROUND_CEILING)
    return min(max(steps * tick, tick), Decimal("1") - tick)


def _safe_buy_size_step(price: float) -> Decimal:
    price_dec = Decimal(str(price))
    if price_dec <= 0:
        return Decimal("0")
    price_decimals = max(-price_dec.as_tuple().exponent, 0)
    price_scale = 10 ** price_decimals
    price_units = int((price_dec * price_scale).to_integral_value(rounding=ROUND_DOWN))
    if price_units <= 0:
        return Decimal("0")

    size_scale = 100
    step_units = price_scale // gcd(price_units, price_scale)
    return Decimal(step_units) / Decimal(size_scale)


def _server_safe_buy_size(price: float, target_size: float, max_usdc: float) -> float:
    """FOK/marketable BUY orders require USDC maker amount <= 2 decimals."""
    price_dec = Decimal(str(price))
    if price_dec <= 0:
        return 0.0
    step = _safe_buy_size_step(price)
    if step <= 0:
        return 0.0

    # py-clob-client-v2 currently rounds limit-order size down to 2 decimals.
    size_scale = 100
    max_size_units = int((Decimal(str(target_size)) * size_scale).to_integral_value(rounding=ROUND_DOWN))
    max_amount_units = int(((Decimal(str(max_usdc)) / price_dec) * size_scale).to_integral_value(rounding=ROUND_DOWN))
    size_units = min(max_size_units, max_amount_units)
    if size_units <= 0:
        return 0.0

    step_units = int((step * size_scale).to_integral_value(rounding=ROUND_CEILING))
    size_units -= size_units % max(step_units, 1)
    return float(Decimal(size_units) / Decimal(size_scale))


def _server_safe_buy_quote(price: float, target_size: float, max_usdc: float, tick_size: str) -> tuple[float, float]:
    """Find the nearest marketable BUY limit price/size pair that satisfies server precision."""
    tick = Decimal(str(tick_size or "0.01"))
    if tick <= 0:
        tick = Decimal("0.01")
    start = _ceil_price_to_tick(price, tick_size)
    max_price = min(Decimal("1") - tick, Decimal(str(max_usdc)) / Decimal("5"))
    if start > max_price:
        return float(start), 0.0

    seen = set()
    candidates: list[Decimal] = []
    max_steps = int(((max_price - start) / tick).to_integral_value(rounding=ROUND_DOWN))
    for i in range(min(max_steps, 200) + 1):
        candidates.append(start + tick * i)

    cent = (start * Decimal("100")).to_integral_value(rounding=ROUND_CEILING) / Decimal("100")
    if start <= cent <= max_price:
        candidates.append(cent)

    for candidate in candidates:
        key = str(candidate.normalize())
        if key in seen:
            continue
        seen.add(key)
        candidate_price = float(candidate)
        size = _server_safe_buy_size(candidate_price, target_size, max_usdc)
        if size >= 5.0:
            return candidate_price, size
    return float(start), 0.0


def _server_safe_min_buy_cost(price: float, tick_size: str) -> float:
    tick = Decimal(str(tick_size or "0.01"))
    if tick <= 0:
        tick = Decimal("0.01")
    start = _ceil_price_to_tick(price, tick_size)
    max_price = Decimal("1") - tick
    best_cost: Decimal | None = None

    candidates = [start + tick * i for i in range(201) if start + tick * i <= max_price]
    cent = (start * Decimal("100")).to_integral_value(rounding=ROUND_CEILING) / Decimal("100")
    if start <= cent <= max_price:
        candidates.append(cent)

    seen = set()
    for candidate in candidates:
        key = str(candidate.normalize())
        if key in seen:
            continue
        seen.add(key)
        step = _safe_buy_size_step(float(candidate))
        if step <= 0:
            continue
        min_size = (Decimal("5") / step).to_integral_value(rounding=ROUND_CEILING) * step
        cost = candidate * min_size
        best_cost = cost if best_cost is None else min(best_cost, cost)
    if best_cost is None:
        return float(start * Decimal("5"))
    return float(best_cost)


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
    neg_risk: bool = False,
    market_slug: str = "", condition_id: str = "",
    usdc_amount: float = 0,
) -> dict:
    """下限价单。若传 usdc_amount > 0，则从 CLOB 实时读盘口价并自动计算 size"""
    _load_clob_libs()
    side, order_type = _validate_order(side, order_type, price, size, usdc_amount)
    client = await get_clob_client(user, db)

    # 金额模式：从 CLOB 实时读订单簿，按深度给 FOK 限价，避免临近结算薄盘口只看 best ask 导致失败。
    if usdc_amount > 0:
        if usdc_amount < 1:
            raise ValueError("下单金额至少 1 USDC")
        orderbook = await _run_clob(client.get_order_book, token_id)
        book_dict = _orderbook_to_dict(orderbook)
        tick_size = str(book_dict.get("tick_size") or tick_size)
        depth = _depth_for_usdc(book_dict, side, usdc_amount)
        if not depth.get("fillable"):
            raise ValueError(depth.get("reason") or "盘口深度不足，无法按金额下单")
        price = _clamp_price(float(depth["worst_price"]), tick_size)
        if side == "BUY":
            price, size = _server_safe_buy_quote(price, float(depth["size"]), usdc_amount, tick_size)
        else:
            size = _floor_decimal(min(float(depth["size"]), usdc_amount / price), 2)
        if size < 5.0:
            min_cost = _server_safe_min_buy_cost(price, tick_size) if side == "BUY" else price * 5
            raise ValueError(f"金额太小或不满足交易所精度，按当前价格至少需要约 {min_cost:.2f} USDC")
        logger.info(
            "实时盘口深度: %s price=%.4f size=%.4f requested=%.4f order_notional=%.4f levels=%s tick=%s",
            side, price, size, usdc_amount, price * size, depth.get("levels_used"), tick_size,
        )
    else:
        price = _clamp_price(price, tick_size)

    side_const = _Side.BUY if side == "BUY" else _Side.SELL
    otype = getattr(_OrderType, order_type)

    order_args = _OrderArgs(
        token_id=token_id,
        price=float(price),
        size=float(size),
        side=side_const,
    )
    options = _PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)

    resp = await _run_clob(client.create_and_post_order, order_args, options=options, order_type=otype)
    _ensure_clob_success(resp, "下单")
    order_id = _clob_order_id(resp)

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
        order_id=order_id,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    return {"trade_id": trade.id, "order_id": trade.order_id, "price": price, "size": size, "response": resp}


async def place_limit_orders_batch(
    user: User,
    db: AsyncSession,
    orders: list[dict],
    post_only: bool = False,
) -> dict:
    """批量提交限价单；主要用于篮子套利的一键 FOK 下单。"""
    _load_clob_libs()
    if not orders:
        raise ValueError("批量下单列表不能为空")
    client = await get_clob_client(user, db)

    post_args = []
    normalized = []
    for spec in orders:
        token_id = str(spec.get("token_id") or "")
        price = float(spec.get("price") or 0)
        size = float(spec.get("size") or 0)
        usdc_amount = float(spec.get("usdc_amount") or 0)
        if usdc_amount > 0:
            raise ValueError("批量限价单需要传入明确的 price 和 size")

        side, order_type = _validate_order(
            str(spec.get("side") or "BUY"),
            str(spec.get("order_type") or "GTC"),
            price,
            size,
            usdc_amount,
        )
        tick_size = str(spec.get("tick_size") or "0.01")
        price = _clamp_price(price, tick_size)
        side_const = _Side.BUY if side == "BUY" else _Side.SELL
        otype = getattr(_OrderType, order_type)
        options = _PartialCreateOrderOptions(
            tick_size=tick_size,
            neg_risk=bool(spec.get("neg_risk", False)),
        )
        order_args = _OrderArgs(
            token_id=token_id,
            price=float(price),
            size=float(size),
            side=side_const,
        )
        signed = await _run_clob(client.create_order, order_args, options)
        post_args.append(_PostOrdersV2Args(order=signed, orderType=otype))
        normalized.append({
            "token_id": token_id,
            "price": price,
            "size": size,
            "side": side,
            "order_type": order_type,
            "market_slug": str(spec.get("market_slug") or ""),
            "condition_id": str(spec.get("condition_id") or ""),
        })

    resp = await _run_clob(client.post_orders, post_args, post_only=post_only)
    if isinstance(resp, dict) and not _batch_response_items(resp):
        _ensure_clob_success(resp, "批量下单")
    items = _batch_response_items(resp)

    saved = []
    failed = []
    for idx, spec in enumerate(normalized):
        item = items[idx] if idx < len(items) else (resp if len(normalized) == 1 else {})
        if not _clob_success(item):
            failed.append({**spec, "response": item})
            continue
        trade = Trade(
            user_id=user.id,
            market_slug=spec["market_slug"],
            condition_id=spec["condition_id"],
            token_id=spec["token_id"],
            side=spec["side"],
            order_type=spec["order_type"],
            price=spec["price"],
            size=spec["size"],
            status="pending",
            order_id=_clob_order_id(item),
        )
        db.add(trade)
        saved.append((trade, item))

    await db.commit()
    orders_out = []
    for trade, item in saved:
        await db.refresh(trade)
        orders_out.append({
            "trade_id": trade.id,
            "order_id": trade.order_id,
            "token_id": trade.token_id,
            "side": trade.side,
            "order_type": trade.order_type,
            "price": trade.price,
            "size": trade.size,
            "response": item,
        })

    return {
        "success": len(failed) == 0,
        "orders": orders_out,
        "failed": failed,
        "response": resp,
    }


async def place_market_order(
    user: User, db: AsyncSession,
    token_id: str, amount: float, side: str,
    order_type: str = "FOK", market_slug: str = "", condition_id: str = "",
    tick_size: str = "0.01", neg_risk: bool = False,
) -> dict:
    """下市价单 (按美元金额)，并尝试回填成交价"""
    _load_clob_libs()
    side, order_type = _validate_order(side, order_type, price=0.5, size=5, usdc_amount=amount)
    if amount <= 0:
        raise ValueError("下单金额必须大于 0")
    amount = _floor_decimal(amount, 2)
    client = await get_clob_client(user, db)

    side_const = _Side.BUY if side == "BUY" else _Side.SELL
    otype = getattr(_OrderType, order_type)

    order = _MarketOrderArgs(
        token_id=token_id,
        amount=amount,
        side=side_const,
        order_type=otype,
    )
    options = _PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)
    resp = await _run_clob(client.create_and_post_market_order, order, options=options, order_type=otype)
    _ensure_clob_success(resp, "市价下单")

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
    filled_size = amount
    if side == "BUY" and filled_price > 0:
        filled_size = amount / filled_price

    trade = Trade(
        user_id=user.id,
        market_slug=market_slug,
        condition_id=condition_id,
        token_id=token_id,
        side=side,
        order_type=order_type,
        price=filled_price,
        size=filled_size,
        status="filled",
        order_id=_clob_order_id(resp),
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    return {"trade_id": trade.id, "order_id": trade.order_id, "price": filled_price, "response": resp}


async def sell_position(
    user: User, db: AsyncSession,
    token_id: str, size: float,
    tick_size: str = "0.01",
    neg_risk: bool = False,
    market_slug: str = "", condition_id: str = "",
) -> dict:
    """从 CLOB 实时读 best bid，挂卖出限价单"""
    _load_clob_libs()
    if size < 5:
        raise ValueError("卖出份额至少 5 份")
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
    options = _PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)

    resp = await _run_clob(
        client.create_and_post_order,
        order_args,
        options=options,
        order_type=_OrderType.GTC,
    )
    _ensure_clob_success(resp, "卖出")
    order_id = _clob_order_id(resp)

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
        order_id=order_id,
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
    _ensure_clob_success(resp, "撤单")

    cancelled = _cancelled_ids(resp)
    not_cancelled = _not_cancelled_ids(resp)
    if cancelled and order_id not in cancelled:
        raise ValueError(f"订单未被取消: {resp}")
    if order_id in not_cancelled:
        raise ValueError(f"订单未被取消: {resp}")

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
    _ensure_clob_success(resp, "全部撤单")

    cancelled = _cancelled_ids(resp)
    if cancelled:
        await db.execute(
            sa_update(Trade)
            .where(Trade.user_id == user.id, Trade.status == "pending", Trade.order_id.in_(cancelled))
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
            if oid and filled is not None:
                try:
                    filled_map[str(oid)] = {"filled": float(filled)}
                except (ValueError, TypeError):
                    pass
        else:
            oid = getattr(o, "id", None) or getattr(o, "orderID", None)
            if oid:
                open_ids.add(str(oid))

    # 1. 更新 filled_size
    for oid, info in filled_map.items():
        await db.execute(
            sa_update(Trade)
            .where(Trade.order_id == oid, Trade.user_id == user.id)
            .values(filled=info["filled"])
        )

    # 2. 本地 pending 的 trade，但 CLOB open_orders 不在了 -> 逐个查询详情，区分成交/取消/过期
    result = await db.execute(
        select(Trade).where(
            Trade.user_id == user.id,
            Trade.status == "pending",
            Trade.order_id.isnot(None),
        )
    )
    local_pending = result.scalars().all()
    status_updates = 0
    for trade in local_pending:
        oid = str(trade.order_id)
        if oid in open_ids:
            continue
        try:
            detail = await _run_clob(client.get_order, oid, timeout=10)
        except Exception as e:
            logger.debug("sync_order_status get_order failed order=%s user=%s: %s", oid, user.id, e)
            continue
        if not isinstance(detail, dict):
            continue
        new_status, filled = _order_status_from_detail(detail, trade.size)
        if not new_status:
            continue
        values = {"status": new_status}
        if filled is not None:
            values["filled"] = filled
        elif new_status == "filled":
            values["filled"] = trade.size
        await db.execute(
            sa_update(Trade)
            .where(Trade.order_id == oid, Trade.user_id == user.id)
            .values(**values)
        )
        status_updates += 1

    await db.commit()
    return status_updates
