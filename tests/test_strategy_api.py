import pytest
from httpx import AsyncClient

from app.services.sports_quotes import QuoteSnapshot


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def quote_payload() -> dict:
    return {
        "market_slug": "nba-game",
        "token_id": "yes-token",
        "yes_price": 0.50,
        "best_bid": 0.49,
        "best_ask": 0.51,
        "spread": 0.02,
        "liquidity": 500,
        "volume_24h": 2000,
    }


@pytest.mark.asyncio
async def test_strategy_domain_fit(client: AsyncClient, user_token: str):
    resp = await client.post(
        "/api/strategy/domain-fit",
        json={
            "domain": "live sports",
            "has_realtime_feed": True,
            "feed_latency_seconds": 5,
            "has_liquid_polymarket_markets": True,
            "catalyst_reliability": "high",
            "market_reacts_gradually": True,
            "objective_resolution": True,
        },
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["applicable"] is True
    assert "quote_snapshot" in data["required_modules"]


@pytest.mark.asyncio
async def test_strategy_no_auth(client: AsyncClient):
    resp = await client.post(
        "/api/strategy/in-play",
        json={"quote": quote_payload(), "fair_probability": 0.6},
    )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_strategy_modules(client: AsyncClient, user_token: str):
    resp = await client.get("/api/strategy/modules", headers=auth(user_token))

    assert resp.status_code == 200
    ids = {item["module_id"] for item in resp.json()["items"]}
    assert "sports_in_play_v1" in ids
    assert "sports_championship_early_v1" in ids
    assert "world_cup_tagging_v1" in ids
    assert "event_domain_fit_v1" in ids


@pytest.mark.asyncio
async def test_strategy_domain_candidates(client: AsyncClient, user_token: str):
    resp = await client.get("/api/strategy/domain-candidates", headers=auth(user_token))

    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = {item["domain_id"] for item in items}
    assert "election_live_count" in ids
    assert "celebrity_rumor" in ids
    assert items[0]["fit"]["score"] >= items[-1]["fit"]["score"]


@pytest.mark.asyncio
async def test_strategy_world_cup_tags(client: AsyncClient, user_token: str):
    resp = await client.get(
        "/api/strategy/world-cup-tags",
        params={"market_title": "2026 FIFA World Cup winner"},
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    items = resp.json()["items"]
    tag_ids = {item["tag_id"] for item in items}
    assert "world_cup_champion_early" in tag_ids
    assert any("sports_championship_early_v1" in item["strategy_modules"] for item in items)


@pytest.mark.asyncio
async def test_strategy_quote_snapshot(client: AsyncClient, user_token: str, monkeypatch):
    from app.api import strategy

    async def mock_snapshot(**kwargs):
        assert kwargs["token_id"] == "yes-token"
        return QuoteSnapshot(
            market_slug=kwargs["market_slug"],
            token_id=kwargs["token_id"],
            best_bid=0.48,
            best_ask=0.52,
            spread=0.04,
            liquidity=400,
            yes_price=0.52,
        )

    monkeypatch.setattr(strategy, "fetch_quote_snapshot", mock_snapshot)

    resp = await client.post(
        "/api/strategy/quote-snapshot",
        json={"market_slug": "nba-game", "token_id": "yes-token", "fallback_yes_price": 0.5},
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    assert resp.json()["best_ask"] == 0.52


@pytest.mark.asyncio
async def test_strategy_in_play_signal(client: AsyncClient, user_token: str):
    resp = await client.post(
        "/api/strategy/in-play",
        json={"quote": quote_payload(), "fair_probability": 0.60},
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "BUY"
    assert data["entry_price"] == 0.51


@pytest.mark.asyncio
async def test_strategy_championship_signal(client: AsyncClient, user_token: str):
    payload = quote_payload()
    payload["yes_price"] = 0.20
    payload["best_ask"] = 0.21
    payload["best_bid"] = 0.20

    resp = await client.post(
        "/api/strategy/championship",
        json={
            "quote": payload,
            "fair_probability": 0.31,
            "launch_age_hours": 12,
            "schedule_catalyst_score": 0.8,
        },
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    assert resp.json()["action"] == "BUY"


@pytest.mark.asyncio
async def test_strategy_election_live_count_signal(client: AsyncClient, user_token: str):
    payload = quote_payload()
    payload["market_slug"] = "senate-state-winner"
    payload["best_ask"] = 0.51

    resp = await client.post(
        "/api/strategy/election-live-count",
        json={
            "quote": payload,
            "yes_side": "Candidate A",
            "baseline_probability": 0.51,
            "reporting_pct": 0.45,
            "reported_margin_pct": 0.06,
            "expected_margin_pct": 0.01,
            "feed_latency_seconds": 8,
            "source_reliability": "high",
        },
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["adjusted_probability"] > data["baseline_probability"]
    assert data["signal"]["action"] == "BUY"


@pytest.mark.asyncio
async def test_strategy_election_live_count_blocks_low_reporting(client: AsyncClient, user_token: str):
    payload = quote_payload()
    payload["market_slug"] = "senate-state-winner"

    resp = await client.post(
        "/api/strategy/election-live-count",
        json={
            "quote": payload,
            "yes_side": "Candidate A",
            "baseline_probability": 0.51,
            "reporting_pct": 0.02,
            "reported_margin_pct": 0.06,
            "expected_margin_pct": 0.01,
            "feed_latency_seconds": 8,
            "source_reliability": "high",
        },
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    assert resp.json()["signal"]["action"] == "WATCH"


@pytest.mark.asyncio
async def test_strategy_paper_signal(client: AsyncClient, user_token: str):
    resp = await client.post(
        "/api/strategy/paper-signal",
        json={
            "strategy_name": "sports_in_play_v1",
            "quote": quote_payload(),
            "fair_probability": 0.60,
            "action": "BUY",
            "edge": 0.09,
            "confidence": 0.86,
            "reason": "fair probability exceeds entry price",
            "live_state": {
                "slug": "nba-game",
                "live": True,
                "ended": False,
                "home_score": 80,
                "away_score": 75,
            },
        },
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_type"] == "paper_signal"
    assert data["signal"]["action"] == "BUY"
    assert data["signal"]["live_state"]["home_score"] == 80


@pytest.mark.asyncio
async def test_strategy_list_paper_signals(client: AsyncClient, user_token: str):
    created = await client.post(
        "/api/strategy/paper-signal",
        json={
            "strategy_name": "sports_in_play_v1",
            "quote": quote_payload(),
            "fair_probability": 0.60,
            "action": "BUY",
            "edge": 0.09,
            "confidence": 0.86,
            "reason": "fair probability exceeds entry price",
        },
        headers=auth(user_token),
    )
    assert created.status_code == 200

    resp = await client.get("/api/strategy/paper-signals", headers=auth(user_token))

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(item["signal"]["strategy_name"] == "sports_in_play_v1" for item in items)


@pytest.mark.asyncio
async def test_strategy_paper_evaluate(client: AsyncClient, user_token: str):
    created = await client.post(
        "/api/strategy/paper-signal",
        json={
            "strategy_name": "sports_in_play_v1",
            "quote": quote_payload(),
            "fair_probability": 0.60,
            "action": "BUY",
            "edge": 0.09,
            "confidence": 0.86,
            "reason": "fair probability exceeds entry price",
        },
        headers=auth(user_token),
    )
    assert created.status_code == 200

    current = quote_payload()
    current["best_bid"] = 0.62
    current["best_ask"] = 0.64
    current["yes_price"] = 0.64
    resp = await client.post(
        "/api/strategy/paper-evaluate",
        json={"signal": created.json()["signal"], "current_quote": current},
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "open"
    assert data["entry_price"] == 0.51
    assert data["mark_price"] == 0.62
    assert data["pnl"] == 0.11


@pytest.mark.asyncio
async def test_strategy_paper_evaluate_rejects_mismatched_quote(client: AsyncClient, user_token: str):
    created = await client.post(
        "/api/strategy/paper-signal",
        json={
            "strategy_name": "sports_in_play_v1",
            "quote": quote_payload(),
            "fair_probability": 0.60,
            "action": "BUY",
            "edge": 0.09,
            "confidence": 0.86,
            "reason": "fair probability exceeds entry price",
        },
        headers=auth(user_token),
    )
    assert created.status_code == 200

    current = quote_payload()
    current["market_slug"] = "other-game"
    resp = await client.post(
        "/api/strategy/paper-evaluate",
        json={"signal": created.json()["signal"], "current_quote": current},
        headers=auth(user_token),
    )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_strategy_discipline_keeps_initial_signal_when_reversal_is_weak(client: AsyncClient, user_token: str):
    created = await client.post(
        "/api/strategy/paper-signal",
        json={
            "strategy_name": "sports_in_play_v1",
            "quote": quote_payload(),
            "fair_probability": 0.60,
            "action": "BUY",
            "edge": 0.09,
            "confidence": 0.86,
            "reason": "fair probability exceeds entry price",
        },
        headers=auth(user_token),
    )
    assert created.status_code == 200

    current = quote_payload()
    current["best_bid"] = 0.62
    current["best_ask"] = 0.64
    current["yes_price"] = 0.64
    resp = await client.post(
        "/api/strategy/discipline",
        json={
            "initial_signal": created.json()["signal"],
            "current_quote": current,
            "candidate_signal": {
                "action": "SELL",
                "edge": 0.07,
                "confidence": 0.7,
                "reason": "small live reversal",
            },
            "thesis_still_valid": True,
            "churn_count": 1,
        },
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "KEEP_INITIAL"
    assert data["recommended_signal_action"] == "BUY"
    assert data["switch_hurdle"] > data["candidate_edge"]


@pytest.mark.asyncio
async def test_strategy_discipline_allows_exit_when_thesis_invalid(client: AsyncClient, user_token: str):
    created = await client.post(
        "/api/strategy/paper-signal",
        json={
            "strategy_name": "sports_in_play_v1",
            "quote": quote_payload(),
            "fair_probability": 0.60,
            "action": "BUY",
            "edge": 0.09,
            "confidence": 0.86,
            "reason": "fair probability exceeds entry price",
        },
        headers=auth(user_token),
    )
    assert created.status_code == 200

    resp = await client.post(
        "/api/strategy/discipline",
        json={
            "initial_signal": created.json()["signal"],
            "current_quote": quote_payload(),
            "candidate_signal": {
                "action": "SELL",
                "edge": 0.02,
                "confidence": 0.6,
                "reason": "thesis invalidated",
            },
            "thesis_still_valid": False,
        },
        headers=auth(user_token),
    )

    assert resp.status_code == 200
    assert resp.json()["action"] == "ALLOW_EXIT"
