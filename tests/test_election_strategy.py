import pytest

from app.services.election_strategy import (
    ElectionCountState,
    election_count_probability_adjustment,
    evaluate_election_live_count,
)
from app.services.sports_strategy import MarketQuote
from app.services.strategy_core import CatalystReliability


def make_quote():
    return MarketQuote(
        market_slug="senate-state-winner",
        token_id="yes-token",
        yes_price=0.50,
        best_bid=0.49,
        best_ask=0.51,
        spread=0.02,
        liquidity=1000,
    )


def make_state(**overrides):
    data = {
        "market_slug": "senate-state-winner",
        "yes_side": "Candidate A",
        "reporting_pct": 0.45,
        "reported_margin_pct": 0.06,
        "expected_margin_pct": 0.01,
        "feed_latency_seconds": 8,
        "source_reliability": CatalystReliability.HIGH,
    }
    data.update(overrides)
    return ElectionCountState(**data)


def test_election_count_probability_adjustment_uses_margin_surprise():
    adjustment = election_count_probability_adjustment(make_state())

    assert adjustment > 0
    assert adjustment <= 0.2


def test_evaluate_election_live_count_buy_signal_from_count_surprise():
    result = evaluate_election_live_count(
        make_quote(),
        make_state(),
        baseline_probability=0.51,
    )

    assert result.adjusted_probability > result.baseline_probability
    assert result.signal.action == "BUY"
    assert result.signal.entry_price == 0.51
    assert "election count adjusted" in result.signal.reason


def test_evaluate_election_live_count_blocks_too_little_reporting():
    result = evaluate_election_live_count(
        make_quote(),
        make_state(reporting_pct=0.02),
        baseline_probability=0.51,
    )

    assert result.signal.action == "WATCH"
    assert "too little vote reported" in result.signal.reason


def test_evaluate_election_live_count_blocks_stale_feed():
    result = evaluate_election_live_count(
        make_quote(),
        make_state(feed_latency_seconds=120),
        baseline_probability=0.51,
    )

    assert result.signal.action == "WATCH"
    assert "stale" in result.signal.reason


def test_evaluate_election_live_count_rejects_mismatched_market():
    with pytest.raises(ValueError, match="does not match"):
        evaluate_election_live_count(
            MarketQuote("other-market", "yes-token", yes_price=0.5),
            make_state(),
            baseline_probability=0.51,
        )
