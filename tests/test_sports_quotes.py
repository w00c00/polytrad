import pytest

from app.services import sports_quotes
from app.services.sports_quotes import build_quote_snapshot, fetch_quote_snapshot, snapshot_to_market_quote


def test_build_quote_snapshot_from_dict_levels():
    snapshot = build_quote_snapshot(
        market_slug="nba-game",
        token_id="yes-token",
        fallback_yes_price=0.5,
        orderbook={
            "bids": [{"price": "0.48", "size": "50"}, {"price": "0.49", "size": "10"}],
            "asks": [{"price": "0.53", "size": "25"}, {"price": "0.52", "size": "20"}],
        },
    )

    assert snapshot.best_bid == 0.49
    assert snapshot.best_ask == 0.52
    assert snapshot.spread == pytest.approx(0.03)
    assert snapshot.yes_price == 0.52
    assert snapshot.liquidity == pytest.approx(52.55)


def test_build_quote_snapshot_uses_fallback_without_asks():
    snapshot = build_quote_snapshot(
        market_slug="nba-game",
        token_id="yes-token",
        fallback_yes_price=0.42,
        orderbook={"bids": [{"price": "0.40", "size": "10"}], "asks": []},
    )

    assert snapshot.best_ask is None
    assert snapshot.spread is None
    assert snapshot.yes_price == 0.42


def test_snapshot_to_market_quote():
    snapshot = build_quote_snapshot(
        market_slug="nba-game",
        token_id="yes-token",
        fallback_yes_price=0.5,
        orderbook={"bids": [{"price": "0.48", "size": "10"}], "asks": [{"price": "0.52", "size": "10"}]},
    )

    quote = snapshot_to_market_quote(snapshot, volume_24h=1200)

    assert quote.market_slug == "nba-game"
    assert quote.best_bid == 0.48
    assert quote.best_ask == 0.52
    assert quote.volume_24h == 1200


@pytest.mark.asyncio
async def test_fetch_quote_snapshot(monkeypatch):
    async def mock_orderbook(token_id):
        assert token_id == "yes-token"
        return {"bids": [{"price": "0.44", "size": "10"}], "asks": [{"price": "0.47", "size": "10"}]}

    monkeypatch.setattr(sports_quotes.clob_api, "get_orderbook", mock_orderbook)

    snapshot = await fetch_quote_snapshot(market_slug="game", token_id="yes-token", fallback_yes_price=0.5)

    assert snapshot.best_bid == 0.44
    assert snapshot.best_ask == 0.47
