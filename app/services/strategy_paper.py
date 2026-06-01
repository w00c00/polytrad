from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.models import ScanResult

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.sports_live import SportsLiveState
    from app.services.sports_quotes import QuoteSnapshot
    from app.services.sports_strategy import StrategySignal


@dataclass(frozen=True)
class PaperStrategySignal:
    strategy_name: str
    market_slug: str
    token_id: str
    fair_probability: float
    action: str
    edge: float
    confidence: float
    reason: str
    quote: dict
    live_state: dict | None
    created_at: str


def build_paper_signal(
    *,
    strategy_name: str,
    quote: QuoteSnapshot,
    signal: StrategySignal,
    fair_probability: float,
    live_state: SportsLiveState | None = None,
    created_at: datetime | None = None,
) -> PaperStrategySignal:
    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return PaperStrategySignal(
        strategy_name=strategy_name,
        market_slug=quote.market_slug,
        token_id=quote.token_id,
        fair_probability=fair_probability,
        action=str(signal.action),
        edge=round(signal.edge, 6),
        confidence=round(signal.confidence, 6),
        reason=signal.reason,
        quote=asdict(quote),
        live_state=asdict(live_state) if live_state else None,
        created_at=timestamp.astimezone(timezone.utc).isoformat(),
    )


def paper_signal_to_json(signal: PaperStrategySignal) -> str:
    return json.dumps(asdict(signal), ensure_ascii=False, default=str)


def paper_signal_from_dict(payload: Mapping[str, Any]) -> PaperStrategySignal:
    try:
        quote = payload["quote"]
    except KeyError as e:
        raise ValueError("paper signal is missing quote") from e

    if not isinstance(quote, dict):
        raise ValueError("paper signal quote must be an object")

    live_state = payload.get("live_state")
    if live_state is not None and not isinstance(live_state, dict):
        raise ValueError("paper signal live_state must be an object or null")

    try:
        return PaperStrategySignal(
            strategy_name=str(payload["strategy_name"]),
            market_slug=str(payload["market_slug"]),
            token_id=str(payload["token_id"]),
            fair_probability=float(payload["fair_probability"]),
            action=str(payload["action"]),
            edge=float(payload["edge"]),
            confidence=float(payload["confidence"]),
            reason=str(payload["reason"]),
            quote=quote,
            live_state=live_state,
            created_at=str(payload["created_at"]),
        )
    except KeyError as e:
        raise ValueError(f"paper signal is missing {e.args[0]}") from e
    except (TypeError, ValueError) as e:
        raise ValueError("paper signal contains invalid field types") from e


def paper_signal_from_json(payload: str) -> PaperStrategySignal:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ValueError("paper signal JSON is invalid") from e
    if not isinstance(raw, dict):
        raise ValueError("paper signal JSON must be an object")
    return paper_signal_from_dict(raw)


async def persist_paper_signal(db: AsyncSession, signal: PaperStrategySignal) -> ScanResult:
    record = ScanResult(scan_type="paper_signal", market_data=paper_signal_to_json(signal))
    db.add(record)
    await db.commit()
    return record
