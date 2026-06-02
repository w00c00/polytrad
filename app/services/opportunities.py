import asyncio
import re
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Credential, User
from app.services.btc_signal import analyze_btc_signal
from app.services.polymarket import clob_api, data_api, gamma_api, to_beijing_time, translate_title
from app.services.scanner import (
    BASKET_MAX_BUY_SUM,
    BASKET_MIN_BUY_SUM,
    _basket_event_safety,
    _basket_integrity,
    _fetch_gamma_pages,
    _is_open,
    _is_tradable_market,
    _market_tick_size,
    _market_token_ids,
    _market_volume_24h,
    _normalise_market,
    _parse_dt,
    _to_float,
    scan_btc_short_markets,
)
from app.services.trading import cancel_order, place_limit_order, place_limit_orders_batch, sell_position


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
    levels_used = 0
    for price, size in levels:
        if remaining <= 1e-9:
            break
        take = min(size, remaining / price)
        if take <= 1e-9:
            continue
        spent += take * price
        shares += take
        remaining -= take * price
        worst_price = price
        levels_used += 1

    best_price = levels[0][0] if levels else 0.0
    best_size = levels[0][1] if levels else 0.0
    top_level_capacity = best_price * best_size if best_price and best_size else 0.0
    avg_price = spent / shares if shares else 0.0
    slippage = (avg_price - best_price) / best_price if best_price and avg_price else 0.0
    gross_profit_if_win = shares - spent
    return {
        "fillable": remaining <= max(0.01, amount_usdc * 0.001),
        "best_price": round(best_price, 4),
        "avg_price": round(avg_price, 4),
        "worst_price": round(worst_price, 4),
        "shares": round(shares, 4),
        "spent": round(spent, 4),
        "payout_if_win": round(shares, 4),
        "gross_profit_if_win": round(gross_profit_if_win, 4),
        "gross_roi_if_win_pct": round((gross_profit_if_win / spent * 100) if spent > 0 else 0.0, 2),
        "break_even_probability": round(avg_price, 4),
        "levels_used": levels_used,
        "top_level_capacity_usdc": round(top_level_capacity, 4),
        "top_level_remaining_usdc": round(max(top_level_capacity - spent, 0.0), 4),
        "next_level_after_usdc": round(top_level_capacity, 4),
        "unfilled_usdc": round(max(remaining, 0), 4),
        "slippage_pct": round(slippage * 100, 2),
        "slippage_bps": round(slippage * 10000, 2),
        "liquidity_mode": "首档内" if levels_used <= 1 and remaining <= max(0.01, amount_usdc * 0.001) else "扫多档",
        "slippage_note": "首档盘口足够，按当前金额不会扫到第二档" if levels_used <= 1 and remaining <= max(0.01, amount_usdc * 0.001) else "",
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


def _consume_pair_by_budget(
    low_levels: list[tuple[float, float]],
    hedge_levels: list[tuple[float, float]],
    budget_usdc: float = 0,
    min_profit_pct: float = 0.0,
) -> dict:
    """同步吃两条 BUY 盘口：低价 YES + 高价参考 NO。"""
    if not low_levels or not hedge_levels:
        return {"fillable": False, "reason": "缺少低价端或对冲端盘口"}

    max_pair_cost = 1.0 / (1.0 + max(min_profit_pct, 0.0) / 100.0)
    budget_left = budget_usdc if budget_usdc > 0 else float("inf")
    i = j = 0
    low_left = low_levels[0][1]
    hedge_left = hedge_levels[0][1]
    shares = low_cost = hedge_cost = total_cost = 0.0
    low_worst = hedge_worst = 0.0

    while i < len(low_levels) and j < len(hedge_levels) and budget_left > 1e-9:
        low_price = low_levels[i][0]
        hedge_price = hedge_levels[j][0]
        pair_cost = low_price + hedge_price
        if pair_cost <= 0 or pair_cost > max_pair_cost:
            break

        take = min(low_left, hedge_left)
        if budget_usdc > 0:
            take = min(take, budget_left / pair_cost)
        if take <= 1e-9:
            break

        shares += take
        low_cost += take * low_price
        hedge_cost += take * hedge_price
        total_cost += take * pair_cost
        budget_left -= take * pair_cost
        low_worst = low_price
        hedge_worst = hedge_price

        low_left -= take
        hedge_left -= take
        if low_left <= 1e-9:
            i += 1
            if i < len(low_levels):
                low_left = low_levels[i][1]
        if hedge_left <= 1e-9:
            j += 1
            if j < len(hedge_levels):
                hedge_left = hedge_levels[j][1]

    payout = shares
    profit = payout - total_cost
    avg_low = low_cost / shares if shares else 0.0
    avg_hedge = hedge_cost / shares if shares else 0.0
    avg_pair_cost = total_cost / shares if shares else 0.0
    fillable = shares >= 5 and profit > 0
    reason = ""
    if not fillable:
        reason = "可盈利深度不足 5 份或利润不足"
    note = ""
    if fillable and budget_usdc > 0 and budget_left > max(0.01, budget_usdc * 0.001):
        note = "预算高于当前可盈利盘口容量，已按可盈利容量估算执行"

    return {
        "fillable": fillable,
        "requested_budget_usdc": round(budget_usdc, 4),
        "target_shares": round(shares, 4),
        "capacity_usdc": round(total_cost, 4),
        "total_cost": round(total_cost, 4),
        "payout_if_hedged": round(payout, 4),
        "expected_profit": round(profit, 4),
        "expected_profit_pct": round((profit / total_cost * 100) if total_cost > 0 else 0.0, 2),
        "avg_pair_cost": round(avg_pair_cost, 4),
        "low_leg": {
            "avg_price": round(avg_low, 4),
            "worst_price": round(low_worst, 4),
            "cost": round(low_cost, 4),
        },
        "hedge_leg": {
            "avg_price": round(avg_hedge, 4),
            "worst_price": round(hedge_worst, 4),
            "cost": round(hedge_cost, 4),
        },
        "unfilled_usdc": round(max(budget_left, 0.0), 4) if budget_usdc > 0 else 0.0,
        "reason": reason,
        "note": note,
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
        if not _is_tradable_market(m, now):
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
        avg_price = depth.get("avg_price", 0)
        if avg_price < 0.02 or avg_price > 0.98:
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
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\b(will|the|a|an)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def _soft_topic(text: str) -> str:
    text = text.lower()
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,\s*20\d{2})?\b",
        " ",
        text,
    )
    text = re.sub(r"\b20\d{2}-\d{2}-\d{2}\b", " ", text)
    text = re.sub(r"\$?\b\d+(?:\.\d+)?\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\b(will|the|a|an|on|by|in|of|to|for|before|after|through|until|end)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_title_date(text: str, now: datetime) -> datetime | None:
    text = text.lower()
    m = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,\s*(20\d{2}))?\b",
        text,
    )
    if not m:
        return None
    month = _MONTHS.get(m.group(1))
    day = int(m.group(2))
    year = int(m.group(3) or now.year)
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def _has_deadline_language(text: str) -> bool:
    return bool(re.search(r"\b(by|before|through|until)\b|by end of|end of", text.lower()))


