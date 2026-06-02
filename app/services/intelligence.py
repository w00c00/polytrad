import asyncio
import html
import math
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import httpx

from app.services.polymarket import data_api, to_beijing_time, translate_title
from app.services.scanner import (
    SPORTS_KEYWORDS,
    _combined_text,
    _extract_tags,
    _fetch_gamma_pages,
    _is_tradable_market,
    _market_tick_size,
    _market_token_ids,
    _market_volume_24h,
    _normalise_market,
    _parse_dt,
    _to_float,
    scan_sports_markets,
)


_INTEL_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL_SECONDS = 180
BJT = timezone(timedelta(hours=8))
_WEATHER_PHRASES = (
    "weather",
    "temperature",
    "highest temperature",
    "lowest temperature",
    "record high",
    "record low",
    "precipitation",
    "rainfall",
    "snowfall",
    "hurricane",
    "tropical storm",
    "air quality",
    "heat wave",
    "cold snap",
    "wind speed",
)
_WEATHER_WORDS = {
    "rain",
    "snow",
    "hail",
    "storm",
    "tornado",
    "flood",
    "flooding",
    "drought",
    "wildfire",
    "aqi",
    "celsius",
    "fahrenheit",
}


def _cache_get(key: str):
    item = _INTEL_CACHE.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts <= _CACHE_TTL_SECONDS:
        return value
    return None


def _cache_set(key: str, value):
    _INTEL_CACHE[key] = (time.time(), value)
    return value


def _timestamp_dt(value) -> datetime | None:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts > 10_000_000_000:
        ts = ts / 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _timestamp_bj(value) -> str | None:
    dt = _timestamp_dt(value)
    if not dt:
        return None
    return dt.astimezone(BJT).strftime("%m-%d %H:%M")


def _normalise_text(text: str) -> str:
    text = html.unescape(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_weather_text(text: str) -> bool:
    normalised = _normalise_text(text)
    if not normalised:
        return False
    if any(phrase in normalised for phrase in _WEATHER_PHRASES):
        return True
    tokens = set(normalised.split())
    if tokens & _WEATHER_WORDS:
        return True
    return bool(re.search(r"\b\d+\s?[cf]\b", normalised))


def _market_text(item: dict) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in (
            "title",
            "question",
            "marketTitle",
            "slug",
            "eventSlug",
            "event_slug",
            "outcome",
            "description",
        )
    )


def _is_weather_market(item: dict) -> bool:
    return _is_weather_text(_market_text(item))


_QUERY_STOPWORDS = {
    "will", "the", "this", "that", "market", "yes", "no", "win", "winner", "next",
    "above", "below", "before", "after", "through", "until", "more", "than", "end",
    "2024", "2025", "2026", "2027", "january", "february", "march", "april", "may",
    "june", "july", "august", "september", "october", "november", "december",
}


