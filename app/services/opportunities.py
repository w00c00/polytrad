import asyncio
import re
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Credential, User
from app.services.btc_signal import analyze_btc_signal
from app.services.polymarket import clob_api, data_api, gamma_api, to_beijing_time, translate_title
from app.services.scanner import (
    _fetch_gamma_pages,
    _is_open,
    _market_token_ids,
    _market_volume_24h,
    _normalise_market,
    _parse_dt,
    _to_float,
    scan_btc_short_markets,
)


def _book_levels(book: dict, side: str) -> list[tuple[float, float]]:
    raw = book.get("asks" if side == "BUY" else "bids", [])
    levels = []
    for level in raw:
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


def _consume_by_usdc(levels: list[tuple[float, float]], amount_usdc: float) -> dict:
    remaining = amount_usdc
    shares = 0.0
    spent = 0.0
    worst_price = 0.0
    for price, size in levels:
        if remaining <= 1e-9:
            break
        take = min(size, remaining / price)
        spent += take * price
        shares += take
        remaining -= take * price
        worst_price = price

    best_price = levels[0][0] if levels else 0.0
    avg_price = spent / shares if shares else 0.0
    slippage = (avg_price - best_price) / best_price if best_price and avg_price else 0.0
    return {
        "fillable": remaining <= max(0.01, amount_usdc * 0.001),
        "best_price": round(best_price, 4),
        "avg_price": round(avg_price, 4),
        "worst_price": round(worst_price, 4),
        "shares": round(shares, 4),
        "spent": round(spent, 4),
        "unfilled_usdc": round(max(remaining, 0), 4),
        "slippage_pct": round(slippage * 100, 2),
    }


def _consume_by_shares(levels: list[tuple[float, float]], target_shares: float) -> dict:
    remaining = target_shares
    spent = 0.0
    filled = 0.0
    worst_price = 0.0
    for price, size in levels:
        if remaining <= 1e-9:
            break
        take = min(size, remaining)
        spent += take * price
        filled += take
        remaining -= take
        worst_price = price

    best_price = levels[0][0] if levels else 0.0
    avg_price = spent / filled if filled else 0.0
    return {
        "fillable": remaining <= max(0.001, target_shares * 0.001),
        "best_price": round(best_price, 4),
        "avg_price": round(avg_price, 4),
        "worst_price": round(worst_price, 4),
        "shares": round(filled, 4),
        "cost": round(spent, 4),
        "missing_shares": round(max(remaining, 0), 4),
    }


async def _orderbook_depth(token_id: str, amount_usdc: float) -> dict:
    book = await clob_api.get_orderbook(token_id)
    return _consume_by_usdc(_book_levels(book, "BUY"), amount_usdc)


