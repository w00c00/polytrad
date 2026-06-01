from __future__ import annotations

from dataclasses import dataclass
from app.services.enum_compat import StrEnum
from math import exp
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.sports_live import SportsLiveState


class StrategyAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WATCH = "WATCH"


@dataclass(frozen=True)
class MarketQuote:
    market_slug: str
    token_id: str
    yes_price: float
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    liquidity: float = 0.0
    volume_24h: float = 0.0


@dataclass(frozen=True)
class StrategySignal:
    action: StrategyAction
    edge: float
    confidence: float
    reason: str
    entry_price: float | None = None
    exit_price: float | None = None


def clamp_probability(value: float) -> float:
    return min(max(value, 0.01), 0.99)


def american_odds_to_probability(odds: int | float) -> float:
    if odds == 0:
        raise ValueError("American odds cannot be zero")
    if odds > 0:
        return 100 / (float(odds) + 100)
    return abs(float(odds)) / (abs(float(odds)) + 100)


def devig_two_way(prob_a: float, prob_b: float) -> tuple[float, float]:
    total = prob_a + prob_b
    if total <= 0:
        raise ValueError("probability total must be positive")
    return prob_a / total, prob_b / total


def live_momentum_adjustment(state: SportsLiveState, sport: str) -> float:
    """Return a small home-side probability adjustment from score state."""

    if not state.live or state.ended or state.score_diff is None:
        return 0.0

    sport_key = sport.lower()
    scale = {
        "nba": 0.018,
        "basketball": 0.018,
        "nfl": 0.028,
        "football": 0.028,
        "soccer": 0.055,
    }.get(sport_key, 0.02)

    return clamp_probability(0.5 + (1 / (1 + exp(-state.score_diff * scale)) - 0.5)) - 0.5


def evaluate_in_play_trade(
    quote: MarketQuote,
    fair_probability: float,
    *,
    min_edge: float = 0.05,
    max_spread: float = 0.08,
    min_liquidity: float = 100.0,
) -> StrategySignal:
    """Compare a live fair probability against Polymarket price and liquidity."""

    fair = clamp_probability(fair_probability)
    entry_price = quote.best_ask if quote.best_ask is not None else quote.yes_price
    exit_price = quote.best_bid if quote.best_bid is not None else quote.yes_price
    spread = quote.spread
    if spread is None and quote.best_bid is not None and quote.best_ask is not None:
        spread = max(quote.best_ask - quote.best_bid, 0)

    if quote.liquidity < min_liquidity:
        return StrategySignal(StrategyAction.WATCH, 0.0, 0.2, "liquidity below threshold")
    if spread is not None and spread > max_spread:
        return StrategySignal(StrategyAction.WATCH, 0.0, 0.25, "spread too wide")

    buy_edge = fair - entry_price
    sell_edge = exit_price - fair
    if buy_edge >= min_edge:
        confidence = min(0.95, 0.5 + buy_edge * 4)
        return StrategySignal(StrategyAction.BUY, buy_edge, confidence, "fair probability exceeds entry price", entry_price=entry_price)
    if sell_edge >= min_edge:
        confidence = min(0.95, 0.5 + sell_edge * 4)
        return StrategySignal(StrategyAction.SELL, sell_edge, confidence, "exit price exceeds fair probability", exit_price=exit_price)
    return StrategySignal(StrategyAction.HOLD, max(buy_edge, sell_edge), 0.4, "edge below threshold")


def evaluate_championship_entry(
    quote: MarketQuote,
    fair_probability: float,
    *,
    launch_age_hours: float,
    schedule_catalyst_score: float,
    min_edge: float = 0.06,
    max_launch_age_hours: float = 72,
    max_entry_price: float = 0.35,
) -> StrategySignal:
    """Score early tournament winner markets before schedule/news repricing."""

    fair = clamp_probability(fair_probability)
    entry_price = quote.best_ask if quote.best_ask is not None else quote.yes_price
    edge = fair - entry_price
    catalyst = min(max(schedule_catalyst_score, 0.0), 1.0)

    if launch_age_hours > max_launch_age_hours:
        return StrategySignal(StrategyAction.WATCH, edge, 0.25, "market is no longer early-launch")
    if entry_price > max_entry_price:
        return StrategySignal(StrategyAction.WATCH, edge, 0.3, "entry price above championship cap")
    if edge >= min_edge and catalyst >= 0.5:
        confidence = min(0.9, 0.45 + edge * 3 + catalyst * 0.2)
        return StrategySignal(StrategyAction.BUY, edge, confidence, "early market has probability edge and schedule catalyst", entry_price=entry_price)
    return StrategySignal(StrategyAction.HOLD, edge, 0.35, "championship edge or catalyst below threshold")