def _reward_max_spread(value) -> float:
    spread = _to_float(value, 0.0)
    return spread / 100 if spread > 1 else spread


def _market_trade_fields(market: dict) -> dict:
    token_ids = _market_token_ids(market)
    return {
        "slug": market.get("slug", ""),
        "condition_id": market.get("conditionId", ""),
        "token_ids": token_ids,
        "token_id": token_ids[0] if token_ids else "",
        "tick_size": _market_tick_size(market),
        "neg_risk": bool(market.get("negRisk", False)),
        "end_date_bj": to_beijing_time(market.get("endDate") or market.get("endDateIso")),
    }


async def _market_metadata_for_order(market_slug: str, token_id: str = "") -> dict:
    """Fetch fresh Gamma metadata so copy-trade orders use the correct exchange/tick fields."""
    if not market_slug:
        return {}
    try:
        market = await gamma_api.get_market_by_slug(market_slug)
    except Exception:
        return {}
    if not market:
        return {}
    now = datetime.now(timezone.utc)
    if not _is_tradable_market(market, now):
        raise ValueError("该市场已结束、进入结算或当前不接单，禁止从机会页下单")
    token_ids = _market_token_ids(market)
    if token_id and token_ids and str(token_id) not in {str(t) for t in token_ids}:
        raise ValueError("token 与市场元数据不匹配，禁止下单")
    return {
        "market_slug": market.get("slug") or market_slug,
        "condition_id": market.get("conditionId") or "",
        "tick_size": _market_tick_size(market),
        "neg_risk": bool(market.get("negRisk", False)),
        "token_ids": token_ids,
        "accepting_orders": market.get("acceptingOrders", True),
    }


async def _ensure_market_safe_to_buy(market_slug: str) -> None:
    await _market_metadata_for_order(market_slug)


