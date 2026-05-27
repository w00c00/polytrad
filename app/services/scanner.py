import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.polymarket import gamma_api, clob_api, to_beijing_time, translate_title
from app.models import ScanResult

logger = logging.getLogger(__name__)

# Polymarket 政治相关 tag 的常见 slug 片段
POLITICAL_KEYWORDS = ["politic", "election", "president", "congress", "senate", "governor", "democrat", "republican", "trump", "biden"]
CHINA_KEYWORDS = ["china", "chinese", "beijing", "xi jinping", "xi jin ping", "ccp", "communist party of china", "taiwan", "hong kong", "hongkong", "tibet", "xinjiang", "中国", "中共", "习近平", "台湾", "香港", "西藏", "新疆"]
SPORTS_KEYWORDS = ["sport", "nfl", "nba", "mlb", "nhl", "soccer", "football", "basketball", "tennis", "ufc", "f1", "world cup"]

# BTC 短周期 series 列表
BTC_SHORT_SERIES = [
    {"slug": "btc-up-or-down-5m", "prefix": "btc-updown-5m", "label": "5分钟", "interval": 300},
    {"slug": "btc-up-or-down-15m", "prefix": "btc-updown-15m", "label": "15分钟", "interval": 900},
]


def _extract_market_info(event: dict) -> list[dict]:
    """从 event 提取 markets 信息"""
    markets_info = []
    for m in event.get("markets", []):
        prices = m.get("outcomePrices", '["0.5","0.5"]')
        if isinstance(prices, str):
            prices = json.loads(prices)
        yes_price = float(prices[0]) if prices else 0.5
        token_ids = m.get("clobTokenIds", [])
        if isinstance(token_ids, str):
            token_ids = json.loads(token_ids)
        markets_info.append({
            "slug": m.get("slug", ""),
            "question": m.get("question", ""),
            "yes_price": yes_price,
            "no_price": 1 - yes_price,
            "token_ids": token_ids,
            "neg_risk": m.get("negRisk", False),
            "tick_size": m.get("minimumTickSize", "0.01"),
        })
    return markets_info


