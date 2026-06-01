from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorldCupMarketTag:
    tag_id: str
    label: str
    strategy_modules: tuple[str, ...]
    market_patterns: tuple[str, ...]
    catalysts: tuple[str, ...]
    risk_controls: tuple[str, ...]


def list_world_cup_market_tags() -> tuple[WorldCupMarketTag, ...]:
    return (
        WorldCupMarketTag(
            tag_id="world_cup_live_fun",
            label="世界杯实时趣味盘口",
            strategy_modules=("sports_in_play_v1", "sports_live_text_v1", "sports_hold_discipline_v1"),
            market_patterns=("next goal", "first goal", "clean sheet", "team to advance", "player card"),
            catalysts=("lineup", "injury", "red_card", "goal", "var_decision", "stoppage_time"),
            risk_controls=("feed_staleness_check", "max_spread", "min_liquidity", "hold_discipline"),
        ),
        WorldCupMarketTag(
            tag_id="world_cup_knockout_equal_strength",
            label="世界杯淘汰赛均势交易",
            strategy_modules=("sports_in_play_v1", "sports_championship_early_v1", "sports_hold_discipline_v1"),
            market_patterns=("match winner", "to qualify", "penalty shootout", "correct score"),
            catalysts=("bracket_path", "rest_days", "lineup", "live_momentum", "extra_time"),
            risk_controls=("pre_match_thesis_required", "hold_discipline", "min_switch_edge", "min_hold_seconds", "churn_penalty"),
        ),
        WorldCupMarketTag(
            tag_id="world_cup_champion_early",
            label="世界杯冠军早期盘口",
            strategy_modules=("sports_championship_early_v1", "event_intel_bridge_v1"),
            market_patterns=("world cup winner", "group winner", "reach final", "top scorer"),
            catalysts=("draw", "group_strength", "bracket_path", "qualification", "injury_news"),
            risk_controls=("max_entry_price", "launch_age_hours", "schedule_catalyst_threshold", "paper_only"),
        ),
    )


def classify_world_cup_market(title: str) -> tuple[WorldCupMarketTag, ...]:
    normalized = title.lower()
    matches = []
    for tag in list_world_cup_market_tags():
        if any(pattern in normalized for pattern in tag.market_patterns) or "world cup" in normalized or "世界杯" in normalized:
            matches.append(tag)
    return tuple(matches)
