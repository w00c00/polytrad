import json
import logging
import asyncio
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.polymarket import gamma_api, clob_api, to_beijing_time, translate_title
from app.models import ScanResult

logger = logging.getLogger(__name__)

# P3 #18: 扫描结果缓存（避免重复点击重复请求 API）
_scan_cache: dict[str, tuple[float, list]] = {}
_CACHE_TTL_SECONDS = 120  # 2 分钟


async def _cached_scan(key: str, scan_func, *args, **kwargs) -> list:
    """带内存缓存的扫描包装"""
    now = time.time()
    if key in _scan_cache:
        ts, data = _scan_cache[key]
        if now - ts < _CACHE_TTL_SECONDS:
            logger.debug(f"scan cache hit: {key}")
            return data
    data = await scan_func(*args, **kwargs)
    _scan_cache[key] = (now, data)
    return data

# Polymarket 政治相关 tag 的常见 slug 片段
POLITICAL_KEYWORDS = ["politic", "election", "president", "congress", "senate", "governor", "democrat", "republican", "trump", "biden"]
CHINA_KEYWORDS = ["china", "chinese", "beijing", "xi jinping", "xi jin ping", "ccp", "communist party of china", "taiwan", "hong kong", "hongkong", "tibet", "xinjiang", "中国", "中共", "习近平", "台湾", "香港", "西藏", "新疆"]
SPORTS_KEYWORDS = [
    # 通用 + 联盟
    "sport", "nfl", "nba", "mlb", "nhl", "soccer", "football", "basketball",
    "tennis", "ufc", "f1", "fifa",
    # 网球大满贯（event 标题常见词）
    "roland garros", "french open", "wimbledon", "australian open", "us open",
    "atp", "wta", "grand slam",
    # 其他主要赛事
    "world cup", "olympics", "copa america", "euro", "champions league",
    "premier league", "la liga", "bundesliga", "serie a", "ligue 1",
    "super bowl", "world series", "stanley cup", "playoffs",
]


def _json_list(value, default=None) -> list:
    """Gamma 有些数组字段以 JSON 字符串返回，这里统一转成 list。"""
    if default is None:
        default = []
    if value is None:
        return default
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else default
        except json.JSONDecodeError:
            return default
    return default


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _extract_tags(item: dict) -> set[str]:
    tags = set()
    for tag in item.get("tags") or []:
        if isinstance(tag, dict):
            for key in ("label", "slug", "id"):
                if tag.get(key) is not None:
                    tags.add(str(tag[key]).lower())
        else:
            tags.add(str(tag).lower())
    for key in ("category", "subcategory", "seriesSlug", "sportsMarketType"):
        if item.get(key):
            tags.add(str(item[key]).lower())
    return tags


def _combined_text(item: dict) -> str:
    parts = [
        item.get("title") or "",
        item.get("question") or "",
        item.get("description") or "",
        item.get("slug") or "",
        " ".join(_extract_tags(item)),
    ]
    return " ".join(parts).lower()


def _is_open(item: dict, now: datetime) -> bool:
    if item.get("closed") or item.get("archived") or item.get("ended"):
        return False
    if item.get("active") is False:
        return False
    end_dt = _parse_dt(item.get("endDate") or item.get("endDateIso"))
    if end_dt and end_dt < now:
        return False
    return True


def _market_yes_price(market: dict) -> float:
    prices = _json_list(market.get("outcomePrices"), ["0.5", "0.5"])
    return _to_float(prices[0], 0.5) if prices else 0.5


def _market_token_ids(market: dict) -> list:
    return _json_list(market.get("clobTokenIds"), [])


def _market_tick_size(market: dict) -> str:
    return str(market.get("minimumTickSize") or market.get("orderPriceMinTickSize") or "0.01")


def _market_volume_24h(market: dict) -> float:
    return _to_float(
        market.get("volume24hrClob")
        or market.get("volume24hr")
        or market.get("volumeClob")
        or market.get("volume"),
        0.0,
    )