async def cross_event_pair_depth(
    buy_candidate: dict,
    sell_reference: dict,
    amount_usdc: float = 0,
    min_profit_pct: float = 0.0,
) -> dict:
    if amount_usdc <= 0:
        amount_usdc = 100.0
    low_token = buy_candidate.get("token_id") or (buy_candidate.get("token_ids") or [""])[0]
    hedge_tokens = sell_reference.get("token_ids") or []
    hedge_token = hedge_tokens[1] if len(hedge_tokens) > 1 else sell_reference.get("hedge_token_id", "")
    if not low_token or not hedge_token:
        return {"fillable": False, "reason": "低价端 YES 或高价端 NO token 缺失"}

    low_book, hedge_book = await asyncio.gather(
        clob_api.get_orderbook(low_token),
        clob_api.get_orderbook(hedge_token),
    )
    low_levels = _book_levels(low_book, "BUY")
    hedge_levels = _book_levels(hedge_book, "BUY")
    depth = _consume_pair_by_budget(
        low_levels,
        hedge_levels,
        budget_usdc=amount_usdc,
        min_profit_pct=min_profit_pct,
    )
    max_depth = _consume_pair_by_budget(
        low_levels,
        hedge_levels,
        budget_usdc=0,
        min_profit_pct=min_profit_pct,
    )
    depth.update({
        "mode": "BUY_LOW_YES_BUY_HIGH_NO",
        "max_capacity_usdc": max_depth.get("capacity_usdc", 0.0),
        "max_expected_profit": max_depth.get("expected_profit", 0.0),
        "max_target_shares": max_depth.get("target_shares", 0.0),
        "low_token_id": low_token,
        "hedge_token_id": hedge_token,
        "low_market_slug": buy_candidate.get("slug", ""),
        "hedge_market_slug": sell_reference.get("slug", ""),
        "low_condition_id": buy_candidate.get("condition_id", ""),
        "hedge_condition_id": sell_reference.get("condition_id", ""),
        "low_tick_size": buy_candidate.get("tick_size") or "0.01",
        "hedge_tick_size": sell_reference.get("tick_size") or "0.01",
        "low_neg_risk": bool(buy_candidate.get("neg_risk", False)),
        "hedge_neg_risk": bool(sell_reference.get("neg_risk", False)),
    })
    return depth


