from datetime import datetime, timezone

import pytest

from app.services.sports_quotes import QuoteSnapshot
from app.services.sports_strategy import StrategyAction, StrategySignal
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


def make_paper(action: StrategyAction):
    return build_paper_signal(
        strategy_name="sports_in_play_v1",
        quote=make_quote(),
        signal=StrategySignal(action, 0.08, 0.82, "edge"),
        fair_probability=0.60,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_evaluate_open_buy_signal_marks_against_current_bid():
    evaluation = evaluate_paper_signal(make_paper(StrategyAction.BUY), make_quote(best_bid=0.62, best_ask=0.64, yes_price=0.64))

    assert evaluation.status == "open"
    assert evaluation.entry_price == 0.52
    assert evaluation.mark_price == 0.62
    assert evaluation.pnl == 0.1
    assert evaluation.pnl_pct == 0.192308


def test_evaluate_open_sell_signal_marks_against_current_ask():
    evaluation = evaluate_paper_signal(make_paper(StrategyAction.SELL), make_quote(best_bid=0.38, best_ask=0.40, yes_price=0.40))

    assert evaluation.status == "open"
    assert evaluation.entry_price == 0.48
    assert evaluation.mark_price == 0.40
    assert evaluation.pnl == 0.08


def test_evaluate_resolved_buy_signal_uses_final_outcome():
    evaluation = evaluate_paper_signal(make_paper(StrategyAction.BUY), make_quote(), resolved_yes=True)

    assert evaluation.status == "resolved"
    assert evaluation.mark_price == 1.0
    assert evaluation.pnl == 0.48


def test_evaluate_hold_signal_has_no_entry():
    evaluation = evaluate_paper_signal(make_paper(StrategyAction.HOLD), make_quote())

    assert evaluation.status == "not_entered"
    assert evaluation.entry_price is None
    assert evaluation.pnl == 0.0


def test_evaluate_rejects_mismatched_quote():
    current = QuoteSnapshot("other-game", "yes-token", 0.5, 0.52, 0.02, 500, 0.52)

    with pytest.raises(ValueError, match="does not match"):
        evaluate_paper_signal(make_paper(StrategyAction.BUY), current)