async def scan_btc_short_markets(db: AsyncSession | None) -> list[dict]:
    """扫描 BTC 短周期市场 (5m/15m)，通过时间戳直接查当前周期"""
    import asyncio
    now_ts = int(datetime.now(timezone.utc).timestamp())

    # 构建所有需要查询的 slug
    slugs = []
    for series_info in BTC_SHORT_SERIES:
        interval = series_info["interval"]
        prefix = series_info["prefix"]
        current_end = (now_ts // interval) * interval
        for offset in range(-1, 6):
            ts = current_end + offset * interval
            slugs.append((f"{prefix}-{ts}", series_info["label"]))

    # 并发查询
    async def fetch_one(slug, label):
        try:
            event = await gamma_api.get_event(slug)
            if not event or not event.get("active"):
                return None
            return {
                "event_slug": event.get("slug", ""),
                "title": event.get("title", ""),
                "series_label": label,
                "start_time_bj": to_beijing_time(event.get("startTime") or event.get("startDate")),
                "end_time_bj": to_beijing_time(event.get("endDate")),
                "markets": _extract_market_info(event),
            }
        except Exception:
            return None

    tasks = [fetch_one(slug, label) for slug, label in slugs]
    raw = await asyncio.gather(*tasks)
    results = [r for r in raw if r is not None]
    results.sort(key=lambda x: x.get("start_time_bj", ""))
    return results


async def scan_hot_markets(db: AsyncSession, hours_until_expiry: int = 24, min_volume: float = 10000) -> list[dict]:
    """扫描即将到期的热门市场"""
    cutoff = datetime.now(timezone.utc) + timedelta(hours=hours_until_expiry)

    # 按 24h 成交量排序
    events = await gamma_api.get_events(order="volume_24hr", ascending=False, limit=100)

    results = []
    for event in events:
        end_str = event.get("endDate") or event.get("endDateIso")
        if not end_str:
            continue

        try:
            end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        if end_date > cutoff:
            continue

        vol = float(event.get("volume24hr") or event.get("volume") or 0)
        if vol < min_volume:
            continue

        # 排除中国相关内容
        title_lower = (event.get("title") or "").lower()
        if any(kw in title_lower for kw in CHINA_KEYWORDS):
            continue

        markets_info = []
        for m in event.get("markets", []):
            prices = m.get("outcomePrices", '["0.5","0.5"]')
            if isinstance(prices, str):
                prices = json.loads(prices)
            yes_price = float(prices[0]) if prices else 0.5
            markets_info.append({
                "slug": m.get("slug", ""),
                "question": m.get("question", ""),
                "yes_price": yes_price,
                "no_price": 1 - yes_price,
                "token_ids": json.loads(m["clobTokenIds"]) if isinstance(m.get("clobTokenIds"), str) else m.get("clobTokenIds", []),
                "volume": float(m.get("volume") or 0),
                "liquidity": float(m.get("liquidity") or 0),
                "neg_risk": m.get("negRisk", False),
                "tick_size": m.get("minimumTickSize", "0.01"),
            })

        results.append({
            "event_slug": event.get("slug", ""),
            "title": event.get("title", ""),
            "title_zh": translate_title(event.get("title", "")),
            "end_date_bj": to_beijing_time(end_str),
            "volume_24h": vol,
            "markets": markets_info,
        })

    # 保存扫描结果
    scan = ScanResult(scan_type="hot", market_data=json.dumps(results, ensure_ascii=False))
    db.add(scan)
    await db.commit()

    return results


async def scan_new_political_markets(db: AsyncSession) -> list[dict]:
    """扫描新创建的政治类市场"""
    events = await gamma_api.get_events(order="start_date", ascending=False, limit=50)

    results = []
    for event in events:
        title = (event.get("title") or "").lower()
        tags = [str(t).lower() for t in (event.get("tags") or [])]
        desc = (event.get("description") or "").lower()
        combined = title + " " + desc + " " + " ".join(tags)

        if not any(kw in combined for kw in POLITICAL_KEYWORDS):
            continue

        # 排除中国相关内容
        if any(kw in combined for kw in CHINA_KEYWORDS):
            continue

        markets_info = []
        for m in event.get("markets", []):
            prices = m.get("outcomePrices", '["0.5","0.5"]')
            if isinstance(prices, str):
                prices = json.loads(prices)
            yes_price = float(prices[0]) if prices else 0.5
            markets_info.append({
                "slug": m.get("slug", ""),
                "question": m.get("question", ""),
                "question_zh": translate_title(m.get("question", "")),
                "yes_price": yes_price,
                "token_ids": json.loads(m["clobTokenIds"]) if isinstance(m.get("clobTokenIds"), str) else m.get("clobTokenIds", []),
                "volume": float(m.get("volume") or 0),
                "neg_risk": m.get("negRisk", False),
                "tick_size": m.get("minimumTickSize", "0.01"),
            })

        results.append({
            "event_slug": event.get("slug", ""),
            "title": event.get("title", ""),
            "title_zh": translate_title(event.get("title", "")),
            "start_date_bj": to_beijing_time(event.get("startDate") or event.get("startDateIso")),
            "markets": markets_info,
        })

    scan = ScanResult(scan_type="new_political", market_data=json.dumps(results, ensure_ascii=False))
    db.add(scan)
    await db.commit()

    return results


async def scan_arbitrage(db: AsyncSession, threshold: float = 0.03) -> list[dict]:
    """扫描事件套利机会 (negRisk 多 market 事件的 YES 价格之和偏离 1.0)"""
    events = await gamma_api.get_events(active=True, closed=False, limit=100)

    results = []
    for event in events:
        # 排除中国相关内容
        title_lower = (event.get("title") or "").lower()
        if any(kw in title_lower for kw in CHINA_KEYWORDS):
            continue

        markets = event.get("markets", [])
        if len(markets) < 2:
            continue

        yes_sum = 0.0
        market_details = []
        valid = True

        for m in markets:
            prices = m.get("outcomePrices", '["0.5","0.5"]')
            if isinstance(prices, str):
                try:
                    prices = json.loads(prices)
                except json.JSONDecodeError:
                    valid = False
                    break
            yes_price = float(prices[0]) if prices else 0.5
            yes_sum += yes_price
            market_details.append({
                "slug": m.get("slug", ""),
                "question": m.get("question", ""),
                "yes_price": yes_price,
                "token_ids": json.loads(m["clobTokenIds"]) if isinstance(m.get("clobTokenIds"), str) else m.get("clobTokenIds", []),
                "neg_risk": True,
                "tick_size": m.get("minimumTickSize", "0.01"),
            })

        if not valid:
            continue

        deviation = abs(yes_sum - 1.0)
        if deviation < threshold:
            continue

        direction = "SELL_YES" if yes_sum > 1.0 else "BUY_YES"
        results.append({
            "event_slug": event.get("slug", ""),
            "title": event.get("title", ""),
            "title_zh": translate_title(event.get("title", "")),
            "yes_sum": round(yes_sum, 4),
            "deviation": round(deviation, 4),
            "direction": direction,
            "markets": market_details,
        })

    scan = ScanResult(scan_type="arbitrage", market_data=json.dumps(results, ensure_ascii=False))
    db.add(scan)
    await db.commit()

    return results


async def scan_sports_markets(db: AsyncSession) -> list[dict]:
    """扫描体育赛事市场"""
    events = await gamma_api.get_events(order="volume_24hr", ascending=False, limit=100)

    results = []
    for event in events:
        title = (event.get("title") or "").lower()
        tags = [str(t).lower() for t in (event.get("tags") or [])]
        combined = title + " " + " ".join(tags)

        if not any(kw in combined for kw in SPORTS_KEYWORDS):
            continue

        markets_info = []
        for m in event.get("markets", []):
            prices = m.get("outcomePrices", '["0.5","0.5"]')
            if isinstance(prices, str):
                prices = json.loads(prices)
            yes_price = float(prices[0]) if prices else 0.5
            markets_info.append({
                "slug": m.get("slug", ""),
                "question": m.get("question", ""),
                "question_zh": translate_title(m.get("question", "")),
                "yes_price": yes_price,
                "token_ids": json.loads(m["clobTokenIds"]) if isinstance(m.get("clobTokenIds"), str) else m.get("clobTokenIds", []),
                "volume": float(m.get("volume") or 0),
                "liquidity": float(m.get("liquidity") or 0),
                "score": m.get("score", ""),
                "neg_risk": m.get("negRisk", False),
                "tick_size": m.get("minimumTickSize", "0.01"),
            })

        results.append({
            "event_slug": event.get("slug", ""),
            "title": event.get("title", ""),
            "title_zh": translate_title(event.get("title", "")),
            "end_date_bj": to_beijing_time(event.get("endDate") or event.get("endDateIso")),
            "volume_24h": float(event.get("volume24hr") or 0),
            "markets": markets_info,
        })

    if db:
        scan = ScanResult(scan_type="sports", market_data=json.dumps(results, ensure_ascii=False))
        db.add(scan)
        await db.commit()

    return results
