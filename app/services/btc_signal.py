"""BTC 短周期本地技术分析信号 — 与上个项目逻辑一致"""
import math
import logging
import httpx
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

BJT = timezone(timedelta(hours=8))

BINANCE_KLINES = [
    "https://api.binance.com/api/v3/klines",
    "https://data-api.binance.vision/api/v3/klines",
]


async def fetch_klines(symbol: str = "BTCUSDT", interval: str = "1m", limit: int = 100) -> list:
    """从 Binance 获取 K 线数据"""
    params = {"symbol": symbol, "interval": interval, "limit": str(limit)}
    async with httpx.AsyncClient(timeout=12) as client:
        for url in BINANCE_KLINES:
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue
    raise RuntimeError("Binance K线接口不可用")


def calc_ema(data: list[float], period: int) -> float:
    if not data:
        return 0.0
    k = 2.0 / (period + 1)
    ema = data[0]
    for v in data[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(-period, 0):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss < 1e-10:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def window_return(closes: list[float], steps: int) -> float:
    steps = max(1, min(steps, len(closes) - 1))
    return closes[-1] / closes[-steps - 1] - 1.0


async def analyze_btc_signal(horizon_minutes: int = 15) -> dict:
    """
    本地技术分析 BTC 短周期概率。
    与上个项目 fetch_btc_signal 逻辑一致。
    """
    lookback = max(80, min(1000, horizon_minutes * 4 + 40))
    klines = await fetch_klines("BTCUSDT", "1m", lookback)

    closes = [float(row[4]) for row in klines]
    if len(closes) < 30:
        raise RuntimeError("K线数据不足")

    current = closes[-1]
    fast_window = max(3, min(60, horizon_minutes // 3))
    mid_window = max(5, min(240, horizon_minutes))
    slow_window = max(10, min(720, horizon_minutes * 2))

    ret_fast = window_return(closes, fast_window)
    ret_mid = window_return(closes, mid_window)
    ret_slow = window_return(closes, slow_window)

    ema_fast_period = max(5, min(60, max(5, horizon_minutes // 2)))
    ema_slow_period = max(12, min(240, max(12, horizon_minutes * 2)))
    ema_fast = calc_ema(closes[-max(ema_slow_period * 4, 30):], ema_fast_period)
    ema_slow = calc_ema(closes[-max(ema_slow_period * 4, 30):], ema_slow_period)

    rsi_period = max(7, min(28, horizon_minutes if horizon_minutes <= 60 else 14))
    rsi = calc_rsi(closes, rsi_period)

    returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    vol_window = max(15, min(240, horizon_minutes * 2))
    recent_returns = returns[-vol_window:]
    mean_return = sum(recent_returns) / len(recent_returns)
    vol = max(0.0001, (sum((x - mean_return) ** 2 for x in recent_returns) / len(recent_returns)) ** 0.5)

    momentum = 0.50 * ret_fast + 0.35 * ret_mid + 0.15 * ret_slow
    trend = (ema_fast / ema_slow - 1.0) if ema_slow else 0.0
    rsi_bias = (rsi - 50.0) / 10000.0
    z = max(-2.0, min(2.0, (momentum + trend + rsi_bias) / (vol * 3.0)))
    raw_prob_up = 1.0 / (1.0 + math.exp(-z))
    prob_up = 0.5 + (raw_prob_up - 0.5) * 0.6

    confidence_value = abs(prob_up - 0.5) * 2.0
    confidence = "低"
    if confidence_value >= 0.55:
        confidence = "高"
    elif confidence_value >= 0.30:
        confidence = "中"

    now_bj = datetime.now(BJT).strftime("%H:%M:%S")

    return {
        "fetched_at": now_bj,
        "price": round(current, 2),
        "horizon_minutes": horizon_minutes,
        "prob_up": round(prob_up, 4),
        "prob_down": round(1.0 - prob_up, 4),
        "confidence": confidence,
        "confidence_value": round(confidence_value, 4),
        "ret_fast": round(ret_fast, 5),
        "ret_mid": round(ret_mid, 5),
        "ret_slow": round(ret_slow, 5),
        "fast_window": fast_window,
        "mid_window": mid_window,
        "slow_window": slow_window,
        "ema_fast": round(ema_fast, 2),
        "ema_slow": round(ema_slow, 2),
        "rsi": round(rsi, 2),
        "vol": round(vol, 6),
    }


def build_llm_prompt(signal: dict, market_info: dict | None = None) -> str:
    """构建给 LLM 的分析 prompt，与上个项目 compact_signal + fetch_minimax_prediction 一致"""
    compact = {
        "period": market_info.get("period", "") if market_info else "",
        "horizon_min": signal["horizon_minutes"],
        "price": signal["price"],
        "p_up": signal["prob_up"],
        "p_down": signal["prob_down"],
        "confidence": signal["confidence"],
        "r_fast": signal["ret_fast"],
        "r_mid": signal["ret_mid"],
        "r_slow": signal["ret_slow"],
        "rsi": signal["rsi"],
        "vol": signal["vol"],
    }

    market_block = {}
    if market_info:
        market_block = {
            "question": market_info.get("question", ""),
            "period": market_info.get("period", ""),
            "end_time": market_info.get("end_time", ""),
            "up_price": market_info.get("up_price", 0),
            "down_price": market_info.get("down_price", 0),
        }

    return f"""你是 BTC 短周期预测市场交易分析师。
根据以下本地技术分析数据和市场信息，给出判断。

本地技术分析:
{compact}

市场信息:
{market_block}

请用简体中文回答，给出:
1. UP/DOWN 概率判断
2. 建议操作（买UP/买DOWN/不交易）
3. 置信度（高/中/低）
4. 简要理由
5. 风险提示"""
