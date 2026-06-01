from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient, MockTransport, Request, Response

from app.services.sports_live import SportsLiveState
from app.services.sports_live_feeds import (
    JsonLiveFeedConfig,
    JsonSportsLiveFeedAdapter,
    LiveTextEvent,
    apply_live_text_event,
    build_live_feed_snapshot,
    normalize_live_text_event,
    recent_live_text_events,
)


def test_normalize_live_text_event_supports_common_provider_keys():
    event = normalize_live_text_event(
        {
            "event_slug": "nba-game",
            "type": "three_pointer",
            "text": "Home guard makes 3-pt shot",
            "timestamp": "2026-01-01T00:01:02Z",
            "quarter": "Q4",
            "clock": "01:12",
            "team": "home",
            "home_score": "101",
            "away_score": "99",
            "importance": "0.8",
            "id": "evt-1",
        },
        source="provider",
    )

    assert event.slug == "nba-game"
    assert event.event_type == "three_pointer"
    assert event.description == "Home guard makes 3-pt shot"
    assert event.period == "Q4"
    assert event.elapsed == "01:12"
    assert event.home_score == 101
    assert event.away_score == 99
    assert event.importance == 0.8
    assert event.provider_event_id == "evt-1"
    assert event.occurred_at == datetime(2026, 1, 1, 0, 1, 2, tzinfo=timezone.utc)


def test_apply_live_text_event_updates_score_clock_without_mutating_state():
    state = SportsLiveState("nba-game", live=True, ended=False, home_score=98, away_score=99, period="Q4", elapsed="02:01")
    event = LiveTextEvent(
        slug="nba-game",
        event_type="score",
        description="home scores",
        source="provider",
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        period="Q4",
        elapsed="01:12",
        home_score=101,
        away_score=99,
    )

    updated = apply_live_text_event(state, event)

    assert state.home_score == 98
    assert updated.home_score == 101
    assert updated.away_score == 99
    assert updated.elapsed == "01:12"
    assert updated.last_update == event.occurred_at
    assert updated.source == "provider"


def test_recent_live_text_events_filters_old_and_undated_events():
    now = datetime.now(timezone.utc)
    fresh = LiveTextEvent(
        slug="nba-game",
        event_type="score",
        description="fresh",
        source="provider",
        occurred_at=now - timedelta(seconds=20),
    )
    old = LiveTextEvent(
        slug="nba-game",
        event_type="score",
        description="old",
        source="provider",
        occurred_at=now - timedelta(seconds=120),
    )
    undated = LiveTextEvent("nba-game", "update", "no timestamp", "provider")

    assert recent_live_text_events([fresh, old, undated], now=now, max_age_seconds=90) == (fresh,)


@pytest.mark.asyncio
async def test_build_live_feed_snapshot_applies_events_in_adapter_order():
    now = datetime.now(timezone.utc)

    class FakeAdapter:
        source = "fake-live-text"

        async def fetch_state(self, event_id):
            assert event_id == "provider-game-id"
            return SportsLiveState("nba-game", live=True, ended=False, home_score=10, away_score=10)

        async def fetch_events(self, event_id, since=None):
            assert event_id == "provider-game-id"
            assert since is None
            return [
                LiveTextEvent(
                    slug="nba-game",
                    event_type="score",
                    description="away scores",
                    source=self.source,
                    occurred_at=now - timedelta(seconds=4),
                    period="Q1",
                    elapsed="09:30",
                    home_score=10,
                    away_score=12,
                ),
                LiveTextEvent(
                    slug="nba-game",
                    event_type="score",
                    description="home scores",
                    source=self.source,
                    occurred_at=now - timedelta(seconds=1),
                    period="Q1",
                    elapsed="09:10",
                    home_score=13,
                    away_score=12,
                ),
            ]

    snapshot = await build_live_feed_snapshot(FakeAdapter(), event_id="provider-game-id")

    assert snapshot.source == "fake-live-text"
    assert snapshot.state.home_score == 13
    assert snapshot.state.away_score == 12
    assert snapshot.state.elapsed == "09:10"
    assert snapshot.provider_latency_seconds is not None
    assert len(snapshot.events) == 2


@pytest.mark.asyncio
async def test_json_sports_live_feed_adapter_fetches_state_and_events():
    async def handler(request: Request) -> Response:
        if request.url.path.endswith("/state/game-1"):
            return Response(
                200,
                json={
                    "data": {
                        "event_slug": "nba-game",
                        "status": "live",
                        "home_score": "80",
                        "away_score": "75",
                        "quarter": "Q3",
                        "clock": "04:12",
                        "updated_at": "2026-01-01T00:01:02Z",
                    }
                },
            )
        if request.url.path.endswith("/events/game-1"):
            assert request.url.params["since"] == "2026-01-01T00:00:00+00:00"
            return Response(
                200,
                json={
                    "data": {
                        "items": [
                            {
                                "event_slug": "nba-game",
                                "type": "score",
                                "text": "home scores",
                                "timestamp": "2026-01-01T00:01:05Z",
                                "home_score": 82,
                                "away_score": 75,
                            }
                        ]
                    }
                },
            )
        return Response(404)

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport, base_url="https://example.test") as client:
        adapter = JsonSportsLiveFeedAdapter(
            JsonLiveFeedConfig(
                source="json-provider",
                state_url_template="https://example.test/state/{event_id}",
                events_url_template="https://example.test/events/{event_id}?since={since}",
                state_path=("data",),
                events_path=("data", "items"),
            ),
            client=client,
        )

        state = await adapter.fetch_state("game-1")
        events = await adapter.fetch_events("game-1", since=datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert state.slug == "nba-game"
    assert state.live is True
    assert state.ended is False
    assert state.home_score == 80
    assert state.period == "Q3"
    assert events[0].description == "home scores"
    assert events[0].home_score == 82


@pytest.mark.asyncio
async def test_json_sports_live_feed_adapter_rejects_bad_event_shape():
    async def handler(request: Request) -> Response:
        return Response(200, json={"events": {"not": "a-list"}})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport, base_url="https://example.test") as client:
        adapter = JsonSportsLiveFeedAdapter(
            JsonLiveFeedConfig(
                source="json-provider",
                state_url_template="https://example.test/state/{event_id}",
                events_url_template="https://example.test/events/{event_id}",
            ),
            client=client,
        )

        with pytest.raises(ValueError, match="events payload"):
            await adapter.fetch_events("game-1")
