import pytest

from app.services.sports_live import SportsLiveState
from app.services.sports_strategy import (
    MarketQuote,
    StrategyAction,
    american_odds_to_probability,
    devig_two_way,
    evaluate_championship_entry,
    evaluate_in_play_trade,
    live_momentum_adjustment,
)


def test_american_odds_to_probability():
    assert round(american_odds_to_probability(-150), 4) == 0.6
    assert round(american_odds_to_probability(200), 4) == 0.3333
    with pytest.raises(ValueError):
        american_odds_to_probability(0)


def test_devig_two_way():
    home, away = devig_two_way(0.6, 0.5)

    assert round(home + away, 6) == 1
    assert home > away


def test_live_momentum_adjustment_uses_score_diff():
    state = SportsLiveState(slug="nba-game", live=True, ended=False, home_score=80, away_score=70)

    assert live_momentum_adjustment(state, "nba") > 0


def test_live_momentum_adjustment_ignores_ended_game():
    state = SportsLiveState(slug="nba-game", live=False, ended=True, home_score=80, away_score=70)

    assert live_momentum_adjustment(state, "nba") == 0


def test_evaluate_in_play_trade_buy_signal():
    signal = evaluate_in_play_trade(
        MarketQuote("game", "yes-token", yes_price=0.48, best_bid=0.47, best_ask=0.49, liquidity=500),
        fair_probability=0.58,
    )

    assert signal.action == StrategyAction.BUY
    assert signal.edge == pytest.approx(0.09)
    assert signal.entry_price == 0.49


def test_evaluate_in_play_trade_sell_signal():
    signal = evaluate_in_play_trade(
        MarketQuote("game", "yes-token", yes_price=0.54, best_bid=0.55, best_ask=0.57, liquidity=500),
        fair_probability=0.48,
    )

    assert signal.action == StrategyAction.SELL
    assert signal.edge == pytest.approx(0.07)
    assert signal.exit_price == 0.55


def test_evaluate_in_play_trade_blocks_wide_spread():
    signal = evaluate_in_play_trade(
        MarketQuote("game", "yes-token", yes_price=0.50, best_bid=0.40, best_ask=0.55, liquidity=500),
        fair_probability=0.70,
    )

    assert signal.action == StrategyAction.WATCH
    assert "spread" in signal.reason


def test_evaluate_in_play_trade_blocks_low_liquidity():
    signal = evaluate_in_play_trade(MarketQuote("game", "yes-token", yes_price=0.50, liquidity=25), fair_probability=0.70)

    assert signal.action == StrategyAction.WATCH
    assert "liquidity" in signal.reason


def test_evaluate_championship_entry_buy_signal():
    signal = evaluate_championship_entry(
        MarketQuote("champ", "yes-token", yes_price=0.20, best_ask=0.21, liquidity=1000),
        fair_probability=0.31,
        launch_age_hours=12,
        schedule_catalyst_score=0.8,
    )

    assert signal.action == StrategyAction.BUY
    assert signal.entry_price == 0.21


def test_evaluate_championship_entry_blocks_late_market():
    signal = evaluate_championship_entry(
        MarketQuote("champ", "yes-token", yes_price=0.20, liquidity=1000),
        fair_probability=0.31,
        launch_age_hours=96,
        schedule_catalyst_score=0.8,
    )

    assert signal.action == StrategyAction.WATCH
    assert "early" in signal.reason
