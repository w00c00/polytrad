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
SPORTS_KEYWORDS = ["sport", "nfl", "nba", "mlb", "nhl", "soccer", "football", "basketball", "tennis", "ufc", "f1", "world cup"]

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
            if event.get("closed") or not event.get("active"):
                return None
            # 过滤已过期
            end_str = event.get("endDate") or ""
            if end_str:
                try:
                    ed = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                    if ed.tzinfo is None:
                        ed = ed.replace(tzinfo=timezone.utc)
                    if ed < now:
                        return None
                except (ValueError, TypeError):
                    pass
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
                if event.get("closed") or not event.get("active"):
                    continue
                slug = event.get("slug", "")
                full_event = await gamma_api.get_event(slug)
                if not full_event:
                    continue
                if full_event.get("closed") or not full_event.get("active"):
                    continue
                # 过滤已过期
                end_str = full_event.get("endDate") or ""
                if end_str:
                    try:
                        ed = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                        if ed.tzinfo is None:
                            ed = ed.replace(tzinfo=timezone.utc)
                        if ed < now:
                            continue
                    except (ValueError, TypeError):
                        pass
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


async def scan_hot_markets(db: AsyncSession, hours_until_expiry: int = 24, min_volume: float = 5000) -> list[dict]:
    """扫描即将到期的热门市场（从 markets 端点分页获取）"""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_until_expiry)
    seen_slugs = set()
    results = []

    for offset in range(0, 2000, 100):
        try:
            resp = await gamma_api.client.get(f"{gamma_api.base}/markets", params={
                "active": "true", "closed": "false", "limit": 100,
                "order": "volume", "ascending": "false", "offset": str(offset),
            })
            resp.raise_for_status()
            markets = resp.json()
            if not markets:
                break
            for m in markets:
                end = m.get("endDate") or m.get("endDateIso") or ""
                if not end:
                    continue
                try:
                    ed = datetime.fromisoformat(end.replace("Z", "+00:00"))
                    if ed.tzinfo is None:
                        ed = ed.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    continue
                if ed < now or ed > cutoff:
                    continue
                vol = float(m.get("volume") or 0)
                if vol < min_volume:
                    continue
                slug = m.get("slug", "")
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                q = m.get("question", "")
                if any(kw in q.lower() for kw in CHINA_KEYWORDS):
                    continue
                prices = m.get("outcomePrices", '["0.5","0.5"]')
                if isinstance(prices, str):
                    prices = json.loads(prices)
                yes_price = float(prices[0]) if prices else 0.5
                token_ids = m.get("clobTokenIds", [])
                if isinstance(token_ids, str):
                    token_ids = json.loads(token_ids)
                results.append({
                    "event_slug": slug,
                    "title": q,
                    "title_zh": translate_title(q),
                    "end_date_bj": to_beijing_time(end),
                    "volume_24h": vol,
                    "markets": [{
                        "slug": slug,
                        "question": q,
                        "question_zh": translate_title(q),
                        "yes_price": yes_price,
                        "no_price": 1 - yes_price,
                        "token_ids": token_ids,
                        "volume": vol,
                        "liquidity": float(m.get("liquidity") or 0),
                        "neg_risk": m.get("negRisk", False),
                        "tick_size": m.get("minimumTickSize", "0.01"),
                    }],
                })
        except Exception as e:
            logger.warning(f"扫描尾盘 markets offset={offset} 失败: {e}")
            break

    results.sort(key=lambda x: x.get("end_date_bj", ""))

    if db:
        scan = ScanResult(scan_type="hot", market_data=json.dumps(results, ensure_ascii=False))
        db.add(scan)
        await db.commit()

    return results


async def scan_new_political_markets(db: AsyncSession) -> list[dict]:
    """扫描新创建的政治类市场（只返回未过期的）"""
    now = datetime.now(timezone.utc)
    events = await gamma_api.get_events(order="start_date", ascending=False, limit=100)

    results = []
    for event in events:
        # 过滤已过期事件
        end_str = event.get("endDate") or event.get("endDateIso") or ""
        if end_str:
            try:
                ed = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if ed.tzinfo is None:
                    ed = ed.replace(tzinfo=timezone.utc)
                if ed < now:
                    continue
            except (ValueError, TypeError):
                pass

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
            # 过滤单个 market 已过期
            m_end = m.get("endDate") or m.get("endDateIso") or ""
            if m_end:
                try:
                    med = datetime.fromisoformat(m_end.replace("Z", "+00:00"))
                    if med.tzinfo is None:
                        med = med.replace(tzinfo=timezone.utc)
                    if med < now:
                        continue
                except (ValueError, TypeError):
                    pass

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

        if not markets_info:
            continue

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
    """扫描事件套利机会 - P2 #14: 分页取 500 个 events，避免漏掉偏差大的机会"""
    now = datetime.now(timezone.utc)
    events = []
    for offset in range(0, 500, 100):
        try:
            resp = await gamma_api.client.get(f"{gamma_api.base}/events", params={
                "active": "true", "closed": "false",
                "limit": 100, "offset": offset,
            })
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            events.extend(batch)
        except Exception:
            break

    results = []
    for event in events:
        # 过滤已过期
        end_str = event.get("endDate") or event.get("endDateIso") or ""
        if end_str:
            try:
                ed = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if ed.tzinfo is None:
                    ed = ed.replace(tzinfo=timezone.utc)
                if ed < now:
                    continue
            except (ValueError, TypeError):
                pass

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
    """扫描体育赛事市场（含单场比赛）- P3 #18: 带 2 分钟缓存"""
    return await _cached_scan("sports", _scan_sports_markets_inner, db)