async def scan_low_slippage_markets(
    amount_usdc: float = 25,
    max_slippage_pct: float = 2.0,
    min_volume_24h: float = 5000,
    max_candidates: int = 120,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    markets = await _fetch_gamma_pages(
        "markets",
        {"order": "volume24hr", "ascending": "false"},
        max_pages=max(1, (max_candidates + 99) // 100),
    )

    candidates = []
    for m in markets:
        if len(candidates) >= max_candidates:
            break
        if not _is_open(m, now):
            continue
        if _market_volume_24h(m) < min_volume_24h:
            continue
        token_ids = _market_token_ids(m)
        if not token_ids:
            continue
        candidates.append(m)

    sem = asyncio.Semaphore(12)

    async def check(market: dict, outcome_idx: int) -> dict | None:
        token_ids = _market_token_ids(market)
        if len(token_ids) <= outcome_idx:
            return None
        async with sem:
            try:
                depth = await _orderbook_depth(token_ids[outcome_idx], amount_usdc)
            except Exception:
                return None
        if not depth["fillable"] or depth["slippage_pct"] > max_slippage_pct:
            return None
        direction = "YES" if outcome_idx == 0 else "NO"
        q = market.get("question", "")
        return {
            "slug": market.get("slug", ""),
            "condition_id": market.get("conditionId", ""),
            "title": q,
            "title_zh": translate_title(q),
            "direction": direction,
            "token_id": token_ids[outcome_idx],
            "volume_24h": _market_volume_24h(market),
            "liquidity": _to_float(market.get("liquidityClob") or market.get("liquidity"), 0.0),
            "end_date_bj": to_beijing_time(market.get("endDate") or market.get("endDateIso")),
            "neg_risk": bool(market.get("negRisk", False)),
            "tick_size": str(market.get("minimumTickSize") or market.get("orderPriceMinTickSize") or "0.01"),
            "depth": depth,
        }

    tasks = []
    for market in candidates:
        tasks.append(check(market, 0))
        if len(_market_token_ids(market)) > 1:
            tasks.append(check(market, 1))
    results = [r for r in await asyncio.gather(*tasks) if r]
    results.sort(key=lambda x: (x["depth"]["slippage_pct"], -x["volume_24h"]))
    return results[:80]


def _canonical_topic(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\b20\d{2}-\d{2}-\d{2}\b", "", text)
    text = re.sub(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", "", text)
    text = re.sub(r"\b\d{1,2}\b", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\b(will|the|a|an|on|by|in|of|to|for)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _reward_max_spread(value) -> float:
    spread = _to_float(value, 0.0)
    return spread / 100 if spread > 1 else spread


async def scan_cross_event_spreads(
    min_spread: float = 0.08,
    max_candidates: int = 300,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    markets = await _fetch_gamma_pages(
        "markets",
        {"order": "volume24hr", "ascending": "false"},
        max_pages=max(1, (max_candidates + 99) // 100),
    )
    items = []
    for m in markets[:max_candidates]:
        if not _is_open(m, now) or not _market_token_ids(m):
            continue
        question = m.get("question") or ""
        key = _canonical_topic(question)
        if len(key) < 8:
            continue
        yes_price = _to_float(m.get("bestAsk") or _normalise_market(m)["yes_price"], 0.0)
        yes_bid = _to_float(m.get("bestBid") or yes_price, 0.0)
        items.append({
            "key": key,
            "slug": m.get("slug", ""),
            "question": question,
            "question_zh": translate_title(question),
            "yes_price": yes_price,
            "best_bid": yes_bid,
            "volume_24h": _market_volume_24h(m),
            "end_date_bj": to_beijing_time(m.get("endDate") or m.get("endDateIso")),
        })

    groups: list[list[dict]] = []
    for item in items:
        placed = False
        for group in groups:
            if SequenceMatcher(None, item["key"], group[0]["key"]).ratio() >= 0.92:
                group.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])

    spreads = []
    for group in groups:
        if len(group) < 2:
            continue
        low = min(group, key=lambda x: x["yes_price"])
        high = max(group, key=lambda x: x["best_bid"])
        spread = high["best_bid"] - low["yes_price"]
        if spread < min_spread:
            continue
        spreads.append({
            "topic": low["key"],
            "topic_zh": translate_title(low["question"]),
            "spread": round(spread, 4),
            "buy_candidate": low,
            "sell_reference": high,
            "markets": sorted(group, key=lambda x: x["yes_price"]),
            "note": "同题价差不是无风险套利，需人工确认两个市场的结算口径完全一致。",
        })

    spreads.sort(key=lambda x: x["spread"], reverse=True)
    return spreads[:50]


async def scan_reward_making_markets(max_candidates: int = 300) -> list[dict]:
    now = datetime.now(timezone.utc)
    markets = await _fetch_gamma_pages(
        "markets",
        {"order": "volume24hr", "ascending": "false"},
        max_pages=max(1, (max_candidates + 99) // 100),
    )
    results = []
    for m in markets[:max_candidates]:
        if not _is_open(m, now) or not _market_token_ids(m):
            continue
        rewards_min = _to_float(m.get("rewardsMinSize"), 0.0)
        rewards_max_spread = _reward_max_spread(m.get("rewardsMaxSpread"))
        if rewards_min <= 0 and rewards_max_spread <= 0:
            continue
        best_ask = _to_float(m.get("bestAsk"), 0.0)
        best_bid = _to_float(m.get("bestBid"), 0.0)
        spread = _to_float(m.get("spread"), 0.0)
        if not spread and best_ask and best_bid:
            spread = best_ask - best_bid
        results.append({
            "slug": m.get("slug", ""),
            "question": m.get("question", ""),
            "question_zh": translate_title(m.get("question", "")),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": round(spread, 4),
            "rewards_min_size": rewards_min,
            "rewards_max_spread": rewards_max_spread,
            "maker_fee_bps": _to_float(m.get("makerBaseFee"), 0.0),
            "taker_fee_bps": _to_float(m.get("takerBaseFee"), 0.0),
            "volume_24h": _market_volume_24h(m),
            "liquidity": _to_float(m.get("liquidityClob") or m.get("liquidity"), 0.0),
            "end_date_bj": to_beijing_time(m.get("endDate") or m.get("endDateIso")),
            "fit": rewards_max_spread <= 0 or spread <= rewards_max_spread,
            "note": "做市前请确认奖励规则、最小挂单和最大点差；本面板只筛选候选盘。",
        })
    results.sort(key=lambda x: (not x["fit"], x["spread"], -x["volume_24h"]))
    return results[:80]


async def scan_resolution_watch(hours: int = 12, min_volume_24h: float = 1000) -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours)
    markets = await _fetch_gamma_pages(
        "markets",
        {
            "order": "volume24hr",
            "ascending": "false",
            "end_date_min": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "end_date_max": cutoff.isoformat().replace("+00:00", "Z"),
        },
        max_pages=12,
    )
    results = []
    for m in markets:
        if m.get("closed") or m.get("archived"):
            continue
        if _market_volume_24h(m) < min_volume_24h:
            continue
        end_dt = _parse_dt(m.get("endDate") or m.get("endDateIso"))
        hours_left = (end_dt - now).total_seconds() / 3600 if end_dt else None
        status = m.get("umaResolutionStatus") or ("ending_soon" if hours_left and hours_left >= 0 else "past_end_open")
        results.append({
            "slug": m.get("slug", ""),
            "question": m.get("question", ""),
            "question_zh": translate_title(m.get("question", "")),
            "yes_price": _normalise_market(m)["yes_price"],
            "best_bid": _to_float(m.get("bestBid"), 0.0),
            "best_ask": _to_float(m.get("bestAsk"), 0.0),
            "volume_24h": _market_volume_24h(m),
            "liquidity": _to_float(m.get("liquidityClob") or m.get("liquidity"), 0.0),
            "end_date_bj": to_beijing_time(m.get("endDate") or m.get("endDateIso")),
            "hours_left": round(hours_left, 2) if hours_left is not None else None,
            "uma_status": status,
            "note": "适合临近结算复盘、撤单、减仓或关注 UMA 提案/争议状态。",
        })
    results.sort(key=lambda x: (x["hours_left"] is None, x["hours_left"] or 999, -x["volume_24h"]))
    return results[:100]


async def basket_precheck(event_slug: str, budget_usdc: float = 100) -> dict:
    event = await gamma_api.get_event(event_slug)
    if not event:
        raise ValueError("事件不存在")
    now = datetime.now(timezone.utc)
    markets = [m for m in event.get("markets", []) if _is_open(m, now) and _market_token_ids(m)]
    if len(markets) < 2:
        raise ValueError("该事件没有足够的可交易结果")

    leg_books = []
    ask_sum = 0.0
    for m in markets:
        token_id = _market_token_ids(m)[0]
        book = await clob_api.get_orderbook(token_id)
        asks = _book_levels(book, "BUY")
        if not asks:
            raise ValueError(f"{m.get('question', '')} 没有可买卖价")
        ask_sum += asks[0][0]
        leg_books.append((m, token_id, asks))

    if ask_sum <= 0:
        raise ValueError("无法计算篮子成本")
    complete_enough = ask_sum >= 0.85
    target_shares = budget_usdc / ask_sum
    legs = []
    total_cost = 0.0
    fillable = True
    for m, token_id, asks in leg_books:
        depth = _consume_by_shares(asks, target_shares)
        total_cost += depth["cost"]
        fillable = fillable and depth["fillable"]
        legs.append({
            "slug": m.get("slug", ""),
            "condition_id": m.get("conditionId", ""),
            "question": m.get("question", ""),
            "question_zh": translate_title(m.get("question", "")),
            "token_id": token_id,
            "tick_size": str(m.get("minimumTickSize") or m.get("orderPriceMinTickSize") or "0.01"),
            "depth": depth,
        })

    payout = target_shares
    profit = payout - total_cost
    return {
        "event_slug": event_slug,
        "title": event.get("title", ""),
        "title_zh": translate_title(event.get("title", "")),
        "budget_usdc": budget_usdc,
        "target_shares": round(target_shares, 4),
        "total_cost": round(total_cost, 4),
        "payout_if_complete": round(payout, 4),
        "estimated_profit": round(profit, 4),
        "estimated_profit_pct": round((profit / total_cost * 100) if total_cost > 0 else 0, 2),
        "fillable": fillable and profit > 0 and complete_enough,
        "legs": legs,
        "note": (
            "预检按买入每个 YES 相同份额计算；成交前仍可能因盘口变化而失效。"
            if complete_enough
            else "YES 总和过低，事件可能不是完整结果集；不要按无风险套利执行。"
        ),
    }


async def btc_momentum_alerts(min_edge: float = 0.04) -> list[dict]:
    markets = await scan_btc_short_markets(None)
    horizon_map = {"5分钟": 5, "15分钟": 15, "1小时": 60, "4小时": 240, "1天": 1440}
    signals: dict[int, dict] = {}
    alerts = []
    for event in markets:
        label = event.get("series_label", "")
        horizon = horizon_map.get(label)
        market = (event.get("markets") or [{}])[0]
        if not horizon or not market:
            continue
        if horizon not in signals:
            try:
                signals[horizon] = await analyze_btc_signal(horizon)
            except Exception as e:
                signals[horizon] = {"error": str(e)}
        signal = signals[horizon]
        if signal.get("error"):
            continue
        up_price = _to_float(market.get("yes_price"), 0.5)
        down_price = _to_float(market.get("no_price"), 1 - up_price)
        up_edge = signal["prob_up"] - up_price
        down_edge = signal["prob_down"] - down_price
        action = "不交易"
        edge = 0.0
        if up_edge >= min_edge:
            action = "买UP"
            edge = up_edge
        elif down_edge >= min_edge:
            action = "买DOWN"
            edge = down_edge
        if action == "不交易":
            continue
        alerts.append({
            "event_slug": event.get("event_slug", ""),
            "title": event.get("title", ""),
            "title_zh": event.get("title_zh") or translate_title(event.get("title", "")),
            "series_label": label,
            "end_time_bj": event.get("end_time_bj"),
            "action": action,
            "edge": round(edge, 4),
            "up_price": up_price,
            "down_price": down_price,
            "signal": signal,
            "market": market,
        })
    alerts.sort(key=lambda x: x["edge"], reverse=True)
    return alerts


async def hedge_suggestions(user: User, db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Credential).where(Credential.user_id == user.id, Credential.is_active == True))
    cred = result.scalar_one_or_none()
    if not cred:
        raise ValueError("未配置钱包")
    wallet = cred.funder_address or cred.wallet_address
    positions = await data_api.get_positions(wallet)
    suggestions = []
    for p in positions:
        size = _to_float(p.get("size"), 0.0)
        if size <= 0 or p.get("redeemed") or p.get("redeemable"):
            continue
        price = _to_float(p.get("curPrice") or p.get("price") or p.get("avgPrice"), 0.0)
        value = _to_float(p.get("currentValue") or p.get("value"), size * price)
        pnl = _to_float(p.get("cashPnl") or p.get("pnl"), 0.0)
        title = p.get("title") or p.get("question") or ""
        risk = "观察"
        action = "继续观察，确认结算口径和流动性。"
        if price >= 0.85 and value >= 5:
            risk = "止盈/降风险"
            action = "价格已接近高概率区，可考虑卖出部分锁定收益。"
        elif 0 < price <= 0.18 and value >= 5:
            risk = "尾部风险"
            action = "若不是明确的高赔率策略，考虑小额留仓或止损。"
        elif pnl < -max(5, value * 0.2):
            risk = "亏损扩大"
            action = "先复核信息差，不建议无条件加仓；可用反向结果或减仓对冲。"
        suggestions.append({
            "title": title,
            "title_zh": translate_title(title),
            "outcome": p.get("outcome") or p.get("side") or "",
            "asset": p.get("asset") or p.get("tokenId") or "",
            "opposite_asset": p.get("oppositeAsset") or p.get("oppositeTokenId") or "",
            "size": size,
            "price": price,
            "current_value": value,
            "pnl": pnl,
            "risk": risk,
            "action": action,
        })
    suggestions.sort(key=lambda x: (x["risk"] == "观察", -abs(x["pnl"])))
    return suggestions