def _market_liquidity(market: dict) -> float:
    return _to_float(market.get("liquidityClob") or market.get("liquidity") or market.get("liquidityNum"), 0.0)


def _normalise_market(market: dict, include_no_price: bool = True) -> dict:
    yes_price = _market_yes_price(market)
    data = {
        "slug": market.get("slug", ""),
        "condition_id": market.get("conditionId", ""),
        "question": market.get("question", ""),
        "question_zh": translate_title(market.get("question", "")),
        "yes_price": yes_price,
        "token_ids": _market_token_ids(market),
        "volume": _market_volume_24h(market),
        "liquidity": _market_liquidity(market),
        "score": market.get("score", ""),
        "neg_risk": bool(market.get("negRisk", False)),
        "tick_size": _market_tick_size(market),
        "sports_market_type": market.get("sportsMarketType"),
        "game_start_bj": to_beijing_time(market.get("gameStartTime") or market.get("eventStartTime")),
        "accepting_orders": market.get("acceptingOrders", True),
    }
    if include_no_price:
        data["no_price"] = 1 - yes_price
    return data


async def _fetch_gamma_pages(endpoint: str, params: dict, max_pages: int = 10, page_size: int = 100) -> list[dict]:
    items: list[dict] = []
    for offset in range(0, max_pages * page_size, page_size):
        page_params = {
            "active": "true",
            "closed": "false",
            "limit": page_size,
            "offset": offset,
            **params,
        }
        try:
            resp = await gamma_api.client.get(f"{gamma_api.base}/{endpoint}", params=page_params)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            items.extend(batch)
            if len(batch) < page_size:
                break
        except Exception as e:
            logger.warning("Gamma %s page offset=%s failed: %s", endpoint, offset, e)
            break
    return items


async def _save_scan(db: AsyncSession | None, scan_type: str, results: list[dict]) -> None:
    if not db:
        return
    scan = ScanResult(scan_type=scan_type, market_data=json.dumps(results, ensure_ascii=False))
    db.add(scan)
    await db.commit()

# BTC 短周期 series 列表
# timestamp 型: slug 格式为 {prefix}-{unix_ts}，可直接构造查询
BTC_TIMESTAMP_SERIES = [
    {"slug": "btc-up-or-down-5m", "prefix": "btc-updown-5m", "label": "5分钟", "interval": 300},
    {"slug": "btc-up-or-down-15m", "prefix": "btc-updown-15m", "label": "15分钟", "interval": 900},
    {"slug": "btc-up-or-down-4h", "prefix": "btc-updown-4h", "label": "4小时", "interval": 14400},
]
# series 型: 通过 series 端点获取 events，slug 为日期格式
BTC_SERIES_FETCH = [
    {"slug": "btc-up-or-down-hourly", "label": "1小时"},
    {"slug": "btc-up-or-down-daily", "label": "1天"},
]


def _extract_market_info(event: dict) -> list[dict]:
    """从 event 提取 markets 信息"""
    markets_info = []
    for m in event.get("markets", []):
        markets_info.append(_normalise_market(m))
    return markets_info


async def scan_btc_short_markets(db: AsyncSession | None) -> list[dict]:
    """扫描 BTC 短周期市场 (5m/15m/4h/1h/1d)"""
    # P3 #18: 2 分钟缓存
    return await _cached_scan("btc_short", _scan_btc_short_markets_inner, db)