async def scan_cross_event_spreads(
    min_spread: float = 0.08,
    max_candidates: int = 300,
    budget_usdc: float = 100,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    markets = await _fetch_gamma_pages(
        "markets",
        {"order": "volume24hr", "ascending": "false"},
        max_pages=max(1, (max_candidates + 99) // 100),
    )
    items = []
    for m in markets[:max_candidates]:
        if not _is_tradable_market(m, now):
            continue
        question = m.get("question") or ""
        key = _canonical_topic(question)
        if len(key) < 8:
            continue
        yes_price = _to_float(m.get("bestAsk") or _normalise_market(m)["yes_price"], 0.0)
        yes_bid = _to_float(m.get("bestBid") or yes_price, 0.0)
        items.append({
            **_market_trade_fields(m),
            "key": key,
            "soft_key": _soft_topic(question),
            "title_date": _extract_title_date(question, now),
            "question": question,
            "question_zh": translate_title(question),
            "yes_price": yes_price,
            "best_bid": yes_bid,
            "volume_24h": _market_volume_24h(m),
            "end_date_bj": to_beijing_time(m.get("endDate") or m.get("endDateIso")),
        })

    spreads = []
    seen_pair_keys = set()

    groups_by_key: dict[str, list[dict]] = {}
    for item in items:
        groups_by_key.setdefault(item["key"], []).append(item)

    for group in groups_by_key.values():
        if len(group) < 2:
            continue
        low = min(group, key=lambda x: x["yes_price"])
        high = max(group, key=lambda x: x["best_bid"])
        pair_key = tuple(sorted([low["slug"], high["slug"]])) + ("exact",)
        if pair_key in seen_pair_keys:
            continue
        spread = high["best_bid"] - low["yes_price"]
        if spread < min_spread:
            continue
        seen_pair_keys.add(pair_key)
        spreads.append({
            "topic": low["key"],
            "topic_zh": translate_title(low["question"]),
            "spread": round(spread, 4),
            "relation_type": "EXACT_DUPLICATE",
            "strategy_label": "同题重复盘",
            "buy_candidate": low,
            "sell_reference": high,
            "markets": sorted(group, key=lambda x: x["yes_price"]),
            "note": "两个市场标题完全一致；按低价 YES + 高价参考 NO 做预算预检。",
        })

    groups_by_soft_key: dict[str, list[dict]] = {}
    for item in items:
        if len(item.get("soft_key", "")) >= 8:
            groups_by_soft_key.setdefault(item["soft_key"], []).append(item)

    for group in groups_by_soft_key.values():
        if len(group) < 2:
            continue
        dated = [g for g in group if g.get("title_date") and _has_deadline_language(g.get("question", ""))]
        if len(dated) < 2:
            continue
        dated.sort(key=lambda x: x["title_date"])
        for earlier, later in zip(dated, dated[1:]):
            if earlier["title_date"] >= later["title_date"]:
                continue
            pair_key = tuple(sorted([earlier["slug"], later["slug"]])) + ("date",)
            if pair_key in seen_pair_keys:
                continue
            no_proxy = 1.0 - (earlier["best_bid"] if earlier["best_bid"] > 0 else earlier["yes_price"])
            rough_edge = 1.0 - (later["yes_price"] + no_proxy)
            seen_pair_keys.add(pair_key)
            spreads.append({
                "topic": later["soft_key"],
                "topic_zh": translate_title(later["question"]),
                "spread": round(rough_edge, 4),
                "relation_type": "DATE_SUPERSET",
                "strategy_label": "到期包含价差",
                "buy_candidate": later,
                "sell_reference": earlier,
                "markets": sorted(group, key=lambda x: x["title_date"] or now),
                "note": "后到期 YES + 前到期 NO：仅适用于同一事件口径下“前到期发生则后到期也发生”的包含关系，提交前仍需人工确认规则文本。",
            })

    spreads.sort(key=lambda x: x["spread"], reverse=True)
    spreads = spreads[:50]

    sem = asyncio.Semaphore(8)

    async def attach_depth(item: dict) -> dict:
        async with sem:
            try:
                item["pair_depth"] = await cross_event_pair_depth(
                    item["buy_candidate"],
                    item["sell_reference"],
                    amount_usdc=budget_usdc,
                    min_profit_pct=0.0,
                )
                item["pair_depth"]["strategy_label"] = item.get("strategy_label", "")
                item["pair_depth"]["relation_type"] = item.get("relation_type", "")
            except Exception as e:
                item["pair_depth"] = {"fillable": False, "reason": str(e)}
        item["executable"] = bool(item.get("pair_depth", {}).get("fillable"))
        return item

    return await asyncio.gather(*(attach_depth(s) for s in spreads))


async def scan_reward_making_markets(max_candidates: int = 300) -> list[dict]:
    now = datetime.now(timezone.utc)
    markets = await _fetch_gamma_pages(
        "markets",
        {"order": "volume24hr", "ascending": "false"},
        max_pages=max(1, (max_candidates + 99) // 100),
    )
    results = []
    for m in markets[:max_candidates]:
        if not _is_tradable_market(m, now):
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
            **_market_trade_fields(m),
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
            "end_date_min": now.isoformat().replace("+00:00", "Z"),
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
        if not end_dt or end_dt < now or end_dt > cutoff:
            continue
        hours_left = (end_dt - now).total_seconds() / 3600 if end_dt else None
        status = m.get("umaResolutionStatus") or "ending_soon"
        can_buy = _is_tradable_market(m, now)
        disabled_reason = ""
        if not can_buy:
            if status != "ending_soon":
                disabled_reason = f"市场已进入 {status} 状态，只观察不下单"
            elif m.get("acceptingOrders") is False:
                disabled_reason = "市场当前不接单"
            else:
                disabled_reason = "市场已结束或不可交易"
        results.append({
            **_market_trade_fields(m),
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
            "can_buy": can_buy,
            "trade_disabled_reason": disabled_reason,
            "note": "可交易临近结算盘可小额 FOK；进入 proposed/resolved 或不接单时只做复盘观察。",
        })
    results.sort(key=lambda x: (not x.get("can_buy"), x["hours_left"] is None, x["hours_left"] or 999, -x["volume_24h"]))
    return results[:100]


def _basket_markets_for_integrity(event: dict) -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        m for m in event.get("markets", [])
        if _is_tradable_market(m, now)
    ]


def _shadow_bid_from_book(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    tick_size: str,
    max_price: float = 0.03,
    improve_ticks: int = 1,
) -> float:
    tick = float(tick_size or "0.01")
    base = bids[0][0] + max(improve_ticks, 0) * tick if bids else tick
    if asks:
        base = min(base, asks[0][0] - tick)
    base = min(base, max_price)
    return _snap_to_tick(base, tick_size) if base > 0 else 0.0


async def basket_precheck(
    event_slug: str,
    budget_usdc: float = 100,
    shadow_price_cap: float = 0.03,
    shadow_improve_ticks: int = 1,
) -> dict:
    event = await gamma_api.get_event(event_slug)
    if not event:
        raise ValueError("事件不存在")
    now = datetime.now(timezone.utc)
    safety = _basket_event_safety(event, now)
    if not safety.get("ok"):
        raise ValueError(f"该篮子不可执行：{safety.get('reason')}")
    markets = safety["markets"]
    if len(markets) < 2:
        raise ValueError("该事件没有足够的可交易结果")
    integrity = _basket_integrity(event, markets)

    leg_books = []
    shadow_books = []
    ask_sum = 0.0
    sem = asyncio.Semaphore(10)

    async def load_market_book(m: dict):
        token_id = _market_token_ids(m)[0]
        tick_size = _market_tick_size(m)
        async with sem:
            try:
                book = await clob_api.get_orderbook(token_id)
                asks = _book_levels(book, "BUY")
                bids = _book_levels(book, "SELL")
            except Exception:
                asks = []
                bids = []
        return m, token_id, tick_size, bids, asks

    for m, token_id, tick_size, bids, asks in await asyncio.gather(*(load_market_book(m) for m in markets)):
        if not asks or asks[0][0] <= 0 or asks[0][0] >= 1:
            shadow_price = _shadow_bid_from_book(
                bids,
                asks,
                tick_size,
                max_price=shadow_price_cap,
                improve_ticks=shadow_improve_ticks,
            )
            shadow_books.append((m, token_id, bids, asks, shadow_price))
            ask_sum += shadow_price
            continue
        ask_sum += asks[0][0]
        leg_books.append((m, token_id, asks))

    if ask_sum <= 0:
        raise ValueError("无法计算篮子成本")
    complete_enough = BASKET_MIN_BUY_SUM <= ask_sum <= BASKET_MAX_BUY_SUM
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
            "neg_risk": bool(m.get("negRisk", True)),
            "depth": depth,
        })

    shadow_legs = []
    shadow_cost = 0.0
    for m, token_id, bids, asks, shadow_price in shadow_books:
        cost = target_shares * shadow_price if shadow_price > 0 else 0.0
        shadow_cost += cost
        shadow_legs.append({
            "slug": m.get("slug", ""),
            "condition_id": m.get("conditionId", ""),
            "question": m.get("question", ""),
            "question_zh": translate_title(m.get("question", "")),
            "token_id": token_id,
            "tick_size": _market_tick_size(m),
            "neg_risk": bool(m.get("negRisk", True)),
            "suggested_price": round(shadow_price, 4),
            "target_shares": round(target_shares, 4),
            "estimated_cost": round(cost, 4),
            "best_bid": round(bids[0][0], 4) if bids else 0.0,
            "best_ask": round(asks[0][0], 4) if asks else 0.0,
            "reason": "缺少可直接买入的 YES 卖盘，建议用 post-only 影子挂单补腿。",
        })

    payout = target_shares
    expected_total_cost = total_cost + shadow_cost
    profit = payout - expected_total_cost
    fillable = bool(integrity["ok"] and not shadow_legs and fillable and profit > 0 and complete_enough)
    if not integrity["ok"]:
        note = integrity["note"]
    elif shadow_legs:
        note = f"池子完整，但有 {len(shadow_legs)} 个盘口缺可直接吃单卖价；禁止一键买入，可先提交影子挂单补腿。"
    elif complete_enough:
        note = "池子完整性已校验；预检按买入每个 YES 相同份额计算，成交前仍可能因盘口变化而失效。"
    else:
        note = f"YES 总和 {ask_sum:.4f} 不在安全区间 {BASKET_MIN_BUY_SUM:.2f}-{BASKET_MAX_BUY_SUM:.3f}，不要按整篮套利执行。"
    return {
        "event_slug": event_slug,
        "title": event.get("title", ""),
        "title_zh": translate_title(event.get("title", "")),
        "budget_usdc": budget_usdc,
        "integrity": integrity,
        "target_shares": round(target_shares, 4),
        "total_cost": round(total_cost, 4),
        "shadow_cost": round(shadow_cost, 4),
        "expected_total_cost": round(expected_total_cost, 4),
        "payout_if_complete": round(payout, 4),
        "estimated_profit": round(profit, 4),
        "estimated_profit_pct": round((profit / expected_total_cost * 100) if expected_total_cost > 0 else 0, 2),
        "fillable": fillable,
        "can_shadow": bool(integrity["ok"] and shadow_legs),
        "legs": legs,
        "shadow_legs": shadow_legs,
        "note": note,
    }


