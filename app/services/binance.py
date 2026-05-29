"""Binance API 服务 - 获取加密货币实时数据和技术指标"""
import httpx
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class BinanceAPI:
    """Binance 公开 API - K线、价格、深度数据"""

    BASE_URL = "https://api.binance.com/api/v3"

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30)

    async def get_price(self, symbol: str) -> dict:
        """获取最新价格"""
        resp = await self.client.get(f"{self.BASE_URL}/ticker/price", params={"symbol": symbol})
        resp.raise_for_status()
        return resp.json()

    async def get_24h_stats(self, symbol: str) -> dict:
        """获取24小时统计数据"""
        resp = await self.client.get(f"{self.BASE_URL}/ticker/24hr", params={"symbol": symbol})
        resp.raise_for_status()
        return resp.json()

    async def get_orderbook(self, symbol: str, limit: int = 20) -> dict:
        """获取深度数据"""
        resp = await self.client.get(f"{self.BASE_URL}/depth", params={"symbol": symbol, "limit": limit})
        resp.raise_for_status()
        return resp.json()

    async def get_klines(self, symbol: str, interval: str = "15m", limit: int = 100) -> list:
        """
        获取K线数据
        interval: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d
        """
        resp = await self.client.get(
            f"{self.BASE_URL}/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_recent_trades(self, symbol: str, limit: int = 50) -> list:
        """获取最近成交记录"""
        resp = await self.client.get(f"{self.BASE_URL}/trades", params={"symbol": symbol, "limit": limit})
        resp.raise_for_status()
        return resp.json()

    async def get_market_indicator(self, symbol: str) -> dict:
        """获取 BTC/ETH 的技术指标数据"""
        # 获取15分钟K线（短期预测）
        klines_15m = await self.get_klines(symbol, interval="15m", limit=50)
        # 获取1小时K线（中期趋势）
        klines_1h = await self.get_klines(symbol, interval="1h", limit=50)
        # 获取24小时统计
        stats_24h = await self.get_24h_stats(symbol)
        # 获取深度
        orderbook = await self.get_orderbook(symbol, limit=20)

        # 解析价格数据
        closes_15m = [float(k[4]) for k in klines_15m]
        closes_1h = [float(k[4]) for k in klines_1h]
        current_price = closes_15m[-1]

        # 计算技术指标
        indicators = {
            "current_price": current_price,
            "price_change_24h": float(stats_24h.get("priceChangePercent", 0)),
            "volume_24h": float(stats_24h.get("volume", 0)),
            "quote_volume_24h": float(stats_24h.get("quoteVolume", 0)),
            "trades_count_24h": int(stats_24h.get("count", 0)),
            "high_24h": float(stats_24h.get("highPrice", 0)),
            "low_24h": float(stats_24h.get("lowPrice", 0)),
        }

        # RSI (14周期, 15分钟)
        rsi_15m = self._calculate_rsi(closes_15m, period=14)
        indicators["rsi_15m"] = rsi_15m

        # RSI (14周期, 1小时)
        rsi_1h = self._calculate_rsi(closes_1h, period=14)
        indicators["rsi_1h"] = rsi_1h

        # EMA (9, 21, 50) - 15分钟
        ema_9_15m = self._calculate_ema(closes_15m, period=9)
        ema_21_15m = self._calculate_ema(closes_15m, period=21)
        ema_50_15m = self._calculate_ema(closes_15m, period=50)
        indicators["ema_9_15m"] = ema_9_15m
        indicators["ema_21_15m"] = ema_21_15m
        indicators["ema_50_15m"] = ema_50_15m

        # EMA (9, 21, 50) - 1小时
        ema_9_1h = self._calculate_ema(closes_1h, period=9)
        ema_21_1h = self._calculate_ema(closes_1h, period=21)
        ema_50_1h = self._calculate_ema(closes_1h, period=50)
        indicators["ema_9_1h"] = ema_9_1h
        indicators["ema_21_1h"] = ema_21_1h
        indicators["ema_50_1h"] = ema_50_1h

        # MACD (15分钟)
        macd_15m = self._calculate_macd(closes_15m)
        indicators["macd_15m"] = macd_15m

        # MACD (1小时)
        macd_1h = self._calculate_macd(closes_1h)
        indicators["macd_1h"] = macd_1h

        # 布林带 (15分钟, 20周期, 2标准差)
        bb_15m = self._calculate_bollinger_bands(closes_15m, period=20, std_dev=2)
        indicators["bollinger_15m"] = bb_15m

        # 布林带 (1小时, 20周期, 2标准差)
        bb_1h = self._calculate_bollinger_bands(closes_1h, period=20, std_dev=2)
        indicators["bollinger_1h"] = bb_1h

        # 成交量趋势 (15分钟)
        volumes_15m = [float(k[5]) for k in klines_15m]
        avg_volume_15m = sum(volumes_15m[-20:]) / 20 if len(volumes_15m) >= 20 else sum(volumes_15m) / len(volumes_15m)
        current_volume_15m = volumes_15m[-1]
        indicators["volume_ratio_15m"] = current_volume_15m / avg_volume_15m if avg_volume_15m > 0 else 1.0

        # 价格变动百分比 (最近5根、10根、20根15分钟K线)
        if len(closes_15m) >= 20:
            change_5 = (current_price - closes_15m[-6]) / closes_15m[-6] * 100
            change_10 = (current_price - closes_15m[-11]) / closes_15m[-11] * 100
            change_20 = (current_price - closes_15m[-21]) / closes_15m[-21] * 100
            indicators["price_change_5_15m"] = change_5
            indicators["price_change_10_15m"] = change_10
            indicators["price_change_20_15m"] = change_20

        # 支撑阻力位 (简化的最近高低点)
        highs_15m = [float(k[2]) for k in klines_15m[-20:]]
        lows_15m = [float(k[3]) for k in klines_15m[-20:]]
        indicators["recent_high"] = max(highs_15m)
        indicators["recent_low"] = min(lows_15m)

        return indicators

    def _calculate_rsi(self, prices: list, period: int = 14) -> Optional[float]:
        """计算 RSI (Relative Strength Index)"""
        if len(prices) < period + 1:
            return None

        gains = []
        losses = []

        for i in range(1, period + 1):
            change = prices[-period + i] - prices[-period + i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)

    def _calculate_ema(self, prices: list, period: int) -> Optional[float]:
        """计算 EMA (Exponential Moving Average)"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = sum(prices[(-period * 2):-period]) / period

        for price in prices[-period:]:
            ema = (price - ema) * multiplier + ema

        return round(ema, 2)

    def _calculate_macd(self, prices: list) -> Optional[dict]:
        """计算 MACD (12, 26, 9)"""
        if len(prices) < 35:
            return None

        # EMA 12
        ema_12 = self._calculate_ema(prices, 12)
        # EMA 26
        ema_26 = self._calculate_ema(prices, 26)

        if ema_12 is None or ema_26 is None:
            return None

        macd_line = ema_12 - ema_26

        # 计算信号线 (EMA 9 of MACD)
        # 简化：使用最近的9个MACD值
        macd_values = []
        for i in range(len(prices) - 8, len(prices) + 1):
            if i >= len(prices):
                break
            ema_12_i = self._calculate_ema(prices[:i], 12)
            ema_26_i = self._calculate_ema(prices[:i], 26)
            if ema_12_i is not None and ema_26_i is not None:
                macd_values.append(ema_12_i - ema_26_i)

        signal_line = sum(macd_values[-9:]) / len(macd_values[-9:]) if len(macd_values) >= 9 else macd_line

        histogram = macd_line - signal_line

        return {
            "macd_line": round(macd_line, 2),
            "signal_line": round(signal_line, 2),
            "histogram": round(histogram, 2)
        }

    def _calculate_bollinger_bands(self, prices: list, period: int = 20, std_dev: int = 2) -> Optional[dict]:
        """计算布林带"""
        if len(prices) < period:
            return None

        recent_prices = prices[-period:]
        sma = sum(recent_prices) / period

        # 计算标准差
        variance = sum((p - sma) ** 2 for p in recent_prices) / period
        std = variance ** 0.5

        upper_band = sma + (std_dev * std)
        lower_band = sma - (std_dev * std)

        return {
            "upper": round(upper_band, 2),
            "middle": round(sma, 2),
            "lower": round(lower_band, 2),
            "bandwidth": round((upper_band - lower_band) / sma * 100, 2)
        }

    async def close(self):
        await self.client.aclose()


# 全局实例
binance_api = BinanceAPI()
