from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import quote

import httpx

from app.services.sports_live import SportsLiveState

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class LiveTextEvent:
    slug: str
    event_type: str
    description: str
    source: str
    occurred_at: datetime | None = None
    period: str = ""
    elapsed: str = ""
    team: str = ""
    home_score: int | None = None
    away_score: int | None = None
    importance: float = 0.0
    provider_event_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LiveFeedSnapshot:
    state: SportsLiveState
    events: tuple[LiveTextEvent, ...]
    source: str
    provider_latency_seconds: float | None = None


@dataclass(frozen=True)
class JsonLiveFeedConfig:
    source: str
    state_url_template: str
    events_url_template: str
    state_path: tuple[str, ...] = ()
    events_path: tuple[str, ...] = ("events",)
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 8.0


class SportsLiveFeedAdapter(Protocol):
    source: str

    async def fetch_state(self, event_id: str) -> SportsLiveState:
        """Fetch current score/clock state for one provider event id."""

    async def fetch_events(self, event_id: str, since: datetime | None = None) -> Sequence[LiveTextEvent]:
        """Fetch normalized play-by-play events after an optional timestamp."""


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_zero(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def _bool_from_provider(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "live", "in_progress"}
    return bool(value)


def _ended_from_provider(value: object, *, default: bool = False) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ended", "final", "complete"}
    return _bool_from_provider(value, default=default)


def _extract_path(payload: object, path: Iterable[str]) -> object:
    current = payload
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _url_from_template(template: str, *, event_id: str, since: datetime | None = None) -> str:
    since_value = quote(since.astimezone(timezone.utc).isoformat(), safe="") if since else ""
    return template.format(event_id=event_id, since=since_value)


def normalize_live_text_event(payload: Mapping[str, Any], *, source: str, default_slug: str = "") -> LiveTextEvent:
    """Normalize one provider play-by-play item into the strategy event shape."""

    occurred_at = _parse_timestamp(payload.get("occurred_at") or payload.get("timestamp") or payload.get("time"))
    return LiveTextEvent(
        slug=str(payload.get("slug") or payload.get("event_slug") or default_slug),
        event_type=str(payload.get("event_type") or payload.get("type") or payload.get("kind") or "update"),
        description=str(payload.get("description") or payload.get("text") or payload.get("message") or ""),
        source=source,
        occurred_at=occurred_at,
        period=str(payload.get("period") or payload.get("quarter") or payload.get("half") or ""),
        elapsed=str(payload.get("elapsed") or payload.get("clock") or payload.get("game_clock") or ""),
        team=str(payload.get("team") or payload.get("side") or ""),
        home_score=_int_or_none(payload.get("home_score")),
        away_score=_int_or_none(payload.get("away_score")),
        importance=_float_or_zero(payload.get("importance")),
        provider_event_id=str(payload.get("provider_event_id") or payload.get("id") or ""),
        payload=dict(payload),
    )


class JsonSportsLiveFeedAdapter:
    def __init__(self, config: JsonLiveFeedConfig, client: httpx.AsyncClient | None = None):
        self.config = config
        self.source = config.source
        self._client = client

    async def _get_json(self, url: str) -> object:
        if self._client is not None:
            response = await self._client.get(url, headers=self.config.headers)
            response.raise_for_status()
            return response.json()

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.get(url, headers=self.config.headers)
            response.raise_for_status()
            return response.json()

    async def fetch_state(self, event_id: str) -> SportsLiveState:
        payload = await self._get_json(_url_from_template(self.config.state_url_template, event_id=event_id))
        raw = _extract_path(payload, self.config.state_path)
        if not isinstance(raw, Mapping):
            raise ValueError("live feed state payload must be an object")

        return SportsLiveState(
            slug=str(raw.get("slug") or raw.get("event_slug") or event_id),
            live=_bool_from_provider(raw.get("live") or raw.get("status"), default=True),
            ended=_ended_from_provider(raw.get("ended") or raw.get("final") or raw.get("status"), default=False),
            home_score=_int_or_none(raw.get("home_score")),
            away_score=_int_or_none(raw.get("away_score")),
            period=str(raw.get("period") or raw.get("quarter") or raw.get("half") or ""),
            elapsed=str(raw.get("elapsed") or raw.get("clock") or raw.get("game_clock") or ""),
            last_update=_parse_timestamp(raw.get("last_update") or raw.get("updated_at") or raw.get("timestamp")),
            source=self.source,
        )

    async def fetch_events(self, event_id: str, since: datetime | None = None) -> Sequence[LiveTextEvent]:
        payload = await self._get_json(_url_from_template(self.config.events_url_template, event_id=event_id, since=since))
        raw_events = _extract_path(payload, self.config.events_path)
        if not isinstance(raw_events, Sequence) or isinstance(raw_events, (str, bytes)):
            raise ValueError("live feed events payload must be a list")

        events = []
        for raw in raw_events:
            if not isinstance(raw, Mapping):
                continue
            events.append(normalize_live_text_event(raw, source=self.source, default_slug=event_id))
        return tuple(events)


def apply_live_text_event(state: SportsLiveState, event: LiveTextEvent) -> SportsLiveState:
    """Return updated score/clock state without mutating the previous state."""

    return SportsLiveState(
        slug=event.slug or state.slug,
        live=state.live,
        ended=state.ended,
        home_score=event.home_score if event.home_score is not None else state.home_score,
        away_score=event.away_score if event.away_score is not None else state.away_score,
        period=event.period or state.period,
        elapsed=event.elapsed or state.elapsed,
        last_update=event.occurred_at or state.last_update,
        source=event.source or state.source,
    )


def recent_live_text_events(
    events: Sequence[LiveTextEvent],
    *,
    now: datetime,
    max_age_seconds: int = 90,
) -> tuple[LiveTextEvent, ...]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    normalized_now = now.astimezone(timezone.utc)
    recent = []
    for event in events:
        if event.occurred_at is None:
            continue
        age = normalized_now - event.occurred_at.astimezone(timezone.utc)
        if age.total_seconds() <= max_age_seconds:
            recent.append(event)
    return tuple(recent)


async def build_live_feed_snapshot(
    adapter: SportsLiveFeedAdapter,
    *,
    event_id: str,
    since: datetime | None = None,
) -> LiveFeedSnapshot:
    state = await adapter.fetch_state(event_id)
    events = tuple(await adapter.fetch_events(event_id, since=since))
    latest = state
    for event in events:
        latest = apply_live_text_event(latest, event)

    latency = None
    if latest.last_update is not None:
        latency = max((datetime.now(timezone.utc) - latest.last_update.astimezone(timezone.utc)).total_seconds(), 0.0)

    return LiveFeedSnapshot(
        state=latest,
        events=events,
        source=adapter.source,
        provider_latency_seconds=latency,
    )
