from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import get_db
from app.deps import get_current_user
from app.models import ScanResult
from app.services.election_strategy import ElectionCountState, evaluate_election_live_count
from app.services.sports_live import SportsLiveState
from app.services.sports_quotes import QuoteSnapshot, fetch_quote_snapshot
from app.services.sports_strategy import (
    MarketQuote,
    StrategyAction,
    StrategySignal,
    evaluate_championship_entry,
    evaluate_in_play_trade,
)
from app.services.strategy_core import CatalystReliability, score_event_driven_domain
from app.services.strategy_discipline import evaluate_signal_discipline
from app.services.strategy_domains import list_domain_candidates
from app.services.strategy_paper import (
    build_paper_signal,
    paper_signal_from_dict,
    paper_signal_from_json,
    persist_paper_signal,
)
from app.services.strategy_paper_eval import evaluate_paper_signal
from app.services.strategy_registry import list_strategy_modules
from app.services.world_cup_strategy import classify_world_cup_market, list_world_cup_market_tags

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import User

router = APIRouter(prefix="/api/strategy", tags=["策略观察"])


class DomainFitReq(BaseModel):
    domain: str
    has_realtime_feed: bool
    feed_latency_seconds: float | None = None
    has_liquid_polymarket_markets: bool
    catalyst_reliability: Literal["high", "medium", "low"]
    market_reacts_gradually: bool
    objective_resolution: bool


class QuoteSnapshotReq(BaseModel):
    market_slug: str
    token_id: str
    fallback_yes_price: float = Field(ge=0, le=1)


class StrategyQuoteReq(BaseModel):
    market_slug: str
    token_id: str
    yes_price: float = Field(ge=0, le=1)
    best_bid: float | None = Field(default=None, ge=0, le=1)
    best_ask: float | None = Field(default=None, ge=0, le=1)
    spread: float | None = Field(default=None, ge=0)
    liquidity: float = Field(default=0, ge=0)
    volume_24h: float = Field(default=0, ge=0)


class InPlaySignalReq(BaseModel):
    quote: StrategyQuoteReq
    fair_probability: float = Field(ge=0, le=1)
    min_edge: float = Field(default=0.05, ge=0, le=1)
    max_spread: float = Field(default=0.08, ge=0, le=1)
    min_liquidity: float = Field(default=100, ge=0)


class ChampionshipSignalReq(BaseModel):
    quote: StrategyQuoteReq
    fair_probability: float = Field(ge=0, le=1)
    launch_age_hours: float = Field(ge=0)
    schedule_catalyst_score: float = Field(ge=0, le=1)
    min_edge: float = Field(default=0.06, ge=0, le=1)
    max_launch_age_hours: float = Field(default=72, ge=0)
    max_entry_price: float = Field(default=0.35, ge=0, le=1)


class ElectionLiveCountReq(BaseModel):
    quote: StrategyQuoteReq
    yes_side: str
    baseline_probability: float = Field(ge=0, le=1)
    reporting_pct: float = Field(ge=0, le=1)
    reported_margin_pct: float = Field(ge=-1, le=1)
    expected_margin_pct: float = Field(ge=-1, le=1)
    feed_latency_seconds: float | None = Field(default=None, ge=0)
    source_reliability: Literal["high", "medium", "low"] = "high"
    source: str = "official_count"
    min_reporting_pct: float = Field(default=0.05, ge=0, le=1)
    max_feed_latency_seconds: float = Field(default=60, ge=0)
    min_edge: float = Field(default=0.05, ge=0, le=1)
    max_spread: float = Field(default=0.08, ge=0, le=1)
    min_liquidity: float = Field(default=100, ge=0)


class LiveStateReq(BaseModel):
    slug: str
    live: bool
    ended: bool
    home_score: int | None = None
    away_score: int | None = None
    period: str = ""
    elapsed: str = ""


class PaperSignalReq(BaseModel):
    strategy_name: str
    quote: StrategyQuoteReq
    fair_probability: float = Field(ge=0, le=1)
    action: Literal["BUY", "SELL", "HOLD", "WATCH"]
    edge: float
    confidence: float = Field(ge=0, le=1)
    reason: str
    live_state: LiveStateReq | None = None


