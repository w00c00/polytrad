import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.polymarket import gamma_api, clob_api
from app.models import ScanResult

logger = logging.getLogger(__name__)

# Polymarket 政治相关 tag 的常见 slug 片段
POLITICAL_KEYWORDS = ["politic", "election", "president", "congress", "senate", "governor", "democrat", "republican", "trump", "biden"]
SPORTS_KEYWORDS = ["sport", "nfl", "nba", "mlb", "nhl", "soccer", "football", "basketball", "tennis", "ufc", "f1", "world cup"]


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
            "end_date": end_str,
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
                "token_ids": json.loads(m["clobTokenIds"]) if isinstance(m.get("clobTokenIds"), str) else m.get("clobTokenIds", []),
                "volume": float(m.get("volume") or 0),
                "neg_risk": m.get("negRisk", False),
                "tick_size": m.get("minimumTickSize", "0.01"),
            })

        results.append({
            "event_slug": event.get("slug", ""),
            "title": event.get("title", ""),
            "start_date": event.get("startDate") or event.get("startDateIso"),
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
            "volume_24h": float(event.get("volume24hr") or 0),
            "markets": markets_info,
        })

    return results