async def execute_basket_buy(
    user: User,
    db: AsyncSession,
    event_slug: str,
    budget_usdc: float = 100,
    min_profit_pct: float = 0.2,
) -> dict:
    precheck = await basket_precheck(event_slug, budget_usdc)
    if not precheck.get("fillable"):
        raise ValueError(precheck.get("note") or "篮子当前不可执行")
    if precheck.get("estimated_profit_pct", 0) < min_profit_pct:
        raise ValueError(f"预估毛利低于阈值 {min_profit_pct:.2f}%")

    target_shares = float(precheck["target_shares"])
    orders = []
    for leg in precheck["legs"]:
        depth = leg.get("depth") or {}
        limit_price = _to_float(depth.get("worst_price") or depth.get("avg_price") or depth.get("best_price"), 0.0)
        if limit_price <= 0:
            raise ValueError(f"{leg.get('question_zh') or leg.get('question')} 缺少可用限价")
        orders.append({
            "token_id": leg["token_id"],
            "price": limit_price,
            "size": target_shares,
            "side": "BUY",
            "order_type": "FOK",
            "tick_size": leg.get("tick_size") or "0.01",
            "neg_risk": bool(leg.get("neg_risk", True)),
            "market_slug": leg.get("slug", ""),
            "condition_id": leg.get("condition_id", ""),
        })

    batch = await place_limit_orders_batch(user, db, orders)
    return {
        "success": batch.get("success") and len(batch.get("orders", [])) == len(orders),
        "event_slug": event_slug,
        "precheck": precheck,
        "orders": batch.get("orders", []),
        "failed": batch.get("failed", []),
        "message": (
            "已批量提交 FOK 篮子订单。FOK 会避免吃不到足额时留下挂单，但交易所不保证多腿原子成交；请到订单页核对。"
        ),
        "response": batch.get("response"),
    }