class PaperEvaluateReq(BaseModel):
    signal: dict[str, Any]
    current_quote: StrategyQuoteReq
    resolved_yes: bool | None = None


class CandidateSignalReq(BaseModel):
    action: Literal["BUY", "SELL", "HOLD", "WATCH"]
    edge: float
    confidence: float = Field(ge=0, le=1)
    reason: str
    entry_price: float | None = Field(default=None, ge=0, le=1)
    exit_price: float | None = Field(default=None, ge=0, le=1)
    market_slug: str | None = None
    token_id: str | None = None


class DisciplineReq(BaseModel):
    initial_signal: dict[str, Any]
    current_quote: StrategyQuoteReq
    candidate_signal: CandidateSignalReq
    thesis_still_valid: bool = True
    seconds_since_entry: int | None = Field(default=None, ge=0)
    churn_count: int = Field(default=0, ge=0)
    min_hold_seconds: int = Field(default=900, ge=0)
    min_switch_edge: float = Field(default=0.1, ge=0, le=1)
    min_exit_edge: float = Field(default=0.08, ge=0, le=1)
    churn_penalty_step: float = Field(default=0.03, ge=0, le=1)


def _market_quote(req: StrategyQuoteReq) -> MarketQuote:
    return MarketQuote(
        market_slug=req.market_slug,
        token_id=req.token_id,
        yes_price=req.yes_price,
        best_bid=req.best_bid,
        best_ask=req.best_ask,
        spread=req.spread,
        liquidity=req.liquidity,
        volume_24h=req.volume_24h,
    )


def _quote_snapshot(req: StrategyQuoteReq) -> QuoteSnapshot:
    return QuoteSnapshot(
        market_slug=req.market_slug,
        token_id=req.token_id,
        best_bid=req.best_bid,
        best_ask=req.best_ask,
        spread=req.spread,
        liquidity=req.liquidity,
        yes_price=req.yes_price,
    )


def _live_state(req: LiveStateReq | None) -> SportsLiveState | None:
    if req is None:
        return None
    return SportsLiveState(
        slug=req.slug,
        live=req.live,
        ended=req.ended,
        home_score=req.home_score,
        away_score=req.away_score,
        period=req.period,
        elapsed=req.elapsed,
        source="api",
    )


def _signal_payload(signal: StrategySignal) -> dict:
    payload = asdict(signal)
    payload["action"] = str(signal.action)
    return payload


@router.post("/domain-fit")
async def domain_fit(req: DomainFitReq, user: User = Depends(get_current_user)):
    fit = score_event_driven_domain(
        domain=req.domain,
        has_realtime_feed=req.has_realtime_feed,
        feed_latency_seconds=req.feed_latency_seconds,
        has_liquid_polymarket_markets=req.has_liquid_polymarket_markets,
        catalyst_reliability=CatalystReliability(req.catalyst_reliability),
        market_reacts_gradually=req.market_reacts_gradually,
        objective_resolution=req.objective_resolution,
    )
    return asdict(fit)


@router.get("/modules")
async def strategy_modules(user: User = Depends(get_current_user)):
    return {"items": [asdict(module) for module in list_strategy_modules()]}


@router.get("/domain-candidates")
async def domain_candidates(user: User = Depends(get_current_user)):
    return {"items": [asdict(candidate) for candidate in list_domain_candidates()]}


@router.get("/world-cup-tags")
async def world_cup_tags(market_title: str | None = None, user: User = Depends(get_current_user)):
    tags = classify_world_cup_market(market_title) if market_title else list_world_cup_market_tags()
    return {"items": [asdict(tag) for tag in tags]}


@router.post("/quote-snapshot")
async def quote_snapshot(req: QuoteSnapshotReq, user: User = Depends(get_current_user)):
    snapshot = await fetch_quote_snapshot(
        market_slug=req.market_slug,
        token_id=req.token_id,
        fallback_yes_price=req.fallback_yes_price,
    )
    return asdict(snapshot)


@router.post("/in-play")
async def in_play_signal(req: InPlaySignalReq, user: User = Depends(get_current_user)):
    signal = evaluate_in_play_trade(
        _market_quote(req.quote),
        req.fair_probability,
        min_edge=req.min_edge,
        max_spread=req.max_spread,
        min_liquidity=req.min_liquidity,
    )
    return _signal_payload(signal)