async def _scan_btc_short_markets_inner(db: AsyncSession | None) -> list[dict]:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    now = datetime.now(timezone.utc)

    # 1. timestamp 型 series: 只查当前和未来的 3 个周期（P1 #7：从 6 减到 3，减少 API 调用）
    slugs = []
    for series_info in BTC_TIMESTAMP_SERIES:
        interval = series_info["interval"]
        prefix = series_info["prefix"]
        current_end = (now_ts // interval) * interval
        for offset in range(0, 3):
            ts = current_end + offset * interval
            slugs.append((f"{prefix}-{ts}", series_info["label"]))

    async def fetch_by_slug(slug, label):
        try:
            event = await gamma_api.get_event(slug)
            if not event:
                return None
            if not _is_open(event, now):
                return None
            title = event.get("title", "")
            return {
                "event_slug": event.get("slug", ""),
                "title": title,
                "title_zh": translate_title(title),
                "series_label": label,
                "start_time_bj": to_beijing_time(event.get("startTime") or event.get("startDate")),
                "end_time_bj": to_beijing_time(event.get("endDate")),
                "markets": _extract_market_info(event),
            }
        except Exception:
            return None

    # 2. series 型: 通过 series 端点获取 events，再查完整 event 数据，过滤已过期
    async def fetch_from_series(series_info):
        try:
            data = await gamma_api.get_series(series_info["slug"])
            if not data:
                return []
            events = data.get("events", [])
            results = []
            for event in events:
                if not _is_open(event, now):
                    continue
                slug = event.get("slug", "")
                full_event = await gamma_api.get_event(slug)
                if not full_event:
                    continue
                if not _is_open(full_event, now):
                    continue
                title = full_event.get("title", "")
                results.append({
                    "event_slug": slug,
                    "title": title,
                    "title_zh": translate_title(title),
                    "series_label": series_info["label"],
                    "start_time_bj": to_beijing_time(full_event.get("startTime") or full_event.get("startDate")),
                    "end_time_bj": to_beijing_time(full_event.get("endDate")),
                    "markets": _extract_market_info(full_event),
                })
            return results
        except Exception:
            return []

    tasks = [fetch_by_slug(slug, label) for slug, label in slugs]
    tasks += [fetch_from_series(s) for s in BTC_SERIES_FETCH]

    raw = await asyncio.gather(*tasks)
    results = []
    for r in raw:
        if isinstance(r, list):
            results.extend(r)
        elif r is not None:
            results.append(r)

    results.sort(key=lambda x: x.get("start_time_bj", ""))
    return results


async def scan_hot_markets(db: AsyncSession | None, hours_until_expiry: int = 24, min_volume: float = 5000) -> list[dict]:
    """扫描即将到期的热门市场。"""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_until_expiry)
    seen_slugs = set()
    results = []

    markets = await _fetch_gamma_pages(
        "markets",
        {
            "order": "volume24hr",
            "ascending": "false",
            "end_date_min": now.isoformat().replace("+00:00", "Z"),
            "end_date_max": cutoff.isoformat().replace("+00:00", "Z"),
        },
        max_pages=20,
    )

    for m in markets:
        if not _is_open(m, now):
            continue
        end = m.get("endDate") or m.get("endDateIso") or ""
        ed = _parse_dt(end)
        if not ed or ed > cutoff:
            continue
        vol = _market_volume_24h(m)
        if vol < min_volume:
            continue
        slug = m.get("slug", "")
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        q = m.get("question", "")
        market_info = _normalise_market(m)
        results.append({
            "event_slug": slug,
            "title": q,
            "title_zh": translate_title(q),
            "end_date_bj": to_beijing_time(end),
            "volume_24h": vol,
            "liquidity": market_info["liquidity"],
            "markets": [market_info],
        })

    results.sort(key=lambda x: x.get("end_date_bj", ""))

    await _save_scan(db, "hot", results)

    return results


