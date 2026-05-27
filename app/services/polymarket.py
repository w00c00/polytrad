import httpx
from typing import Any
from app.config import get_settings

settings = get_settings()


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
        resp = await self.client.get(f"{self.base}/search", params={"query": query})
        resp.raise_for_status()
        return resp.json()

    async def get_tags(self) -> list[dict]:
        resp = await self.client.get(f"{self.base}/tags")
        resp.raise_for_status()
        return resp.json()

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
