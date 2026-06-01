from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from app.services.sports_strategy import (
    MarketQuote,
    StrategyAction,
    StrategySignal,
    clamp_probability,
    evaluate_in_play_trade,
)
from app.services.strategy_core import CatalystReliability


@dataclass(frozen=True)
class ElectionCountState:
    market_slug: str
    yes_side: str
    reporting_pct: float
    reported_margin_pct: float
    expected_margin_pct: float
    feed_latency_seconds: float | None
    source_reliability: CatalystReliability
    source: str = "official_count"


@dataclass(frozen=True)
class ElectionLiveCountSignal:
    market_slug: str
    yes_side: str
    baseline_probability: float
    adjusted_probability: float
    probability_adjustment: float
    reporting_pct: float
    signal: StrategySignal


def election_count_probability_adjustment(state: ElectionCountState) -> float:
    reporting = min(max(state.reporting_pct, 0.0), 1.0)
    surprise = state.reported_margin_pct - state.expected_margin_pct
    reliability_weight = {
        CatalystReliability.HIGH: 1.0,
        CatalystReliability.MEDIUM: 0.65,
        CatalystReliability.LOW: 0.35,
    }[state.source_reliability]
    adjustment = surprise * sqrt(reporting) * reliability_weight * 1.8
    return round(max(min(adjustment, 0.2), -0.2), 6)


def evaluate_election_live_count(
    quote: MarketQuote,
    state: ElectionCountState,
    *,
    baseline_probability: float,
    min_reporting_pct: float = 0.05,
    max_feed_latency_seconds: float = 60,
    min_edge: float = 0.05,
    max_spread: float = 0.08,
    min_liquidity: float = 100.0,
) -> ElectionLiveCountSignal:
    if quote.market_slug != state.market_slug:
        raise ValueError("quote market does not match election count state")

    baseline = clamp_probability(baseline_probability)
    reporting = min(max(state.reporting_pct, 0.0), 1.0)
    adjustment = election_count_probability_adjustment(state)
    adjusted = clamp_probability(baseline + adjustment)

    if reporting < min_reporting_pct:
        signal = StrategySignal(
            action=StrategyAction.WATCH,
            edge=0.0,
            confidence=0.2,
            reason="too little vote reported for count-based repricing",
        )
    elif state.feed_latency_seconds is None or state.feed_latency_seconds > max_feed_latency_seconds:
        signal = StrategySignal(
            action=StrategyAction.WATCH,
            edge=0.0,
            confidence=0.2,
            reason="election count feed is stale or latency is unknown",
        )
    elif state.source_reliability == CatalystReliability.LOW and reporting < 0.3:
        signal = StrategySignal(
            action=StrategyAction.WATCH,
            edge=0.0,
            confidence=0.25,
            reason="low reliability count source before enough reporting",
        )
    else:
        signal = evaluate_in_play_trade(
            quote,
            adjusted,
            min_edge=min_edge,
            max_spread=max_spread,
            min_liquidity=min_liquidity,
        )
        signal = StrategySignal(
            action=signal.action,
            edge=signal.edge,
            confidence=signal.confidence,
            reason=f"election count adjusted fair probability; {signal.reason}",
            entry_price=signal.entry_price,
            exit_price=signal.exit_price,
        )

    return ElectionLiveCountSignal(
        market_slug=state.market_slug,
        yes_side=state.yes_side,
        baseline_probability=baseline,
        adjusted_probability=adjusted,
        probability_adjustment=adjustment,
        reporting_pct=reporting,
        signal=signal,
    )
