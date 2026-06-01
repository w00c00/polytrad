from datetime import datetime, timezone

from app.services.sports_quotes import QuoteSnapshot
from app.services.sports_strategy import StrategyAction, StrategySignal
from app.services.strategy_discipline import DisciplineAction, evaluate_signal_discipline
from app.services.strategy_paper import build_paper_signal
from app.services.strategy_paper_eval import evaluate_paper_signal


def make_quote(*, best_bid=0.48, best_ask=0.52, yes_price=0.52):
    return QuoteSnapshot(
        market_slug="nba-game",
        token_id="yes-token",
        best_bid=best_bid,
        best_ask=best_ask,
        spread=None if best_bid is None or best_ask is None else best_ask - best_bid,
        liquidity=500,
        yes_price=yes_price,
    )


def make_initial_buy():
    return build_paper_signal(
        strategy_name="sports_in_play_v1",
        quote=make_quote(),
        signal=StrategySignal(StrategyAction.BUY, 0.08, 0.82, "initial edge"),
        fair_probability=0.60,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_discipline_keeps_profitable_initial_signal_against_weak_exit():
    initial = make_initial_buy()
    current = make_quote(best_bid=0.62, best_ask=0.64, yes_price=0.64)
    evaluation = evaluate_paper_signal(initial, current)
    candidate = StrategySignal(StrategyAction.SELL, 0.07, 0.7, "small reversal")

    decision = evaluate_signal_discipline(
        initial_signal=initial,
        current_evaluation=evaluation,
        candidate_signal=candidate,
    )

    assert decision.action == DisciplineAction.KEEP_INITIAL
    assert decision.recommended_signal_action == "BUY"
    assert decision.opportunity_cost == 0.1
    assert decision.switch_hurdle > candidate.edge


def test_discipline_allows_exit_when_reversal_clears_hurdle():
    initial = make_initial_buy()
    current = make_quote(best_bid=0.62, best_ask=0.64, yes_price=0.64)
    evaluation = evaluate_paper_signal(initial, current)
    candidate = StrategySignal(StrategyAction.SELL, 0.22, 0.9, "strong reversal")

    decision = evaluate_signal_discipline(
        initial_signal=initial,
        current_evaluation=evaluation,
        candidate_signal=candidate,
    )

    assert decision.action == DisciplineAction.ALLOW_EXIT
    assert decision.recommended_signal_action == "SELL"


def test_discipline_blocks_early_churn_during_minimum_hold_window():
    initial = make_initial_buy()
    evaluation = evaluate_paper_signal(initial, make_quote(best_bid=0.50, best_ask=0.52, yes_price=0.52))
    candidate = StrategySignal(StrategyAction.SELL, 0.2, 0.8, "early reversal")

    decision = evaluate_signal_discipline(
        initial_signal=initial,
        current_evaluation=evaluation,
        candidate_signal=candidate,
        seconds_since_entry=120,
        min_hold_seconds=900,
    )

    assert decision.action == DisciplineAction.KEEP_INITIAL
    assert "minimum hold window" in decision.reason


def test_discipline_blocks_switch_to_other_market_without_large_edge():
    initial = make_initial_buy()
    current = make_quote(best_bid=0.62, best_ask=0.64, yes_price=0.64)
    evaluation = evaluate_paper_signal(initial, current)
    candidate = StrategySignal(StrategyAction.BUY, 0.12, 0.8, "other market")

    decision = evaluate_signal_discipline(
        initial_signal=initial,
        current_evaluation=evaluation,
        candidate_signal=candidate,
        candidate_market_slug="other-game",
        candidate_token_id="other-token",
    )

    assert decision.action == DisciplineAction.BLOCK_SWITCH
    assert decision.recommended_signal_action == "BUY"
    assert decision.switch_hurdle == 0.2


def test_discipline_allows_replacement_when_initial_thesis_invalid():
    initial = make_initial_buy()
    evaluation = evaluate_paper_signal(initial, make_quote(best_bid=0.45, best_ask=0.47, yes_price=0.47))
    candidate = StrategySignal(StrategyAction.SELL, 0.03, 0.6, "injury invalidated thesis")

    decision = evaluate_signal_discipline(
        initial_signal=initial,
        current_evaluation=evaluation,
        candidate_signal=candidate,
        thesis_still_valid=False,
    )

    assert decision.action == DisciplineAction.ALLOW_EXIT