async def execute_basket_shadow_orders(
    user: User,
    db: AsyncSession,
    event_slug: str,
    budget_usdc: float = 100,
    shadow_price_cap: float = 0.03,
    improve_ticks: int = 1,
) -> dict:
    precheck = await basket_precheck(
        event_slug,
        budget_usdc,
        shadow_price_cap=shadow_price_cap,
        shadow_improve_ticks=improve_ticks,
    )
    integrity = precheck.get("integrity") or {}
    if not integrity.get("ok"):
        raise ValueError(integrity.get("note") or "池子完整性未通过，禁止影子挂单")
    shadow_legs = precheck.get("shadow_legs") or []
    if not shadow_legs:
        raise ValueError("当前没有需要影子挂单补腿的盘口")

    orders = []
    for leg in shadow_legs:
        price = _to_float(leg.get("suggested_price"), 0.0)
        size = _to_float(leg.get("target_shares"), 0.0)
        if price <= 0 or price > shadow_price_cap:
            raise ValueError(f"{leg.get('question_zh') or leg.get('question')} 影子价格无效或超过上限")
        if size < 5:
            raise ValueError(f"{leg.get('question_zh') or leg.get('question')} 影子挂单份额不足 5")
        orders.append({
            "token_id": leg["token_id"],
            "price": price,
            "size": size,
            "side": "BUY",
            "order_type": "GTC",
            "tick_size": leg.get("tick_size") or "0.01",
            "neg_risk": bool(leg.get("neg_risk", True)),
            "market_slug": leg.get("slug", ""),
            "condition_id": leg.get("condition_id", ""),
        })

    batch = await place_limit_orders_batch(user, db, orders, post_only=True)
    return {
        "success": batch.get("success") and len(batch.get("orders", [])) == len(orders),
        "event_slug": event_slug,
        "precheck": precheck,
        "orders": batch.get("orders", []),
        "failed": batch.get("failed", []),
        "message": "已为缺盘口结果提交 post-only 影子买单；成交后请重新预检篮子，再决定是否一键买入其余腿。",
        "response": batch.get("response"),
    }


async def quick_buy_token(
    user: User,
    db: AsyncSession,
    token_id: str,
    amount_usdc: float = 0,
    size: float = 0,
    limit_price: float = 0,
    order_type: str = "FOK",
    tick_size: str = "0.01",
    neg_risk: bool = False,
    market_slug: str = "",
    condition_id: str = "",
) -> dict:
    metadata = await _market_metadata_for_order(market_slug, token_id)
    if metadata:
        market_slug = metadata.get("market_slug") or market_slug
        condition_id = metadata.get("condition_id") or condition_id
        tick_size = metadata.get("tick_size") or tick_size
        neg_risk = bool(metadata.get("neg_risk", neg_risk))
    if size > 0 and limit_price > 0:
        result = await place_limit_order(
            user, db,
            token_id=token_id,
            price=limit_price,
            size=size,
            side="BUY",
            order_type=order_type,
            tick_size=tick_size,
            neg_risk=neg_risk,
            market_slug=market_slug,
            condition_id=condition_id,
        )
    elif amount_usdc > 0:
        result = await place_limit_order(
            user, db,
            token_id=token_id,
            price=0,
            size=0,
            side="BUY",
            order_type=order_type,
            tick_size=tick_size,
            neg_risk=neg_risk,
            market_slug=market_slug,
            condition_id=condition_id,
            usdc_amount=amount_usdc,
        )
    else:
        raise ValueError("请提供买入金额，或提供份额和限价")
    result["message"] = "已提交快捷买入订单"
    return result


async def quick_sell_token(
    user: User,
    db: AsyncSession,
    token_id: str,
    size: float,
    tick_size: str = "0.01",
    neg_risk: bool = False,
    market_slug: str = "",
    condition_id: str = "",
) -> dict:
    result = await sell_position(
        user, db,
        token_id=token_id,
        size=size,
        tick_size=tick_size,
        neg_risk=neg_risk,
        market_slug=market_slug,
        condition_id=condition_id,
    )
    result["message"] = "已提交快捷卖出订单"
    return result