def _news_query_from_title(title: str) -> str:
    clean = re.sub(r"[?$]", "", html.unescape(title or ""))
    clean = re.sub(r"^\s*Will\s+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bWill\b\s*", "", clean, flags=re.IGNORECASE)
    entities = []
    for match in re.finditer(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\b", clean):
        value = match.group(0).strip()
        if value.lower() in _QUERY_STOPWORDS:
            continue
        if len(value) >= 4:
            entities.append(value)
    if entities:
        return " ".join(entities[:2])

    tokens = [
        t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", clean.lower())
        if t not in _QUERY_STOPWORDS
    ]
    return " ".join(tokens[:5]) or clean[:80]


async def _google_news_rss(query: str, lookback_hours: int, max_records: int = 5) -> list[dict]:
    if not query:
        return []
    days = max(1, math.ceil(lookback_hours / 24))
    params = {
        "q": f"{query} when:{days}d",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    headers = {"User-Agent": "PolyTrad/1.0 (+https://github.com/w00c00/polytrad)"}
    try:
        async with httpx.AsyncClient(timeout=12, headers=headers) as client:
            resp = await client.get("https://news.google.com/rss/search", params=params)
            resp.raise_for_status()
    except Exception:
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return []

    items = []
    for node in root.findall("./channel/item")[:max_records]:
        title = html.unescape(node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        source = node.findtext("source") or ""
        pub_raw = node.findtext("pubDate") or ""
        pub_dt = None
        try:
            pub_dt = parsedate_to_datetime(pub_raw)
            if pub_dt and pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pub_dt = None
        title_main = re.sub(r"\s+-\s+[^-]+$", "", title).strip() or title
        items.append({
            "title": title_main,
            "title_zh": translate_title(title_main),
            "source": html.unescape(source).strip(),
            "url": link,
            "published_at": pub_dt.isoformat() if pub_dt else pub_raw,
            "published_at_bj": pub_dt.astimezone(BJT).strftime("%m-%d %H:%M") if pub_dt else None,
        })
    return items


def _category_match(market: dict, category: str) -> bool:
    category = (category or "all").lower()
    if category == "all":
        return True
    combined = _combined_text(market)
    tags = _extract_tags(market)
    if category == "politics":
        politics = ["politic", "election", "president", "senate", "congress", "trump", "biden"]
        return "politics" in tags or any(k in combined for k in politics)
    if category == "sports":
        return "sports" in tags or any(k in combined for k in SPORTS_KEYWORDS)
    if category == "crypto":
        crypto = ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "xrp"]
        return any(k in combined for k in crypto)
    return category in combined or category in tags


async def scan_news_catalysts(
    category: str = "politics",
    lookback_hours: int = 48,
    max_candidates: int = 24,
) -> list[dict]:
    category = (category or "politics").lower()
    lookback_hours = min(max(int(lookback_hours or 48), 6), 168)
    max_candidates = min(max(int(max_candidates or 24), 5), 80)
    cache_key = f"news:{category}:{lookback_hours}:{max_candidates}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    now = datetime.now(timezone.utc)
    pool_size = min(max_candidates * 3, 240)
    markets = await _fetch_gamma_pages(
        "markets",
        {"order": "volume24hr", "ascending": "false"},
        max_pages=max(3, (pool_size + 99) // 100),
    )

    candidates = []
    seen = set()
    for market in markets:
        slug = market.get("slug", "")
        if not slug or slug in seen:
            continue
        if not _is_tradable_market(market, now):
            continue
        if not _category_match(market, category):
            continue
        question = market.get("question") or market.get("title") or ""
        token_ids = _market_token_ids(market)
        if not question or not token_ids:
            continue
        seen.add(slug)
        info = _normalise_market(market)
        candidates.append({
            "slug": slug,
            "event_slug": market.get("eventSlug") or market.get("groupItemTitle") or slug,
            "condition_id": market.get("conditionId", ""),
            "title": question,
            "title_zh": translate_title(question),
            "category": category,
            "query": _news_query_from_title(question),
            "token_ids": token_ids,
            "token_id": token_ids[0] if token_ids else "",
            "tick_size": _market_tick_size(market),
            "neg_risk": bool(market.get("negRisk", False)),
            "yes_price": info.get("yes_price", 0.0),
            "no_price": info.get("no_price", 0.0),
            "volume_24h": _market_volume_24h(market),
            "liquidity": info.get("liquidity", 0.0),
            "end_date_bj": to_beijing_time(market.get("endDate") or market.get("endDateIso")),
            "end_ts": _parse_dt(market.get("endDate") or market.get("endDateIso")),
        })
        if len(candidates) >= pool_size:
            break

    sem = asyncio.Semaphore(4)

    async def attach_news(item: dict) -> dict:
        async with sem:
            news = await _google_news_rss(item["query"], lookback_hours, max_records=5)
        latest_dt = None
        if news:
            latest_raw = news[0].get("published_at")
            try:
                latest_dt = datetime.fromisoformat(str(latest_raw).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                latest_dt = None
        recency_score = 0.0
        if latest_dt:
            hours_old = max((now - latest_dt.astimezone(timezone.utc)).total_seconds() / 3600, 0.0)
            recency_score = max(0.0, 30.0 - hours_old)
        news_score = min(len(news) * 15.0, 45.0)
        volume_score = min(math.log10(max(item["volume_24h"], 1)) * 8.0, 25.0)
        score = round(news_score + recency_score + volume_score, 1)
        item.update({
            "news_count": len(news),
            "latest_headline": news[0]["title"] if news else "",
            "latest_headline_zh": news[0]["title_zh"] if news else "",
            "latest_news_bj": news[0].get("published_at_bj") if news else None,
            "headlines": news,
            "signal_score": score,
            "signal_level": "高" if score >= 70 else "中" if score >= 45 else "低",
            "note": "新闻热度只代表催化关注度，不代表方向；下单前必须确认规则文本、来源和盘口深度。",
        })
        return item

    results = await asyncio.gather(*(attach_news(c) for c in candidates))
    far_future = now + timedelta(days=3650)
    results.sort(key=lambda x: (
        x.get("end_ts") or far_future,
        -x.get("signal_score", 0),
        -x.get("news_count", 0),
        -x.get("volume_24h", 0),
    ))
    return _cache_set(cache_key, results[:max_candidates])


ESPN_LEAGUES = {
    "nba": ("basketball", "nba", "NBA"),
    "wnba": ("basketball", "wnba", "WNBA"),
    "nfl": ("football", "nfl", "NFL"),
    "mlb": ("baseball", "mlb", "MLB"),
    "nhl": ("hockey", "nhl", "NHL"),
    "eng.1": ("soccer", "eng.1", "英超"),
    "esp.1": ("soccer", "esp.1", "西甲"),
    "ita.1": ("soccer", "ita.1", "意甲"),
    "ger.1": ("soccer", "ger.1", "德甲"),
    "fra.1": ("soccer", "fra.1", "法甲"),
    "uefa.champions": ("soccer", "uefa.champions", "欧冠"),
    "usa.1": ("soccer", "usa.1", "MLS"),
    "jpn.1": ("soccer", "jpn.1", "J1"),
}


async def _espn_scoreboard(league: str, days_back: int = 1, days_ahead: int = 7) -> list[dict]:
    sport, league_slug, label = ESPN_LEAGUES[league]
    now = datetime.now(timezone.utc)
    dates = [(now + timedelta(days=offset)).strftime("%Y%m%d") for offset in range(-days_back, days_ahead + 1)]
    events = []
    headers = {"User-Agent": "PolyTrad/1.0"}
    async with httpx.AsyncClient(timeout=12, headers=headers) as client:
        for date_text in dates:
            try:
                resp = await client.get(
                    f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/scoreboard",
                    params={"dates": date_text, "limit": 80},
                )
                resp.raise_for_status()
            except Exception:
                continue
            for event in (resp.json() or {}).get("events") or []:
                comp = (event.get("competitions") or [{}])[0]
                competitors = comp.get("competitors") or []
                teams = []
                for c in competitors:
                    team = c.get("team") or {}
                    teams.append({
                        "display_name": team.get("displayName") or "",
                        "short_name": team.get("shortDisplayName") or "",
                        "name": team.get("name") or "",
                        "abbreviation": team.get("abbreviation") or "",
                        "score": c.get("score") or "",
                        "home_away": c.get("homeAway") or "",
                    })
                status = (comp.get("status") or event.get("status") or {}).get("type") or {}
                dt_raw = event.get("date") or comp.get("date")
                events.append({
                    "id": event.get("id"),
                    "league": label,
                    "name": event.get("name") or "",
                    "short_name": event.get("shortName") or "",
                    "date": dt_raw,
                    "date_bj": to_beijing_time(dt_raw),
                    "state": status.get("state") or "",
                    "status": status.get("name") or status.get("description") or "",
                    "completed": bool(status.get("completed")),
                    "teams": teams,
                })
    dedup = {}
    for event in events:
        dedup[event.get("id") or f"{event['league']}:{event['name']}:{event['date']}"] = event
    return list(dedup.values())


def _team_aliases(team: dict) -> set[str]:
    aliases = set()
    for key in ("display_name", "short_name", "name", "abbreviation"):
        value = _normalise_text(team.get(key, ""))
        if value and len(value) >= 3:
            aliases.add(value)
    return aliases


def _match_game(title: str, games: list[dict]) -> dict | None:
    text = _normalise_text(title)
    best = None
    best_score = 0
    for game in games:
        teams = game.get("teams") or []
        if len(teams) < 2:
            continue
        score = 0
        matched = []
        for team in teams[:2]:
            aliases = _team_aliases(team)
            if any(alias in text for alias in aliases):
                score += 1
                matched.append(team.get("abbreviation") or team.get("short_name") or team.get("display_name"))
        if score > best_score:
            best_score = score
            best = {**game, "matched_teams": matched}
    return best if best_score >= 2 else None


def _schedule_bucket(title: str) -> tuple[str, bool]:
    text = _normalise_text(title)
    esports = ["counter strike", "cs2", "lol", "league of legends", "dota", "valorant", "esports", "bo3", "bo5"]
    cricket = ["t20", "cricket", "blast", "odi", "test match", "wicket", "six", "qualifier"]
    tennis = ["tennis", "atp", "wta", "roland garros", "wimbledon", "us open", "australian open"]
    combat = ["ufc", "mma", "boxing"]
    racing = ["f1", "formula 1", "nascar"]
    if any(k in text for k in esports):
        return "电竞", False
    if any(k in text for k in cricket):
        return "板球", False
    if any(k in text for k in tennis):
        return "网球", False
    if any(k in text for k in combat):
        return "格斗", False
    if any(k in text for k in racing):
        return "赛车", False
    if "nba" in text:
        return "NBA", True
    if "nfl" in text:
        return "NFL", True
    if "mlb" in text:
        return "MLB", True
    if "nhl" in text:
        return "NHL", True
    top_soccer = [
        "premier league", "la liga", "serie a", "bundesliga", "ligue 1", "champions league", "mls",
        "arsenal", "chelsea", "liverpool", "manchester city", "manchester united", "tottenham",
        "real madrid", "barcelona", "atletico", "bayern", "borussia dortmund", "psg",
        "inter milan", "ac milan", "juventus", "napoli",
    ]
    if any(k in text for k in top_soccer):
        return "足球", True
    if " fc" in f" {text}" or " soccer" in text:
        return "足球小联赛", False
    return "其他体育", False


async def scan_sports_schedule_radar(
    max_candidates: int = 120,
    days_ahead: int = 7,
    include_unsupported: bool = False,
) -> list[dict]:
    max_candidates = min(max(int(max_candidates or 120), 20), 300)
    days_ahead = min(max(int(days_ahead or 7), 1), 30)
    cache_key = f"schedule:{max_candidates}:{days_ahead}:{int(bool(include_unsupported))}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    sports_events = await scan_sports_markets(None)
    league_games_nested = await asyncio.gather(*(_espn_scoreboard(l, days_back=1, days_ahead=days_ahead) for l in ESPN_LEAGUES))
    games = [g for group in league_games_nested for g in group]

    results = []
    for event in sports_events[:max_candidates]:
        title = event.get("title") or ""
        trade_market = next((m for m in event.get("markets", []) if m.get("token_ids") and m.get("accepting_orders", True)), None)
        bucket, espn_supported = _schedule_bucket(title)
        if not espn_supported and not include_unsupported:
            continue
        matched = _match_game(title, games)
        is_game = bool(event.get("is_game") or " vs " in title.lower() or " vs. " in title.lower())
        if matched:
            if matched.get("completed"):
                risk_level = "danger"
                action = "比赛已完结，若 Polymarket 仍显示可交易，只观察不下单"
            elif matched.get("state") == "in":
                risk_level = "warning"
                action = "比赛进行中，盘口跳变快，只适合小额 FOK"
            else:
                risk_level = "success"
                action = "赛程匹配，按开赛时间和市场规则复核"
            teams = " vs ".join(t.get("short_name") or t.get("display_name") or t.get("abbreviation") for t in matched.get("teams", [])[:2])
            game_status = matched.get("status") or matched.get("state") or "-"
        else:
            if not espn_supported:
                risk_level = "info"
                action = f"{bucket}暂不走 ESPN 匹配；按市场到期和官方赛程手动核对"
                game_status = "非ESPN覆盖"
            elif is_game:
                risk_level = "warning"
                action = f"{bucket}未匹配到 ESPN 赛程；可能是小联赛或标题格式不同，下单前核对官方赛程"
                game_status = "ESPN未匹配"
            else:
                risk_level = "info"
                action = "更像冠军/奖项/长期盘，不按单场赛程过滤"
                game_status = "长期盘"
            teams = ""
        row = {
            "event_slug": event.get("event_slug", ""),
            "title": title,
            "title_zh": event.get("title_zh") or translate_title(title),
            "is_game": is_game,
            "league": matched.get("league") if matched else "",
            "league_guess": bucket,
            "espn_supported": espn_supported,
            "game": matched.get("short_name") or matched.get("name") if matched else "",
            "teams": teams,
            "game_time_bj": matched.get("date_bj") if matched else event.get("start_time_bj") or event.get("end_date_bj"),
            "game_status": game_status,
            "completed": bool(matched.get("completed")) if matched else False,
            "risk_level": risk_level,
            "action": action,
            "end_date_bj": event.get("end_date_bj"),
            "start_time_bj": event.get("start_time_bj"),
            "volume_24h": event.get("volume_24h", 0.0),
            "markets": event.get("markets", []),
        }
        if trade_market:
            row.update({
                "market_slug": trade_market.get("slug", ""),
                "slug": trade_market.get("slug", ""),
                "condition_id": trade_market.get("condition_id", ""),
                "question": trade_market.get("question") or title,
                "question_zh": trade_market.get("question_zh") or translate_title(trade_market.get("question") or title),
                "token_ids": trade_market.get("token_ids") or [],
                "token_id": (trade_market.get("token_ids") or [""])[0],
                "tick_size": trade_market.get("tick_size") or "0.01",
                "neg_risk": bool(trade_market.get("neg_risk", False)),
                "yes_price": _to_float(trade_market.get("yes_price"), 0.0),
                "no_price": _to_float(trade_market.get("no_price"), 0.0),
                "can_buy": not row.get("completed"),
                "trade_disabled_reason": "比赛已完结，只观察不下单" if row.get("completed") else "",
            })
        else:
            row.update({
                "token_ids": [],
                "yes_price": 0.0,
                "no_price": 0.0,
                "can_buy": False,
                "trade_disabled_reason": "未找到可交易的子市场 token",
            })
        results.append(row)

    priority = {"danger": 0, "warning": 1, "success": 2, "info": 3}
    results.sort(key=lambda x: (priority.get(x["risk_level"], 9), x.get("game_time_bj") or "99-99 99:99", -x.get("volume_24h", 0)))
    return _cache_set(cache_key, results)


async def _recent_trade_pages(total_limit: int) -> list[dict]:
    page_size = 500
    offsets = list(range(0, total_limit, page_size))
    sem = asyncio.Semaphore(4)

    async def fetch(offset: int) -> list[dict]:
        async with sem:
            try:
                return await data_api.get_recent_trades(limit=min(page_size, total_limit - offset), offset=offset)
            except Exception:
                return []

    pages = await asyncio.gather(*(fetch(offset) for offset in offsets))
    seen = set()
    trades = []
    for page in pages:
        for trade in page:
            key = (
                trade.get("transactionHash"),
                trade.get("asset"),
                trade.get("timestamp"),
                trade.get("proxyWallet"),
                trade.get("side"),
            )
            if key in seen:
                continue
            seen.add(key)
            trades.append(trade)
    return trades


def _closed_position_stats(items: list[dict], market_filter=None) -> dict:
    total = 0.0
    wins = 0
    counted = 0
    filtered = [item for item in items if not market_filter or market_filter(item)]
    for item in filtered[:200]:
        pnl = None
        for key in ("cashPnl", "realizedPnl", "pnl", "profit"):
            if item.get(key) is not None:
                pnl = _to_float(item.get(key), 0.0)
                break
        if pnl is None:
            continue
        counted += 1
        total += pnl
        if pnl > 0:
            wins += 1
    return {
        "closed_count": counted,
        "closed_pnl": round(total, 2),
        "closed_win_rate": round(wins / counted * 100, 1) if counted else None,
    }


async def _wallet_closed_stats(wallet: str, market_filter=None) -> dict:
    try:
        closed = await data_api.get_closed_positions(wallet)
    except Exception:
        return {"closed_count": 0, "closed_pnl": 0.0, "closed_win_rate": None}
    return _closed_position_stats(closed, market_filter)


async def _wallet_closed_stats_bundle(wallet: str, market_filter=None) -> tuple[dict, dict | None]:
    try:
        closed = await data_api.get_closed_positions(wallet)
    except Exception:
        empty = {"closed_count": 0, "closed_pnl": 0.0, "closed_win_rate": None}
        return empty, empty if market_filter else None
    overall = _closed_position_stats(closed)
    filtered = _closed_position_stats(closed, market_filter) if market_filter else None
    return overall, filtered


async def scan_smart_money(
    lookback_hours: int = 24,
    limit: int = 500,
    min_notional: float = 50,
    top_wallets: int = 15,
) -> dict:
    return await _scan_smart_money(
        lookback_hours=lookback_hours,
        limit=limit,
        min_notional=min_notional,
        top_wallets=top_wallets,
        category="all",
    )


async def scan_weather_smart_money(
    lookback_hours: int = 72,
    limit: int = 5000,
    min_notional: float = 5,
    top_wallets: int = 30,
    min_weather_win_rate: float = 55,
    min_weather_closed: int = 2,
    qualified_only: bool = True,
) -> dict:
    return await _scan_smart_money(
        lookback_hours=lookback_hours,
        limit=limit,
        min_notional=min_notional,
        top_wallets=top_wallets,
        category="weather",
        market_filter=_is_weather_market,
        min_filtered_win_rate=min_weather_win_rate,
        min_filtered_closed=min_weather_closed,
        qualified_only=qualified_only,
    )


async def _scan_smart_money(
    *,
    lookback_hours: int = 24,
    limit: int = 500,
    min_notional: float = 50,
    top_wallets: int = 15,
    category: str = "all",
    market_filter=None,
    min_filtered_win_rate: float = 0,
    min_filtered_closed: int = 0,
    qualified_only: bool = False,
) -> dict:
    lookback_hours = min(max(int(lookback_hours or 24), 1), 168)
    limit = min(max(int(limit or 500), 50), 5000)
    min_notional = min(max(float(min_notional or 50), 1.0), 100000.0)
    top_wallets = min(max(int(top_wallets or 15), 3), 80)
    min_filtered_win_rate = min(max(float(min_filtered_win_rate or 0), 0.0), 100.0)
    min_filtered_closed = min(max(int(min_filtered_closed or 0), 0), 200)
    cache_key = (
        f"smart:{category}:{lookback_hours}:{limit}:{min_notional}:{top_wallets}:"
        f"{min_filtered_win_rate}:{min_filtered_closed}:{int(bool(qualified_only))}"
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)
    trades = await _recent_trade_pages(limit)
    groups: dict[str, dict] = {}
    large_trades = []
    for trade in trades:
        wallet = (trade.get("proxyWallet") or trade.get("user") or "").lower()
        if not wallet:
            continue
        dt = _timestamp_dt(trade.get("timestamp"))
        if dt and dt < cutoff:
            continue
        if market_filter and not market_filter(trade):
            continue
        price = _to_float(trade.get("price"), 0.0)
        size = _to_float(trade.get("size"), 0.0)
        notional = abs(price * size)
        if notional < 1:
            continue
        title = trade.get("title") or ""
        slim = {
            "wallet": wallet,
            "category": category,
            "side": trade.get("side") or "",
            "token_id": trade.get("asset") or "",
            "condition_id": trade.get("conditionId") or "",
            "market_slug": trade.get("slug") or "",
            "event_slug": trade.get("eventSlug") or "",
            "title": title,
            "title_zh": translate_title(title),
            "outcome": trade.get("outcome") or "",
            "outcome_index": trade.get("outcomeIndex"),
            "price": round(price, 4),
            "size": round(size, 4),
            "notional": round(notional, 2),
            "timestamp": trade.get("timestamp"),
            "timestamp_bj": _timestamp_bj(trade.get("timestamp")),
            "name": trade.get("name") or "",
            "pseudonym": trade.get("pseudonym") or "",
            "bio": trade.get("bio") or "",
            "profile_image": trade.get("profileImageOptimized") or trade.get("profileImage") or "",
            "transaction_hash": trade.get("transactionHash") or "",
        }
        group = groups.setdefault(wallet, {
            "wallet": wallet,
            "name": slim["name"],
            "pseudonym": slim["pseudonym"],
            "bio": slim["bio"],
            "profile_image": slim["profile_image"],
            "trades_count": 0,
            "buy_notional": 0.0,
            "sell_notional": 0.0,
            "total_notional": 0.0,
            "unique_markets": set(),
            "recent_trades": [],
        })
        group["trades_count"] += 1
        group["total_notional"] += notional
        if str(slim["side"]).upper() == "BUY":
            group["buy_notional"] += notional
        else:
            group["sell_notional"] += notional
        group["unique_markets"].add(slim["market_slug"] or slim["condition_id"])
        group["recent_trades"].append(slim)
        if notional >= min_notional:
            large_trades.append(slim)

    candidates = [g for g in groups.values() if g["total_notional"] >= min_notional]
    candidates.sort(key=lambda x: (x["total_notional"], x["trades_count"]), reverse=True)
    candidate_limit = top_wallets if not market_filter else min(max(top_wallets * 4, top_wallets), 80)
    candidates = candidates[:candidate_limit]

    sem = asyncio.Semaphore(5)

    async def attach_stats(group: dict) -> dict:
        async with sem:
            overall_stats, filtered_stats = await _wallet_closed_stats_bundle(group["wallet"], market_filter)
        stats = filtered_stats or overall_stats
        recent = sorted(group["recent_trades"], key=lambda t: float(t.get("timestamp") or 0), reverse=True)[:8]
        copy_promo = bool(re.search(r"\b(copy|mirror|ref|follow me)\b", f"{group.get('name','')} {group.get('bio','')}", re.IGNORECASE))
        score = group["total_notional"] / 100 + group["trades_count"] * 2
        if stats.get("closed_win_rate") is not None:
            score += max(stats["closed_win_rate"] - 50, 0) / 2
        if stats.get("closed_pnl", 0) > 0:
            score += min(stats["closed_pnl"] / 50, 20)
        qualified = True
        if market_filter:
            qualified = (
                stats.get("closed_win_rate") is not None
                and stats.get("closed_count", 0) >= min_filtered_closed
                and stats.get("closed_win_rate", 0) >= min_filtered_win_rate
            )
        group.update({
            "category": category,
            "total_notional": round(group["total_notional"], 2),
            "buy_notional": round(group["buy_notional"], 2),
            "sell_notional": round(group["sell_notional"], 2),
            "unique_markets": len(group["unique_markets"]),
            "recent_trades": recent,
            "latest_trade_bj": recent[0].get("timestamp_bj") if recent else None,
            "last_buy_trade": next((t for t in recent if str(t.get("side")).upper() == "BUY" and t.get("token_id")), None),
            "copy_trade_promo": copy_promo,
            "smart_score": round(score, 1),
            "risk_note": "疑似跟单/推广账号，先观察其历史胜率和仓位变化" if copy_promo else "聪明钱只代表资金流，不代表必赢；注意可能是对冲、做市或信息滞后。",
            "all_closed_count": overall_stats.get("closed_count", 0),
            "all_closed_pnl": overall_stats.get("closed_pnl", 0.0),
            "all_closed_win_rate": overall_stats.get("closed_win_rate"),
            **stats,
        })
        if category == "weather":
            group.update({
                "weather_closed_count": stats.get("closed_count", 0),
                "weather_closed_pnl": stats.get("closed_pnl", 0.0),
                "weather_closed_win_rate": stats.get("closed_win_rate"),
                "weather_qualified": qualified,
                "weather_threshold_note": (
                    f"天气历史 {stats.get('closed_count', 0)} 笔 / 胜率 "
                    f"{stats.get('closed_win_rate') if stats.get('closed_win_rate') is not None else '-'}%，"
                    f"门槛 {min_filtered_closed} 笔 / {min_filtered_win_rate:.1f}%"
                ),
                "risk_note": (
                    "天气高胜率只代表历史已平仓表现；温度盘临近结算、数据源和盘口跳变都可能造成跟单失效。"
                    if qualified
                    else "未达到天气高胜率门槛，只建议观察，不建议一键跟单。"
                ),
            })
        return group

    wallets = await asyncio.gather(*(attach_stats(g) for g in candidates))
    if market_filter and qualified_only:
        wallets = [w for w in wallets if w.get("weather_qualified")]
    wallets.sort(key=lambda x: x.get("smart_score", 0), reverse=True)
    large_trades.sort(key=lambda x: (x.get("notional", 0), float(x.get("timestamp") or 0)), reverse=True)
    result = {
        "generated_at_bj": datetime.now(BJT).strftime("%m-%d %H:%M"),
        "category": category,
        "lookback_hours": lookback_hours,
        "sampled_trades": len(trades),
        "matched_trades": sum(w.get("trades_count", 0) for w in wallets),
        "qualified_only": qualified_only,
        "min_filtered_win_rate": min_filtered_win_rate,
        "min_filtered_closed": min_filtered_closed,
        "wallets": wallets,
        "large_trades": large_trades[:50],
        "note": (
            "天气跟单只扫描温度、降雨、风暴等天气类公开成交，并优先按天气已平仓胜率排序；"
            "天气盘常临近结算，跟买前必须核对官方数据源、结算时间和盘口深度。"
            if category == "weather"
            else "该面板基于 Polymarket 公开成交流和公开已平仓数据估算，只能用于观察，不能替代独立判断。"
        ),
    }
    return _cache_set(cache_key, result)
