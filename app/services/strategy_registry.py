from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyModuleDefinition:
    module_id: str
    name: str
    domain: str
    execution_mode: str
    summary: str
    required_inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    risk_controls: tuple[str, ...]
    api_paths: tuple[str, ...]
    status: str = "paper"


def list_strategy_modules() -> tuple[StrategyModuleDefinition, ...]:
    return (
        StrategyModuleDefinition(
            module_id="sports_in_play_v1",
            name="Sports in-play fair-value signal",
            domain="sports",
            execution_mode="read_only_paper",
            summary="Compare live fair probability with Polymarket best ask/bid during NBA, NFL, or football matches.",
            required_inputs=(
                "market_slug",
                "token_id",
                "quote_snapshot",
                "fair_probability",
                "optional_live_text_state",
            ),
            outputs=("action", "edge", "confidence", "reason", "entry_price", "exit_price"),
            risk_controls=("min_edge", "max_spread", "min_liquidity", "feed_staleness_check", "hold_discipline"),
            api_paths=("/api/strategy/in-play", "/api/strategy/paper-signal", "/api/strategy/paper-evaluate", "/api/strategy/discipline"),
        ),
        StrategyModuleDefinition(
            module_id="sports_championship_early_v1",
            name="Sports championship early-entry signal",
            domain="sports",
            execution_mode="read_only_paper",
            summary="Score newly launched tournament winner markets before schedule or bracket catalysts are fully priced.",
            required_inputs=(
                "market_slug",
                "token_id",
                "quote_snapshot",
                "fair_probability",
                "launch_age_hours",
                "schedule_catalyst_score",
            ),
            outputs=("action", "edge", "confidence", "reason", "entry_price"),
            risk_controls=("min_edge", "max_launch_age_hours", "max_entry_price", "schedule_catalyst_threshold", "hold_discipline"),
            api_paths=("/api/strategy/championship", "/api/strategy/paper-signal", "/api/strategy/paper-evaluate", "/api/strategy/discipline"),
        ),
        StrategyModuleDefinition(
            module_id="world_cup_tagging_v1",
            name="World Cup market tag set",
            domain="sports_world_cup",
            execution_mode="read_only",
            summary="Group World Cup live novelty, knockout, and early champion markets under strategy-ready tags.",
            required_inputs=("market_title", "market_slug", "optional_event_intel_payload"),
            outputs=("tag_id", "label", "strategy_modules", "catalysts", "risk_controls"),
            risk_controls=("feed_staleness_check", "hold_discipline", "paper_only_for_new_tags"),
            api_paths=("/api/strategy/world-cup-tags",),
            status="tagging",
        ),
        StrategyModuleDefinition(
            module_id="event_domain_fit_v1",
            name="Event-driven domain fit check",
            domain="cross_domain",
            execution_mode="read_only",
            summary="Check whether a non-sports Polymarket category has the feed, liquidity, and resolution shape needed for this strategy family.",
            required_inputs=(
                "domain",
                "has_realtime_feed",
                "feed_latency_seconds",
                "has_liquid_polymarket_markets",
                "catalyst_reliability",
                "market_reacts_gradually",
                "objective_resolution",
            ),
            outputs=("score", "applicable", "reason", "required_modules"),
            risk_controls=("objective_resolution_required", "realtime_feed_required", "liquidity_required"),
            api_paths=("/api/strategy/domain-fit",),
            status="design_gate",
        ),
        StrategyModuleDefinition(
            module_id="election_live_count_v1",
            name="Election live-count repricing signal",
            domain="politics",
            execution_mode="read_only_paper",
            summary="Adjust fair probability from official count margin surprises and compare it with Polymarket quotes.",
            required_inputs=(
                "market_slug",
                "token_id",
                "quote_snapshot",
                "baseline_probability",
                "reporting_pct",
                "reported_margin_pct",
                "expected_margin_pct",
                "feed_latency_seconds",
                "source_reliability",
            ),
            outputs=("adjusted_probability", "probability_adjustment", "action", "edge", "confidence", "reason"),
            risk_controls=("min_reporting_pct", "max_feed_latency_seconds", "min_edge", "max_spread", "min_liquidity", "hold_discipline"),
            api_paths=("/api/strategy/election-live-count", "/api/strategy/paper-signal", "/api/strategy/discipline"),
        ),
    )


def get_strategy_module(module_id: str) -> StrategyModuleDefinition | None:
    return next((module for module in list_strategy_modules() if module.module_id == module_id), None)