async def execute_slippage_batch_buy(
    user: User,
    db: AsyncSession,
    items: list[dict],
    amount_usdc: float = 25,
    max_slippage_pct: float = 2.0,
) -> dict:
    if not items:
        raise ValueError("请选择至少一个盘口")
    if len(items) > 25:
        raise ValueError("一次最多批量买入 25 个盘口")

    sem = asyncio.Semaphore(8)

    async def precheck(item: dict) -> dict:
        token_id = item.get("token_id") or (item.get("token_ids") or [""])[0]
        if not token_id:
            return {"ok": False, "item": item, "reason": "缺少 token_id"}
        try:
            await _ensure_market_safe_to_buy(item.get("slug", ""))
        except Exception as e:
            return {"ok": False, "item": item, "reason": str(e)}
        async with sem:
            try:
                depth = await _orderbook_depth(token_id, amount_usdc)
            except Exception as e:
                return {"ok": False, "item": item, "reason": f"盘口获取失败: {e}"}
        if not depth.get("fillable"):
            return {"ok": False, "item": item, "depth": depth, "reason": "当前盘口吃不满设置金额"}
        if depth.get("slippage_pct", 0) > max_slippage_pct:
            return {
                "ok": False,
                "item": item,
                "depth": depth,
                "reason": f"当前滑点 {depth.get('slippage_pct')}% 超过阈值 {max_slippage_pct}%",
            }
        if depth.get("worst_price", 0) <= 0 or depth.get("shares", 0) < 5:
            return {"ok": False, "item": item, "depth": depth, "reason": "份额不足 5 或缺少有效限价"}
        return {"ok": True, "item": item, "depth": depth}

    checks = await asyncio.gather(*(precheck(i) for i in items))
    failed_checks = [c for c in checks if not c.get("ok")]
    if failed_checks:
        first = failed_checks[0]
        title = first.get("item", {}).get("title_zh") or first.get("item", {}).get("title") or first.get("item", {}).get("slug") or "某盘口"
        raise ValueError(f"{title}: {first.get('reason')}；已取消整批提交，请重扫后再试")

    orders = []
    total_amount = 0.0
    for check in checks:
        item = check["item"]
        depth = check["depth"]
        total_amount += float(depth.get("spent") or amount_usdc)
        orders.append({
            "token_id": item.get("token_id") or (item.get("token_ids") or [""])[0],
            "price": depth["worst_price"],
            "size": depth["shares"],
            "side": "BUY",
            "order_type": "FOK",
            "tick_size": item.get("tick_size") or "0.01",
            "neg_risk": bool(item.get("neg_risk", False)),
            "market_slug": item.get("slug", ""),
            "condition_id": item.get("condition_id", ""),
        })

    batch = await place_limit_orders_batch(user, db, orders)
    return {
        "success": batch.get("success") and len(batch.get("orders", [])) == len(orders),
        "amount_per_market": amount_usdc,
        "total_checked_cost": round(total_amount, 4),
        "prechecks": checks,
        "orders": batch.get("orders", []),
        "failed": batch.get("failed", []),
        "message": "已按当前盘口重新预检并批量提交 FOK 买入；FOK 不成交则不会留下残单。",
        "response": batch.get("response"),
    }


async def execute_hedge_close_batch(
    user: User,
    db: AsyncSession,
    items: list[dict],
    fraction: float = 1.0,
) -> dict:
    if not items:
        raise ValueError("请选择至少一个持仓")
    if len(items) > 25:
        raise ValueError("一次最多平仓 25 个持仓")
    fraction = min(max(float(fraction or 1.0), 0.01), 1.0)

    sem = asyncio.Semaphore(8)

    async def precheck(item: dict) -> dict:
        token_id = item.get("asset") or item.get("token_id") or item.get("tokenId")
        size = _to_float(item.get("size"), 0.0) * fraction
        if not token_id:
            return {"ok": False, "item": item, "reason": "缺少持仓 token"}
        if size < 5:
            return {"ok": False, "item": item, "reason": "平仓份额不足 5"}
        async with sem:
            try:
                book = await clob_api.get_orderbook(token_id)
            except Exception as e:
                return {"ok": False, "item": item, "reason": f"订单簿获取失败: {e}"}
        depth = _consume_by_shares(_book_levels(book, "SELL"), size)
        if not depth.get("fillable"):
            return {"ok": False, "item": item, "depth": depth, "reason": "买盘深度不足，无法 FOK 平仓"}
        if depth.get("worst_price", 0) <= 0:
            return {"ok": False, "item": item, "depth": depth, "reason": "缺少有效买盘"}
        return {"ok": True, "item": item, "size": round(size, 4), "depth": depth}

    checks = await asyncio.gather(*(precheck(i) for i in items))
    failed_checks = [c for c in checks if not c.get("ok")]
    if failed_checks:
        first = failed_checks[0]
        title = first.get("item", {}).get("title_zh") or first.get("item", {}).get("title") or first.get("item", {}).get("asset") or "某持仓"
        raise ValueError(f"{title}: {first.get('reason')}；已取消整批平仓")

    orders = []
    for check in checks:
        item = check["item"]
        depth = check["depth"]
        orders.append({
            "token_id": item.get("asset") or item.get("token_id") or item.get("tokenId"),
            "price": depth["worst_price"],
            "size": check["size"],
            "side": "SELL",
            "order_type": "FOK",
            "tick_size": item.get("tick_size") or "0.01",
            "neg_risk": bool(item.get("neg_risk", False)),
            "market_slug": item.get("slug", ""),
            "condition_id": item.get("condition_id", ""),
        })

    batch = await place_limit_orders_batch(user, db, orders)
    return {
        "success": batch.get("success") and len(batch.get("orders", [])) == len(orders),
        "fraction": fraction,
        "prechecks": checks,
        "orders": batch.get("orders", []),
        "failed": batch.get("failed", []),
        "message": "已按当前 best bid 深度预检并批量提交 FOK 平仓；深度不足的订单不会留下挂单。",
        "response": batch.get("response"),
    }


