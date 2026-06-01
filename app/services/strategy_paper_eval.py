from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.services.sports_quotes import QuoteSnapshot
    from app.services.strategy_paper import PaperStrategySignal


@dataclass(frozen=True)
class PaperEvaluation:
    status: Literal["open", "resolved", "not_entered"]
    action: str
    market_slug: str
    token_id: str
    entry_price: float | None
    mark_price: float | None
    pnl: float
    pnl_pct: float | None
    reason: str


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _entry_price(signal: PaperStrategySignal) -> float | None:
    if signal.action == "BUY":
        return _float_or_none(signal.quote.get("best_ask")) or _float_or_none(signal.quote.get("yes_price"))
    if signal.action == "SELL":
        return _float_or_none(signal.quote.get("best_bid")) or _float_or_none(signal.quote.get("yes_price"))
    return None


def _open_mark_price(signal: PaperStrategySignal, current_quote: QuoteSnapshot) -> float:
    if signal.action == "BUY":
        return current_quote.best_bid if current_quote.best_bid is not None else current_quote.yes_price
    if signal.action == "SELL":
        return current_quote.best_ask if current_quote.best_ask is not None else current_quote.yes_price
    return current_quote.yes_price


def _pnl_pct(pnl: float, entry_price: float | None) -> float | None:
    if entry_price is None or entry_price <= 0:
        return None
    return round(pnl / entry_price, 6)


def evaluate_paper_signal(
    signal: PaperStrategySignal,
    current_quote: QuoteSnapshot,
    *,
    resolved_yes: bool | None = None,
) -> PaperEvaluation:
    if signal.market_slug != current_quote.market_slug or signal.token_id != current_quote.token_id:
        raise ValueError("current quote does not match paper signal market/token")

    if signal.action not in {"BUY", "SELL"}:
        return PaperEvaluation(
            status="not_entered",
            action=signal.action,
            market_slug=signal.market_slug,
            token_id=signal.token_id,
            entry_price=None,
            mark_price=None,
            pnl=0.0,
            pnl_pct=None,
            reason="paper signal did not create a simulated entry",
        )

    entry = _entry_price(signal)
    if entry is None:
        raise ValueError("paper signal has no usable entry price")

    if resolved_yes is None:
        mark = _open_mark_price(signal, current_quote)
        status: Literal["open", "resolved"] = "open"
        reason = "mark-to-market against current quote"
    else:
        mark = 1.0 if resolved_yes else 0.0
        status = "resolved"
        reason = "resolved against final YES outcome"

    pnl = mark - entry if signal.action == "BUY" else entry - mark
    pnl = round(pnl, 6)
    return PaperEvaluation(
        status=status,
        action=signal.action,
        market_slug=signal.market_slug,
        token_id=signal.token_id,
        entry_price=entry,
        mark_price=mark,
        pnl=pnl,
        pnl_pct=_pnl_pct(pnl, entry),
        reason=reason,
    )
