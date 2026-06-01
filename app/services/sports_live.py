from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SportsLiveState:
    """Normalized live sports state from Polymarket or an external feed."""

    slug: str
    live: bool
    ended: bool
    home_score: int | None = None
    away_score: int | None = None
    period: str = ""
    elapsed: str = ""
    last_update: datetime | None = None
    source: str = "polymarket"

    @property
    def score_diff(self) -> int | None:
        if self.home_score is None or self.away_score is None:
            return None
        return self.home_score - self.away_score


def _parse_score(score: str | None) -> tuple[int | None, int | None]:
    if not score or "-" not in score:
        return None, None
    left, right = score.split("-", 1)
    try:
        return int(left.strip()), int(right.strip())
    except ValueError:
        return None, None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_polymarket_sport_result(payload: dict) -> SportsLiveState:
    """Convert a Polymarket sports websocket message into local state."""

    home_score, away_score = _parse_score(payload.get("score"))
    return SportsLiveState(
        slug=str(payload.get("slug") or ""),
        live=bool(payload.get("live")),
        ended=bool(payload.get("ended")),
        home_score=home_score,
        away_score=away_score,
        period=str(payload.get("period") or ""),
        elapsed=str(payload.get("elapsed") or ""),
        last_update=_parse_timestamp(payload.get("last_update")),
        source="polymarket",
    )


def is_stale(state: SportsLiveState, now: datetime, max_age_seconds: int = 90) -> bool:
    if state.last_update is None:
        return True
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age = now.astimezone(timezone.utc) - state.last_update.astimezone(timezone.utc)
    return age.total_seconds() > max_age_seconds
