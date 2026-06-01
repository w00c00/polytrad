from datetime import datetime, timezone

import pytest

from app.services.sports_live import SportsLiveState
from app.services.sports_quotes import QuoteSnapshot
from app.services.sports_strategy import StrategyAction, StrategySignal
from app.services.strategy_paper import (
    build_paper_signal,
    paper_signal_from_dict,
    paper_signal_from_json,
    paper_signal_to_json,
    persist_paper_signal,
)


class FakeDB:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, record):
        self.added.append(record)

    async def commit(self):
        self.commits += 1


def make_quote():
    return QuoteSnapshot(
        market_slug="nba-game",
        token_id="yes-token",
        best_bid=0.48,
        best_ask=0.52,
        spread=0.04,
        liquidity=500,
        yes_price=0.52,
    )


def test_build_paper_signal_serializes_signal_and_live_state():
    paper = build_paper_signal(
        strategy_name="sports_in_play_v1",
        quote=make_quote(),
        signal=StrategySignal(StrategyAction.BUY, 0.08, 0.82, "edge"),
        fair_probability=0.60,
        live_state=SportsLiveState("nba-game", live=True, ended=False, home_score=80, away_score=75),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert paper.action == "BUY"
    assert paper.edge == 0.08
    assert paper.quote["best_ask"] == 0.52
    assert paper.live_state is not None
    assert paper.live_state["home_score"] == 80


def test_paper_signal_to_json():
    paper = build_paper_signal(
        strategy_name="sports_in_play_v1",
        quote=make_quote(),
        signal=StrategySignal(StrategyAction.HOLD, 0.01, 0.4, "edge below threshold"),
        fair_probability=0.53,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    payload = paper_signal_to_json(paper)

    assert '"strategy_name": "sports_in_play_v1"' in payload
    assert '"action": "HOLD"' in payload


def test_paper_signal_from_json_round_trips_payload():
    paper = build_paper_signal(
        strategy_name="sports_in_play_v1",
        quote=make_quote(),
        signal=StrategySignal(StrategyAction.BUY, 0.08, 0.82, "edge"),
        fair_probability=0.60,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    restored = paper_signal_from_json(paper_signal_to_json(paper))

    assert restored.strategy_name == paper.strategy_name
    assert restored.quote["best_ask"] == 0.52


def test_paper_signal_from_dict_rejects_invalid_payload():
    with pytest.raises(ValueError, match="missing quote"):
        paper_signal_from_dict({"strategy_name": "sports_in_play_v1"})


@pytest.mark.asyncio
async def test_persist_paper_signal():
    db = FakeDB()
    paper = build_paper_signal(
        strategy_name="sports_in_play_v1",
        quote=make_quote(),
        signal=StrategySignal(StrategyAction.WATCH, 0.0, 0.2, "liquidity below threshold"),
        fair_probability=0.60,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    record = await persist_paper_signal(db, paper)

    assert record.scan_type == "paper_signal"
    assert db.added == [record]
    assert db.commits == 1