async def scan_new_political_markets(db: AsyncSession | None) -> list[dict]:
    """扫描政治类新盘，优先使用 Gamma 的 politics tag，再用关键词兜底。"""
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=30)  # 只保留 30 天内创建的市场

    tagged_events = await _fetch_gamma_pages(
        "events",
        {"tag_slug": "politics", "order": "createdAt", "ascending": "false"},
        max_pages=10,
    )
    fallback_events = await _fetch_gamma_pages(
        "events",
        {"order": "createdAt", "ascending": "false"},
        max_pages=5,
    )

    events = []
    seen_event_slugs = set()
    for event in tagged_events + fallback_events:
        slug = event.get("slug", "")
        if not slug or slug in seen_event_slugs:
            continue
        seen_event_slugs.add(slug)
        events.append(event)

    results = []
    for event in events:
        if not _is_open(event, now):
            continue

        # 过滤 30 天前创建的市场
        created_str = event.get("createdAt") or event.get("creationDate") or ""
        created = _parse_dt(created_str)
        if created and created < recent_cutoff:
            continue

        combined = _combined_text(event)
        tags = _extract_tags(event)
        if "politics" not in tags and not any(kw in combined for kw in POLITICAL_KEYWORDS):
            continue

        markets_info = []
        for m in event.get("markets", []):
            if not _is_open(m, now):
                continue
            info = _normalise_market(m)
            if not info["token_ids"]:
                continue
            markets_info.append(info)

        if not markets_info:
            continue

        results.append({
            "event_slug": event.get("slug", ""),
            "title": event.get("title", ""),
            "title_zh": translate_title(event.get("title", "")),
            "created_at_bj": to_beijing_time(created_str),
            "start_date_bj": to_beijing_time(event.get("startDate") or event.get("startDateIso")),
            "end_date_bj": to_beijing_time(event.get("endDate") or event.get("endDateIso")),
            "volume_24h": _to_float(event.get("volume24hr") or event.get("volume"), 0.0),
            "markets": markets_info,
        })

    results.sort(key=lambda x: x.get("created_at_bj") or "", reverse=True)
    await _save_scan(db, "new_political", results)

    return results


async def scan_arbitrage(db: AsyncSession | None, threshold: float = 0.03) -> list[dict]:
    """扫描负风险多结果事件的 YES 篮子套利。"""
    now = datetime.now(timezone.utc)
    events = await _fetch_gamma_pages(
        "events",
        {"order": "volume24hr", "ascending": "false"},
        max_pages=15,
    )

    results = []
    for event in events:
        if not _is_open(event, now):
            continue

        markets = [m for m in event.get("markets", []) if _is_open(m, now)]
        if len(markets) < 2:
            continue

        neg_risk_ids = {str(m.get("negRiskMarketID")) for m in markets if m.get("negRiskMarketID")}
        is_neg_risk_event = bool(event.get("enableNegRisk") or event.get("negRisk") or neg_risk_ids)
        if not is_neg_risk_event:
            continue

        yes_ask_sum = 0.0
        yes_bid_sum = 0.0
        valid_buy_basket = True
        valid_sell_basket = True
        market_details = []

        for m in markets:
            info = _normalise_market(m)
            if not info["token_ids"] or not info.get("accepting_orders", True):
                valid_buy_basket = False
                valid_sell_basket = False
                continue
            yes_price = info["yes_price"]
            best_ask = _to_float(m.get("bestAsk"), 0.0)
            best_bid = _to_float(m.get("bestBid"), 0.0)
            if best_ask <= 0 or best_ask >= 1:
                valid_buy_basket = False
            else:
                yes_ask_sum += best_ask
            if best_bid <= 0 or best_bid >= 1:
                valid_sell_basket = False
            else:
                yes_bid_sum += best_bid
            info.update({
                "best_ask": best_ask or yes_price,
                "best_bid": best_bid or yes_price,
                "neg_risk": True,
            })
            market_details.append(info)

        if len(market_details) < 2:
            continue

        if valid_buy_basket and yes_ask_sum < 1.0 - threshold:
            direction = "BUY_YES"
            price_sum = yes_ask_sum
            deviation = 1.0 - yes_ask_sum
            executable = yes_ask_sum >= 0.85
            note = (
                "买入所有 YES 结果，完整篮子理论到期兑付 1 USDC。"
                if executable
                else "YES 总和过低，可能不是完整结果集，只作为观察候选。"
            )
        elif valid_sell_basket and yes_bid_sum > 1.0 + threshold:
            direction = "SELL_YES"
            price_sum = yes_bid_sum
            deviation = yes_bid_sum - 1.0
            executable = False
            note = "卖出所有 YES 需要已有库存或完整做市流程，当前版本不建议一键执行。"
        else:
            continue

        results.append({
            "event_slug": event.get("slug", ""),
            "title": event.get("title", ""),
            "title_zh": translate_title(event.get("title", "")),
            "yes_sum": round(price_sum, 4),
            "yes_ask_sum": round(yes_ask_sum, 4),
            "yes_bid_sum": round(yes_bid_sum, 4),
            "deviation": round(deviation, 4),
            "estimated_profit_pct": round(deviation * 100, 2),
            "direction": direction,
            "executable": executable,
            "execution_note": note,
            "end_date_bj": to_beijing_time(event.get("endDate") or event.get("endDateIso")),
            "markets": market_details,
        })

    results.sort(key=lambda x: x.get("deviation", 0), reverse=True)
    await _save_scan(db, "arbitrage", results)

    return results