async def _scan_sports_markets_inner(db: AsyncSession) -> list[dict]:
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=48)  # 48 小时内到期的比赛

    # 1. 扫描 events（冠军/季后赛等长期市场）
    events = await gamma_api.get_events(order="volume_24hr", ascending=False, limit=100)

    results = []
    seen_slugs = set()

    for event in events:
        # 过滤已过期
        end_str = event.get("endDate") or event.get("endDateIso") or ""
        if end_str:
            try:
                ed = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if ed.tzinfo is None:
                    ed = ed.replace(tzinfo=timezone.utc)
                if ed < now:
                    continue
            except (ValueError, TypeError):
                pass

        title = (event.get("title") or "").lower()
        # P1 #5: Polymarket tags 是字符串列表，不是 dict，去掉错误的类型过滤
        tags = [str(t).lower() for t in (event.get("tags") or [])]
        combined = title + " " + " ".join(tags)

        if not any(kw in combined for kw in SPORTS_KEYWORDS):
            continue

        markets_info = []
        for m in event.get("markets", []):
            # 过滤单个 market 已过期
            m_end = m.get("endDate") or m.get("endDateIso") or ""
            if m_end:
                try:
                    med = datetime.fromisoformat(m_end.replace("Z", "+00:00"))
                    if med.tzinfo is None:
                        med = med.replace(tzinfo=timezone.utc)
                    if med < now:
                        continue
                except (ValueError, TypeError):
                    pass

            prices = m.get("outcomePrices", '["0.5","0.5"]')
            if isinstance(prices, str):
                prices = json.loads(prices)
            yes_price = float(prices[0]) if prices else 0.5
            slug = m.get("slug", "")
            seen_slugs.add(slug)
            markets_info.append({
                "slug": slug,
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

        if not markets_info:
            continue

        results.append({
            "event_slug": event.get("slug", ""),
            "title": event.get("title", ""),
            "title_zh": translate_title(event.get("title", "")),
            "end_date_bj": to_beijing_time(end_str),
            "volume_24h": float(event.get("volume24hr") or 0),
            "markets": markets_info,
        })

    # 2. 用 offset 分页扫描单场比赛 markets（72h 内到期）
    GAME_KW = ["vs", "matchup", "beat", "points", "spread", "handicap",
                "o/u", "over/under", "completed match", "map winner",
                "game handicap", "set 1", "first set"]
    GAME_SPORT_KW = SPORTS_KEYWORDS + [
        "esports", "lol", "dota", "cs2", "counter-strike", "valorant",
        "overwatch", "rocket league", "mobile legends", "mlbb",
        "atp", "wta", "roland garros", "legends cricket",
    ]

    async def fetch_game_markets():
        all_games = []
        for offset in range(0, 2000, 100):  # 最多 20 页，2000 个 markets
            try:
                params = {
                    "active": "true", "closed": "false", "limit": 100,
                    "order": "volume", "ascending": "false", "offset": str(offset),
                }
                resp = await gamma_api.client.get(f"{gamma_api.base}/markets", params=params)
                resp.raise_for_status()
                markets = resp.json()
                if not markets:
                    break
                for m in markets:
                    q = (m.get("question") or "").lower()
                    slug = m.get("slug", "")
                    if slug in seen_slugs:
                        continue
                    is_game = any(kw in q for kw in GAME_KW)
                    is_sport = any(kw in q for kw in GAME_SPORT_KW)
                    if not (is_game and is_sport):
                        continue
                    # 72h 内到期，且未过期
                    end = m.get("endDate") or m.get("endDateIso") or ""
                    if end:
                        try:
                            ed = datetime.fromisoformat(end.replace("Z", "+00:00"))
                            if ed.tzinfo is None:
                                ed = ed.replace(tzinfo=timezone.utc)
                            if ed < now or ed > soon:
                                continue
                        except (ValueError, TypeError):
                            continue
                    prices = m.get("outcomePrices", '["0.5","0.5"]')
                    if isinstance(prices, str):
                        prices = json.loads(prices)
                    yes_price = float(prices[0]) if prices else 0.5
                    token_ids = m.get("clobTokenIds", [])
                    if isinstance(token_ids, str):
                        token_ids = json.loads(token_ids)
                    all_games.append({
                        "slug": slug,
                        "question": m.get("question", ""),
                        "question_zh": translate_title(m.get("question", "")),
                        "yes_price": yes_price,
                        "token_ids": token_ids,
                        "volume": float(m.get("volume") or 0),
                        "liquidity": float(m.get("liquidity") or 0),
                        "neg_risk": m.get("negRisk", False),
                        "tick_size": m.get("minimumTickSize", "0.01"),
                    })
                    seen_slugs.add(slug)
            except Exception as e:
                logger.warning(f"扫描体育市场 offset={offset} 失败: {e}")
                break
        return all_games

    game_markets = await fetch_game_markets()

    # 将单场比赛按 event_slug 分组（用 slug 前缀推断）
    if game_markets:
        # 每个比赛市场作为独立 event
        for gm in game_markets:
            results.append({
                "event_slug": gm["slug"],
                "title": gm["question"],
                "title_zh": gm["question_zh"],
                "end_date_bj": "",  # 单场比赛不需要显示结束时间
                "volume_24h": gm["volume"],
                "markets": [gm],
                "is_game": True,
            })

    if db:
        scan = ScanResult(scan_type="sports", market_data=json.dumps(results, ensure_ascii=False))
        db.add(scan)
        await db.commit()

    return results
