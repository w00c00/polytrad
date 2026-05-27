import httpx
from datetime import datetime, timezone, timedelta
from typing import Any
from app.config import get_settings

settings = get_settings()

BJT = timezone(timedelta(hours=8))


def to_beijing_time(iso_str: str | None) -> str | None:
    """将 ISO 时间字符串转为北京时间显示"""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_bj = dt.astimezone(BJT)
        return dt_bj.strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str


# 体育/政治标题常见翻译
_TITLE_MAP = {
    "Will": "", "win": "赢", "beat": "击败", "vs": "vs", "finals": "总决赛",
    "championship": "锦标赛", "election": "选举", "president": "总统",
    "governor": "州长", "senate": "参议院", "congress": "国会",
    "democrat": "民主党", "republican": "共和党", "Super Bowl": "超级碗",
    "World Series": "世界大赛", "NBA": "NBA", "NFL": "NFL", "MLB": "MLB",
    "NHL": "NHL", "UFC": "UFC", "F1": "F1", "World Cup": "世界杯",
    "Champions League": "欧冠", "Premier League": "英超",
    "Champion": "冠军", "Top 4": "前四", "Relegate": "降级",
    "Bitcoin": "比特币", "Ethereum": "以太坊", "above": "高于", "below": "低于",
    "by": "在", "before": "之前", "end of": "结束前",
}


def translate_title(title: str) -> str:
    """简单翻译标题中的常见词"""
    result = title
    for en, zh in _TITLE_MAP.items():
        result = result.replace(en, zh)
    return result


class GammaAPI:
    """Polymarket Gamma API - 市场发现与元数据 (无需认证)"""

    def __init__(self):
        self.base = settings.polymarket_gamma_host
        self.client = httpx.AsyncClient(timeout=30)

    async def get_events(self, **params) -> list[dict]:
        params.setdefault("active", "true")
        params.setdefault("closed", "false")
        params.setdefault("limit", 50)
        resp = await self.client.get(f"{self.base}/events", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_event(self, slug: str) -> dict | None:
        resp = await self.client.get(f"{self.base}/events", params={"slug": slug})
        resp.raise_for_status()
        events = resp.json()
        return events[0] if events else None

    async def get_markets(self, **params) -> list[dict]:
        params.setdefault("active", "true")
        params.setdefault("closed", "false")
        params.setdefault("limit", 50)
        resp = await self.client.get(f"{self.base}/markets", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_market_by_slug(self, slug: str) -> dict | None:
        resp = await self.client.get(f"{self.base}/markets", params={"slug": slug})
        resp.raise_for_status()
        markets = resp.json()
        return markets[0] if markets else None

    async def search(self, query: str) -> list[dict]:
        """通过 events + markets 过滤实现搜索（/search 端点已下线）"""
        keywords = query.lower().split()
        results = []
        for ep in ["/events", "/markets"]:
            resp = await self.client.get(f"{self.base}{ep}", params={"active": "true", "closed": "false", "limit": 100})
            if resp.status_code == 200:
                for item in resp.json():
                    text = (item.get("title", "") + item.get("question", "") + item.get("slug", "")).lower()
                    if any(kw in text for kw in keywords):
                        results.append(item)
        return results

    async def get_tags(self) -> list[dict]:
        resp = await self.client.get(f"{self.base}/tags")
        resp.raise_for_status()
        return resp.json()

    async def get_series(self, slug: str) -> dict | None:
        """获取 series 信息及其 events（用于 BTC 短周期等循环市场）"""
        resp = await self.client.get(f"{self.base}/series", params={"slug": slug})
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data[0] if data else None

    async def get_prices_history(self, market_id: str, interval: str = "1d") -> list:
        resp = await self.client.get(
            f"{self.base}/prices-history",
            params={"market": market_id, "interval": interval},
        )
        resp.raise_for_status()
        return resp.json()


class DataAPI:
    """Polymarket Data API - 持仓、交易历史 (无需认证)"""

    def __init__(self):
        self.base = settings.polymarket_data_host
        self.client = httpx.AsyncClient(timeout=30)

    async def get_positions(self, wallet_address: str) -> list[dict]:
        resp = await self.client.get(f"{self.base}/positions", params={"user": wallet_address})
        resp.raise_for_status()
        return resp.json()

    async def get_closed_positions(self, wallet_address: str) -> list[dict]:
        resp = await self.client.get(f"{self.base}/closed-positions", params={"user": wallet_address})
        resp.raise_for_status()
        return resp.json()

    async def get_value(self, wallet_address: str) -> dict:
        resp = await self.client.get(f"{self.base}/value", params={"user": wallet_address})
        resp.raise_for_status()
        return resp.json()

    async def get_trades(self, wallet_address: str, limit: int = 100) -> list[dict]:
        resp = await self.client.get(f"{self.base}/trades", params={"user": wallet_address, "limit": limit})
        resp.raise_for_status()
        return resp.json()


class CLOBAPI:
    """Polymarket CLOB API - 订单簿、价格 (公开读取无需认证)"""

    def __init__(self):
        self.base = settings.polymarket_clob_host
        self.client = httpx.AsyncClient(timeout=30)

    async def get_midpoint(self, token_id: str) -> float:
        resp = await self.client.get(f"{self.base}/midpoint", params={"token_id": token_id})
        resp.raise_for_status()
        return float(resp.json().get("mid", 0))

    async def get_price(self, token_id: str, side: str = "BUY") -> float:
        resp = await self.client.get(f"{self.base}/price", params={"token_id": token_id, "side": side})
        resp.raise_for_status()
        return float(resp.json().get("price", 0))

    async def get_orderbook(self, token_id: str) -> dict:
        resp = await self.client.get(f"{self.base}/book", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    async def get_spread(self, token_id: str) -> dict:
        resp = await self.client.get(f"{self.base}/spread", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    async def get_tick_size(self, token_id: str) -> str:
        resp = await self.client.get(f"{self.base}/tick-size", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json().get("tick_size", "0.01")

    async def get_last_trade(self, token_id: str) -> dict:
        resp = await self.client.get(f"{self.base}/last-trade-price", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()


gamma_api = GammaAPI()
data_api = DataAPI()
clob_api = CLOBAPI()
