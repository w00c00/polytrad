from __future__ import annotations

from dataclasses import dataclass

from app.services.strategy_core import CatalystReliability, StrategyFit, score_event_driven_domain


@dataclass(frozen=True)
class DomainCandidate:
    domain_id: str
    name: str
    category: str
    strategy_mode: str
    thesis: str
    catalyst_examples: tuple[str, ...]
    live_feed_options: tuple[str, ...]
    market_shape: str
    fit: StrategyFit
    recommendation: str


@dataclass(frozen=True)
class DomainCandidateProfile:
    domain_id: str
    name: str
    category: str
    strategy_mode: str
    thesis: str
    catalyst_examples: tuple[str, ...]
    live_feed_options: tuple[str, ...]
    market_shape: str
    has_realtime_feed: bool
    feed_latency_seconds: float | None
    has_liquid_polymarket_markets: bool
    catalyst_reliability: CatalystReliability
    market_reacts_gradually: bool
    objective_resolution: bool


def _recommendation(fit: StrategyFit) -> str:
    if fit.applicable and fit.score >= 0.85:
        return "pilot"
    if fit.score >= 0.65 and not fit.applicable:
        return "watchlist_after_risk_fix"
    if fit.score >= 0.5:
        return "research_only"
    return "reject"


def _candidate_profiles() -> tuple[DomainCandidateProfile, ...]:
    return (
        DomainCandidateProfile(
            domain_id="election_live_count",
            name="Election live-count markets",
            category="politics",
            strategy_mode="in_play_repricing",
            thesis="Official count updates can move probability gradually when markets lag county or district-level results.",
            catalyst_examples=("precinct batch", "county margin swing", "turnout model update"),
            live_feed_options=("official election result feeds", "state or county result pages", "trusted news election desks"),
            market_shape="binary winner, state winner, or seat-control markets with objective final resolution",
            has_realtime_feed=True,
            feed_latency_seconds=10,
            has_liquid_polymarket_markets=True,
            catalyst_reliability=CatalystReliability.HIGH,
            market_reacts_gradually=True,
            objective_resolution=True,
        ),
        DomainCandidateProfile(
            domain_id="award_show_results",
            name="Award show live-result markets",
            category="entertainment",
            strategy_mode="in_play_repricing",
            thesis="Official award announcements create sequential catalysts, but liquidity is usually event-specific.",
            catalyst_examples=("category announcement", "acceptance order", "official winner post"),
            live_feed_options=("official broadcast live blog", "official social feed", "major media live coverage"),
            market_shape="winner markets for objective announced awards",
            has_realtime_feed=True,
            feed_latency_seconds=30,
            has_liquid_polymarket_markets=True,
            catalyst_reliability=CatalystReliability.HIGH,
            market_reacts_gradually=True,
            objective_resolution=True,
        ),
        DomainCandidateProfile(
            domain_id="macro_release",
            name="Macro release markets",
            category="economics",
            strategy_mode="release_repricing",
            thesis="Official macro data is reliable, but the first release often reprices faster than a manual strategy can enter.",
            catalyst_examples=("CPI print", "jobs report", "FOMC statement"),
            live_feed_options=("official agency release", "economic calendar API", "exchange newswire"),
            market_shape="threshold or yes/no markets around official economic statistics",
            has_realtime_feed=True,
            feed_latency_seconds=2,
            has_liquid_polymarket_markets=True,
            catalyst_reliability=CatalystReliability.HIGH,
            market_reacts_gradually=False,
            objective_resolution=True,
        ),
        DomainCandidateProfile(
            domain_id="weather_disaster",
            name="Weather and disaster markets",
            category="weather",
            strategy_mode="forecast_drift",
            thesis="Forecast tracks move before resolution, but liquidity and exact market resolution must be verified per market.",
            catalyst_examples=("forecast cone shift", "landfall probability", "official warning update"),
            live_feed_options=("official weather agency feeds", "forecast model updates", "satellite or warning feeds"),
            market_shape="threshold, landfall, or location outcome markets",
            has_realtime_feed=True,
            feed_latency_seconds=60,
            has_liquid_polymarket_markets=False,
            catalyst_reliability=CatalystReliability.MEDIUM,
            market_reacts_gradually=True,
            objective_resolution=True,
        ),
        DomainCandidateProfile(
            domain_id="legal_regulatory",
            name="Legal and regulatory decision markets",
            category="policy",
            strategy_mode="watch_only",
            thesis="Court or agency updates can be meaningful, but interpretations and resolution wording often create ambiguity.",
            catalyst_examples=("court docket update", "agency vote", "regulatory filing"),
            live_feed_options=("court docket feeds", "agency calendars", "official filings"),
            market_shape="decision or approval markets with high wording risk",
            has_realtime_feed=True,
            feed_latency_seconds=60,
            has_liquid_polymarket_markets=False,
            catalyst_reliability=CatalystReliability.MEDIUM,
            market_reacts_gradually=True,
            objective_resolution=False,
        ),
        DomainCandidateProfile(
            domain_id="celebrity_rumor",
            name="Celebrity and rumor markets",
            category="culture",
            strategy_mode="reject",
            thesis="Catalysts are hard to verify and resolution is often subjective, so this does not fit the strategy family.",
            catalyst_examples=("unverified post", "tabloid report", "social media rumor"),
            live_feed_options=("social media stream", "news mentions"),
            market_shape="rumor-driven markets with weak objective signal",
            has_realtime_feed=True,
            feed_latency_seconds=30,
            has_liquid_polymarket_markets=False,
            catalyst_reliability=CatalystReliability.LOW,
            market_reacts_gradually=True,
            objective_resolution=False,
        ),
    )


def list_domain_candidates() -> tuple[DomainCandidate, ...]:
    candidates = []
    for profile in _candidate_profiles():
        fit = score_event_driven_domain(
            domain=profile.name,
            has_realtime_feed=profile.has_realtime_feed,
            feed_latency_seconds=profile.feed_latency_seconds,
            has_liquid_polymarket_markets=profile.has_liquid_polymarket_markets,
            catalyst_reliability=profile.catalyst_reliability,
            market_reacts_gradually=profile.market_reacts_gradually,
            objective_resolution=profile.objective_resolution,
        )
        candidates.append(
            DomainCandidate(
                domain_id=profile.domain_id,
                name=profile.name,
                category=profile.category,
                strategy_mode=profile.strategy_mode,
                thesis=profile.thesis,
                catalyst_examples=profile.catalyst_examples,
                live_feed_options=profile.live_feed_options,
                market_shape=profile.market_shape,
                fit=fit,
                recommendation=_recommendation(fit),
            )
        )
    return tuple(sorted(candidates, key=lambda candidate: candidate.fit.score, reverse=True))