async def scan_sports_markets(db: AsyncSession | None) -> list[dict]:
    """扫描体育赛事市场（含单场比赛）- P3 #18: 带 2 分钟缓存"""
    return await _cached_scan("sports", _scan_sports_markets_inner, db)


async def _scan_sports_markets_inner(db: AsyncSession | None) -> list[dict]:
    now = datetime.now(timezone.utc)
    one_year = now + timedelta(days=365)
    results = []
    seen_slugs = set()

    events = await _fetch_gamma_pages(
        "events",
        {"tag_slug": "sports", "order": "volume24hr", "ascending": "false"},
        max_pages=20,
    )

    def is_game_event(event: dict, markets_info: list[dict]) -> bool:
        tags = _extract_tags(event)
        title = (event.get("title") or "").lower()
        if "games" in tags or event.get("live") or event.get("score") or event.get("gameStatus"):
            return True
        if " vs " in title or " vs. " in title:
            return True
        return any(m.get("sports_market_type") and (m.get("game_start_bj") or "game" in str(m.get("sports_market_type"))) for m in markets_info)

    for event in events:
        slug = event.get("slug", "")
        if not slug or slug in seen_slugs:
            continue
        if not _is_open(event, now):
            continue
        end_dt = _parse_dt(event.get("endDate") or event.get("endDateIso"))
        if end_dt and end_dt > one_year:
            continue

        markets_info = []
        for m in event.get("markets", []):
            if not _is_open(m, now):
                continue
            info = _normalise_market(m)
            if not info["token_ids"]:
                continue
            markets_info.append(info)

        if not markets_info:
            continue

        seen_slugs.add(slug)
        game_event = is_game_event(event, markets_info)
        results.append({
            "event_slug": event.get("slug", ""),
            "title": event.get("title", ""),
            "title_zh": translate_title(event.get("title", "")),
            "end_date_bj": to_beijing_time(event.get("endDate") or event.get("endDateIso")),
            "start_time_bj": to_beijing_time(event.get("startTime") or event.get("startDate") or event.get("startDateIso")),
            "volume_24h": _to_float(event.get("volume24hr") or event.get("volume"), 0.0),
            "liquidity": _to_float(event.get("liquidityClob") or event.get("liquidity"), 0.0),
            "score": event.get("score", ""),
            "live": bool(event.get("live")),
            "period": event.get("period", ""),
            "markets": markets_info,
            "is_game": game_event,
        })

    results.sort(key=lambda x: (not x.get("is_game"), x.get("end_date_bj") or "99-99 99:99", -x.get("volume_24h", 0)))
    await _save_scan(db, "sports", results)

    return results
