from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.polymarket import clob_api
from app.services.sports_strategy import MarketQuote


@dataclass(frozen=True)
class QuoteSnapshot:
    market_slug: str
    token_id: str
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    liquidity: float
    yes_price: float
    source: str = "polymarket_clob"


def _level_price(level: Any) -> float | None:
    raw = level.get("price") if isinstance(level, dict) else getattr(level, "price", None)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _level_size(level: Any) -> float:
    raw = level.get("size") if isinstance(level, dict) else getattr(level, "size", None)
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def build_quote_snapshot(
    *,
    market_slug: str,
    token_id: str,
    orderbook: dict,
    fallback_yes_price: float,
) -> QuoteSnapshot:
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])
    bid_prices = [price for level in bids if (price := _level_price(level)) is not None]
    ask_prices = [price for level in asks if (price := _level_price(level)) is not None]

    best_bid = max(bid_prices) if bid_prices else None
    best_ask = min(ask_prices) if ask_prices else None
    spread = None
    if best_bid is not None and best_ask is not None:
        spread = max(best_ask - best_bid, 0.0)

    liquidity = sum(_level_size(level) * (_level_price(level) or 0.0) for level in bids + asks)
    yes_price = best_ask if best_ask is not None else fallback_yes_price
    return QuoteSnapshot(
        market_slug=market_slug,
        token_id=token_id,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        liquidity=round(liquidity, 4),
        yes_price=yes_price,
    )


def snapshot_to_market_quote(snapshot: QuoteSnapshot, volume_24h: float = 0.0) -> MarketQuote:
    return MarketQuote(
        market_slug=snapshot.market_slug,
        token_id=snapshot.token_id,
        yes_price=snapshot.yes_price,
        best_bid=snapshot.best_bid,
        best_ask=snapshot.best_ask,
        spread=snapshot.spread,
        liquidity=snapshot.liquidity,
        volume_24h=volume_24h,
    )


async def fetch_quote_snapshot(
    *,
    market_slug: str,
    token_id: str,
    fallback_yes_price: float,
) -> QuoteSnapshot:
    orderbook = await clob_api.get_orderbook(token_id)
    return build_quote_snapshot(
        market_slug=market_slug,
        token_id=token_id,
        orderbook=orderbook,
        fallback_yes_price=fallback_yes_price,
    )