async def execute_cross_event_hedge(
    user: User,
    db: AsyncSession,
    buy_candidate: dict,
    sell_reference: dict,
    amount_usdc: float = 0,
    min_profit_pct: float = 0.2,
) -> dict:
    await asyncio.gather(
        _ensure_market_safe_to_buy(buy_candidate.get("slug", "")),
        _ensure_market_safe_to_buy(sell_reference.get("slug", "")),
    )
    depth = await cross_event_pair_depth(
        buy_candidate,
        sell_reference,
        amount_usdc=amount_usdc,
        min_profit_pct=min_profit_pct,
    )
    if not depth.get("fillable"):
        raise ValueError(depth.get("reason") or "同题价差双边深度不足，无法安全执行")

    size = float(depth["target_shares"])
    orders = [
        {
            "token_id": depth["low_token_id"],
            "price": depth["low_leg"]["worst_price"],
            "size": size,
            "side": "BUY",
            "order_type": "FOK",
            "tick_size": depth["low_tick_size"],
            "neg_risk": depth["low_neg_risk"],
            "market_slug": depth["low_market_slug"],
            "condition_id": depth["low_condition_id"],
        },
        {
            "token_id": depth["hedge_token_id"],
            "price": depth["hedge_leg"]["worst_price"],
            "size": size,
            "side": "BUY",
            "order_type": "FOK",
            "tick_size": depth["hedge_tick_size"],
            "neg_risk": depth["hedge_neg_risk"],
            "market_slug": depth["hedge_market_slug"],
            "condition_id": depth["hedge_condition_id"],
        },
    ]
    batch = await place_limit_orders_batch(user, db, orders)

    cancel_attempts = []
    if not batch.get("success"):
        for order in batch.get("orders", []):
            oid = order.get("order_id")
            if not oid:
                continue
            try:
                cancel_attempts.append(await cancel_order(user, db, oid))
            except Exception as e:
                cancel_attempts.append({"order_id": oid, "error": str(e)})

    return {
        "success": batch.get("success") and len(batch.get("orders", [])) == 2,
        "depth": depth,
        "orders": batch.get("orders", []),
        "failed": batch.get("failed", []),
        "cancel_attempts": cancel_attempts,
        "message": (
            "已用两条 FOK 批量提交低价 YES + 高价 NO 对冲。CLOB 不提供跨市场原子成交；"
            "若任一腿返回失败，系统会立即尝试撤销另一腿残留挂单。"
        ),
        "response": batch.get("response"),
    }


def _snap_to_tick(price: float, tick_size: str) -> float:
    tick = float(tick_size or "0.01")
    decimals = len(str(tick_size).rstrip("0").split(".", 1)[1]) if "." in str(tick_size) else 0
    return round(min(max(price, tick), 1.0 - tick), decimals)


async def _maker_bid_price(token_id: str, tick_size: str, improve_ticks: int = 0) -> float:
    book = await clob_api.get_orderbook(token_id)
    bids = _book_levels(book, "SELL")
    asks = _book_levels(book, "BUY")
    tick = float(tick_size or "0.01")
    if bids:
        price = bids[0][0] + max(improve_ticks, 0) * tick
    elif asks:
        price = asks[0][0] - tick
    else:
        return 0.0
    if asks:
        price = min(price, asks[0][0] - tick)
    return _snap_to_tick(price, tick_size) if price > 0 else 0.0


async def place_reward_maker_quote(
    user: User,
    db: AsyncSession,
    market_slug: str,
    amount_per_side: float = 10,
    improve_ticks: int = 0,
) -> dict:
    market = await gamma_api.get_market_by_slug(market_slug)
    if not market:
        raise ValueError("市场不存在")
    token_ids = _market_token_ids(market)
    if len(token_ids) < 2:
        raise ValueError("该市场不是 YES/NO 双结果市场")

    tick_size = _market_tick_size(market)
    rewards_min = _to_float(market.get("rewardsMinSize"), 0.0)
    orders = []
    labels = ["YES", "NO"]
    for token_id, label in zip(token_ids[:2], labels):
        price = await _maker_bid_price(token_id, tick_size, improve_ticks)
        if price <= 0:
            raise ValueError(f"{label} 订单簿没有可挂买价")
        size = amount_per_side / price
        if rewards_min > 0 and size < rewards_min:
            need = rewards_min * price
            raise ValueError(f"{label} 单边金额不足奖励最小份额，至少约 {need:.2f} USDC")
        orders.append({
            "token_id": token_id,
            "price": price,
            "size": size,
            "side": "BUY",
            "order_type": "GTC",
            "tick_size": tick_size,
            "neg_risk": bool(market.get("negRisk", False)),
            "market_slug": market.get("slug", ""),
            "condition_id": market.get("conditionId", ""),
        })

    batch = await place_limit_orders_batch(user, db, orders, post_only=True)
    return {
        "success": batch.get("success") and len(batch.get("orders", [])) == len(orders),
        "market_slug": market_slug,
        "orders": batch.get("orders", []),
        "failed": batch.get("failed", []),
        "message": "已提交 YES/NO 双边 post-only 做市委托；请在订单页检查是否持续 scoring。",
        "response": batch.get("response"),
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
            "end_date_bj": to_beijing_time(p.get("endDate") or p.get("endDateIso")),
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
