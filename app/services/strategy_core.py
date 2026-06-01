from __future__ import annotations

from dataclasses import dataclass
from app.services.enum_compat import StrEnum


class CatalystReliability(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class StrategyFit:
    domain: str
    applicable: bool
    score: float
    reason: str
    required_modules: tuple[str, ...]
    blocking_risks: tuple[str, ...] = ()


def score_event_driven_domain(
    *,
    domain: str,
    has_realtime_feed: bool,
    feed_latency_seconds: float | None,
    has_liquid_polymarket_markets: bool,
    catalyst_reliability: CatalystReliability,
    market_reacts_gradually: bool,
    objective_resolution: bool,
) -> StrategyFit:
    """Assess whether the sports live-edge strategy transfers to another domain."""

    risks: list[str] = []
    score = 0.0

    if has_realtime_feed:
        score += 0.22
    else:
        risks.append("no realtime feed")

    if feed_latency_seconds is None:
        risks.append("unknown feed latency")
    elif feed_latency_seconds <= 10:
        score += 0.18
    elif feed_latency_seconds <= 60:
        score += 0.09
    else:
        risks.append("feed too slow for in-play repricing")

    if has_liquid_polymarket_markets:
        score += 0.2
    else:
        risks.append("insufficient Polymarket liquidity")

    reliability_points = {
        CatalystReliability.HIGH: 0.18,
        CatalystReliability.MEDIUM: 0.1,
        CatalystReliability.LOW: 0.03,
    }
    score += reliability_points[catalyst_reliability]
    if catalyst_reliability == CatalystReliability.LOW:
        risks.append("catalyst is hard to verify")

    if market_reacts_gradually:
        score += 0.12
    else:
        risks.append("market reprices too quickly after catalyst")

    if objective_resolution:
        score += 0.1
    else:
        risks.append("resolution is subjective or ambiguous")

    score = round(min(score, 1.0), 3)
    applicable = score >= 0.65 and not any(
        risk in risks
        for risk in (
            "no realtime feed",
            "insufficient Polymarket liquidity",
            "resolution is subjective or ambiguous",
        )
    )

    required_modules = (
        "market_discovery",
        "catalyst_feed",
        "quote_snapshot",
        "fair_probability_model",
        "risk_gate",
    )
    reason = "fits event-driven repricing strategy" if applicable else "does not yet fit event-driven repricing strategy"
    return StrategyFit(domain, applicable, score, reason, required_modules, tuple(risks))