@router.post("/championship")
async def championship_signal(req: ChampionshipSignalReq, user: User = Depends(get_current_user)):
    signal = evaluate_championship_entry(
        _market_quote(req.quote),
        req.fair_probability,
        launch_age_hours=req.launch_age_hours,
        schedule_catalyst_score=req.schedule_catalyst_score,
        min_edge=req.min_edge,
        max_launch_age_hours=req.max_launch_age_hours,
        max_entry_price=req.max_entry_price,
    )
    return _signal_payload(signal)


@router.post("/election-live-count")
async def election_live_count_signal(req: ElectionLiveCountReq, user: User = Depends(get_current_user)):
    try:
        signal = evaluate_election_live_count(
            _market_quote(req.quote),
            ElectionCountState(
                market_slug=req.quote.market_slug,
                yes_side=req.yes_side,
                reporting_pct=req.reporting_pct,
                reported_margin_pct=req.reported_margin_pct,
                expected_margin_pct=req.expected_margin_pct,
                feed_latency_seconds=req.feed_latency_seconds,
                source_reliability=CatalystReliability(req.source_reliability),
                source=req.source,
            ),
            baseline_probability=req.baseline_probability,
            min_reporting_pct=req.min_reporting_pct,
            max_feed_latency_seconds=req.max_feed_latency_seconds,
            min_edge=req.min_edge,
            max_spread=req.max_spread,
            min_liquidity=req.min_liquidity,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    payload = asdict(signal)
    payload["signal"] = _signal_payload(signal.signal)
    return payload


@router.post("/paper-signal")
async def paper_signal(
    req: PaperSignalReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    signal = StrategySignal(
        action=StrategyAction(req.action),
        edge=req.edge,
        confidence=req.confidence,
        reason=req.reason,
    )
    paper = build_paper_signal(
        strategy_name=req.strategy_name,
        quote=_quote_snapshot(req.quote),
        signal=signal,
        fair_probability=req.fair_probability,
        live_state=_live_state(req.live_state),
    )
    record = await persist_paper_signal(db, paper)
    return {"id": record.id, "scan_type": record.scan_type, "signal": asdict(paper)}


@router.get("/paper-signals")
async def list_paper_signals(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScanResult)
        .where(ScanResult.scan_type == "paper_signal")
        .order_by(ScanResult.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    items = []
    for record in records:
        try:
            signal = paper_signal_from_json(record.market_data)
        except ValueError:
            continue
        items.append(
            {
                "id": record.id,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "signal": asdict(signal),
            }
        )
    return {"items": items}


@router.post("/paper-evaluate")
async def paper_evaluate(req: PaperEvaluateReq, user: User = Depends(get_current_user)):
    try:
        signal = paper_signal_from_dict(req.signal)
        evaluation = evaluate_paper_signal(
            signal,
            _quote_snapshot(req.current_quote),
            resolved_yes=req.resolved_yes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return asdict(evaluation)


@router.post("/discipline")
async def signal_discipline(req: DisciplineReq, user: User = Depends(get_current_user)):
    try:
        initial = paper_signal_from_dict(req.initial_signal)
        current_evaluation = evaluate_paper_signal(initial, _quote_snapshot(req.current_quote))
        candidate = StrategySignal(
            action=StrategyAction(req.candidate_signal.action),
            edge=req.candidate_signal.edge,
            confidence=req.candidate_signal.confidence,
            reason=req.candidate_signal.reason,
            entry_price=req.candidate_signal.entry_price,
            exit_price=req.candidate_signal.exit_price,
        )
        decision = evaluate_signal_discipline(
            initial_signal=initial,
            current_evaluation=current_evaluation,
            candidate_signal=candidate,
            candidate_market_slug=req.candidate_signal.market_slug,
            candidate_token_id=req.candidate_signal.token_id,
            thesis_still_valid=req.thesis_still_valid,
            seconds_since_entry=req.seconds_since_entry,
            churn_count=req.churn_count,
            min_hold_seconds=req.min_hold_seconds,
            min_switch_edge=req.min_switch_edge,
            min_exit_edge=req.min_exit_edge,
            churn_penalty_step=req.churn_penalty_step,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    payload = asdict(decision)
    payload["action"] = str(decision.action)
    return payload
