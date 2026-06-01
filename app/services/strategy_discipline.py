from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from app.services.sports_strategy import StrategyAction, StrategySignal

if TYPE_CHECKING:
    from app.services.strategy_paper import PaperStrategySignal
    from app.services.strategy_paper_eval import PaperEvaluation


class DisciplineAction(StrEnum):
    KEEP_INITIAL = "KEEP_INITIAL"
    ALLOW_NEW_SIGNAL = "ALLOW_NEW_SIGNAL"
    ALLOW_EXIT = "ALLOW_EXIT"
    BLOCK_SWITCH = "BLOCK_SWITCH"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class DisciplineDecision:
    action: DisciplineAction
    recommended_signal_action: str
    reason: str
    switch_hurdle: float
    candidate_edge: float
    opportunity_cost: float
    churn_penalty: float


def _is_entered(action: str) -> bool:
    return action in {StrategyAction.BUY, StrategyAction.SELL, "BUY", "SELL"}


def _is_opposite(initial_action: str, candidate_action: StrategyAction) -> bool:
    return (initial_action == "BUY" and candidate_action == StrategyAction.SELL) or (
        initial_action == "SELL" and candidate_action == StrategyAction.BUY
    )


def evaluate_signal_discipline(
    *,
    initial_signal: PaperStrategySignal,
    current_evaluation: PaperEvaluation,
    candidate_signal: StrategySignal,
    candidate_market_slug: str | None = None,
    candidate_token_id: str | None = None,
    thesis_still_valid: bool = True,
    seconds_since_entry: int | None = None,
    churn_count: int = 0,
    min_hold_seconds: int = 900,
    min_switch_edge: float = 0.1,
    min_exit_edge: float = 0.08,
    churn_penalty_step: float = 0.03,
) -> DisciplineDecision:
    """Prevent profitable initial ideas from being churned away by weak later signals."""

    candidate_edge = round(candidate_signal.edge, 6)
    opportunity_cost = max(current_evaluation.pnl, 0.0)
    churn_penalty = max(churn_count, 0) * churn_penalty_step
    switch_hurdle = round(min_switch_edge + opportunity_cost + churn_penalty, 6)

    if not _is_entered(initial_signal.action):
        return DisciplineDecision(
            DisciplineAction.ALLOW_NEW_SIGNAL,
            str(candidate_signal.action),
            "initial signal did not create a simulated entry",
            switch_hurdle,
            candidate_edge,
            opportunity_cost,
            churn_penalty,
        )

    if not thesis_still_valid:
        if candidate_signal.action in {StrategyAction.HOLD, StrategyAction.WATCH}:
            return DisciplineDecision(
                DisciplineAction.REVIEW,
                StrategyAction.HOLD,
                "initial thesis is invalid but candidate has no executable replacement",
                switch_hurdle,
                candidate_edge,
                opportunity_cost,
                churn_penalty,
            )
        return DisciplineDecision(
            DisciplineAction.ALLOW_EXIT,
            str(candidate_signal.action),
            "initial thesis invalidated; later signal may replace or exit",
            switch_hurdle,
            candidate_edge,
            opportunity_cost,
            churn_penalty,
        )

    if (
        seconds_since_entry is not None
        and seconds_since_entry < min_hold_seconds
        and candidate_signal.action != StrategyAction(initial_signal.action)
    ):
        return DisciplineDecision(
            DisciplineAction.KEEP_INITIAL,
            initial_signal.action,
            "minimum hold window blocks early churn while thesis is still valid",
            switch_hurdle,
            candidate_edge,
            opportunity_cost,
            churn_penalty,
        )

    if _is_opposite(initial_signal.action, candidate_signal.action):
        exit_hurdle = round(min_exit_edge + opportunity_cost + churn_penalty, 6)
        if candidate_signal.edge < exit_hurdle:
            return DisciplineDecision(
                DisciplineAction.KEEP_INITIAL,
                initial_signal.action,
                "opposite signal does not overcome exit hurdle and current opportunity cost",
                exit_hurdle,
                candidate_edge,
                opportunity_cost,
                churn_penalty,
            )
        return DisciplineDecision(
            DisciplineAction.ALLOW_EXIT,
            str(candidate_signal.action),
            "opposite signal is strong enough to overcome exit hurdle",
            exit_hurdle,
            candidate_edge,
            opportunity_cost,
            churn_penalty,
        )

    if candidate_signal.action in {StrategyAction.HOLD, StrategyAction.WATCH}:
        return DisciplineDecision(
            DisciplineAction.KEEP_INITIAL,
            initial_signal.action,
            "later signal is not strong enough to replace an active initial thesis",
            switch_hurdle,
            candidate_edge,
            opportunity_cost,
            churn_penalty,
        )

    candidate_market = candidate_market_slug or initial_signal.market_slug
    candidate_token = candidate_token_id or initial_signal.token_id
    same_market = candidate_market == initial_signal.market_slug and candidate_token == initial_signal.token_id
    if same_market:
        return DisciplineDecision(
            DisciplineAction.ALLOW_NEW_SIGNAL,
            str(candidate_signal.action),
            "candidate reinforces the initial direction",
            switch_hurdle,
            candidate_edge,
            opportunity_cost,
            churn_penalty,
        )

    if candidate_signal.edge < switch_hurdle:
        return DisciplineDecision(
            DisciplineAction.BLOCK_SWITCH,
            initial_signal.action,
            "replacement signal does not clear switch hurdle after current opportunity cost",
            switch_hurdle,
            candidate_edge,
            opportunity_cost,
            churn_penalty,
        )

    return DisciplineDecision(
        DisciplineAction.ALLOW_NEW_SIGNAL,
        str(candidate_signal.action),
        "replacement signal clears switch hurdle",
        switch_hurdle,
        candidate_edge,
        opportunity_cost,
        churn_penalty,
    )
