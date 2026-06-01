from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Credential, Trade, User
from app.services.polymarket import clob_api, data_api, to_beijing_time, translate_title


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            if ts > 10_000_000_000:
                ts = ts / 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, ValueError):
            return None
    text = str(value)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _position_token(position: dict) -> str:
    return str(
        position.get("asset")
        or position.get("token_id")
        or position.get("tokenId")
        or position.get("clobTokenId")
        or ""
    )


def _position_title(position: dict) -> str:
    return str(position.get("title_zh") or translate_title(position.get("title") or position.get("question") or "未知市场"))


def _position_value(position: dict) -> float:
    return _num(position.get("currentValue") or position.get("value"))


def _position_size(position: dict) -> float:
    return _num(position.get("size") or position.get("shares"))


def _position_price(position: dict) -> float:
    size = _position_size(position)
    value = _position_value(position)
    if size > 0 and value > 0:
        return value / size
    return _num(position.get("curPrice") or position.get("currentPrice") or position.get("price") or position.get("avgPrice"))


def _topic_key(title: str) -> str:
    text = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", " ", title).strip().lower()
    parts = text.split()
    return " ".join(parts[:6]) if parts else title[:20]


def _book_levels(book: dict, side: str) -> list[tuple[float, float]]:
    raw = book.get("bids" if side == "SELL" else "asks", [])
    levels: list[tuple[float, float]] = []
    for level in raw:
        price = level.get("price") if isinstance(level, dict) else getattr(level, "price", None)
        size = level.get("size") if isinstance(level, dict) else getattr(level, "size", None)
        p = _num(price)
        s = _num(size)
        if 0 < p < 1 and s > 0:
            levels.append((p, s))
    levels.sort(key=lambda x: x[0], reverse=(side == "SELL"))
    return levels


def _sell_depth_from_levels(levels: list[tuple[float, float]], target_size: float) -> dict:
    remaining = target_size
    filled = 0.0
    value = 0.0
    worst_bid = 0.0
    levels_used = 0
    for price, available in levels:
        if remaining <= 1e-9:
            break
        take = min(available, remaining)
        if take <= 1e-9:
            continue
        filled += take
        value += take * price
        remaining -= take
        worst_bid = price
        levels_used += 1
    return {
        "sellable_shares": round(filled, 4),
        "sellable_value": round(value, 4),
        "avg_exit_price": round(value / filled, 4) if filled else 0.0,
        "best_bid": round(levels[0][0], 4) if levels else 0.0,
        "worst_bid": round(worst_bid, 4),
        "missing_shares": round(max(remaining, 0.0), 4),
        "levels_used": levels_used,
        "fillable": remaining <= max(0.001, target_size * 0.001),
    }


async def _active_wallet(user: User, db: AsyncSession) -> tuple[Credential, str]:
    result = await db.execute(select(Credential).where(Credential.user_id == user.id, Credential.is_active == True))
    cred = result.scalar_one_or_none()
    if not cred:
        raise ValueError("未配置钱包")
    return cred, cred.funder_address or cred.wallet_address


async def _load_wallet_snapshot(address: str) -> tuple[list[dict], list[dict], Any, list[dict]]:
    positions, closed, value, trades = await asyncio.gather(
        data_api.get_positions(address),
        data_api.get_closed_positions(address),
        data_api.get_value(address),
        data_api.get_trades(address, limit=150),
    )
    return positions or [], closed or [], value, trades or []


def _portfolio_total_value(value_payload: Any, positions: list[dict]) -> float:
    if isinstance(value_payload, list) and value_payload:
        total = _num(value_payload[0].get("value"))
    elif isinstance(value_payload, dict):
        total = _num(value_payload.get("value"))
    else:
        total = 0.0
    if total <= 0:
        total = sum(_position_value(p) for p in positions)
    return total


async def _attach_exit_depth(positions: list[dict], max_positions: int = 40) -> dict[str, dict]:
    sem = asyncio.Semaphore(8)
    depth_map: dict[str, dict] = {}

    async def check(position: dict) -> None:
        token = _position_token(position)
        size = _position_size(position)
        if not token or size <= 0:
            return
        async with sem:
            try:
                book = await clob_api.get_orderbook(token)
                depth_map[token] = _sell_depth_from_levels(_book_levels(book, "SELL"), size)
            except Exception as e:
                depth_map[token] = {"fillable": False, "reason": f"订单簿读取失败: {e}", "best_bid": 0.0, "sellable_value": 0.0}

    by_value = sorted(positions, key=_position_value, reverse=True)[:max_positions]
    await asyncio.gather(*(check(p) for p in by_value))
    return depth_map


def _risk_item(position: dict, total_value: float, depth: dict | None, now: datetime) -> dict:
    title = _position_title(position)
    value = _position_value(position)
    size = _position_size(position)
    pnl = _num(position.get("cashPnl"))
    pnl_pct = _num(position.get("percentPnl"))
    price = _position_price(position)
    end_dt = _parse_dt(position.get("endDate") or position.get("endDateIso"))
    hours_left = (end_dt - now).total_seconds() / 3600 if end_dt else None
    warnings: list[str] = []
    blockers: list[str] = []
    actions: list[str] = []

    share_of_portfolio = value / total_value if total_value > 0 else 0.0
    if share_of_portfolio >= 0.30:
        warnings.append(f"单一持仓占组合 {share_of_portfolio * 100:.1f}%，集中度过高")
        actions.append("考虑分批减仓或设置更低单市场预算")
    elif share_of_portfolio >= 0.15:
        warnings.append(f"单一持仓占组合 {share_of_portfolio * 100:.1f}%，需关注集中风险")

    if hours_left is not None:
        if hours_left < 0:
            warnings.append("市场已过期但持仓仍显示，可能需要赎回或等待结算")
            actions.append("不要继续加仓，检查是否可 redeem")
        elif hours_left <= 6:
            warnings.append(f"距离到期仅 {hours_left:.1f} 小时")
            actions.append("确认是否继续持有到结算")
        elif hours_left <= 24:
            warnings.append(f"24 小时内到期（{hours_left:.1f}h）")

    if pnl_pct <= -35 or pnl <= -50:
        warnings.append(f"浮亏较大：{pnl_pct:.1f}% / ${pnl:.2f}")
        actions.append("复核原始买入理由，避免亏损仓位被动拖到无流动性")
    elif pnl_pct <= -20:
        warnings.append(f"浮亏超过 20%：{pnl_pct:.1f}%")

    if price >= 0.95:
        warnings.append("价格接近 1，继续持有的上行空间有限")
    elif 0 < price <= 0.05:
        warnings.append("价格接近 0，可能已接近归零或等待结算")

    if depth:
        if not depth.get("fillable"):
            warnings.append(depth.get("reason") or "当前买盘不足，无法一次性按 best bid 附近平仓")
            actions.append("如需退出，考虑拆单或等待买盘恢复")
        elif depth.get("best_bid", 0) <= 0:
            warnings.append("没有有效 best bid，退出流动性很差")
        sellable_value = _num(depth.get("sellable_value"))
        if value > 0 and sellable_value > 0 and sellable_value < value * 0.85:
            warnings.append(f"按当前买盘全平约 ${sellable_value:.2f}，低于当前估值较多")

    if position.get("redeemable"):
        actions.append("该仓位可赎回，优先 redeem 回收资金")
    if position.get("redeemed"):
        blockers.append("已赎回仓位，不应继续展示为有效持仓")

    risk_level = "low"
    if blockers:
        risk_level = "critical"
    elif len(warnings) >= 4 or share_of_portfolio >= 0.30:
        risk_level = "high"
    elif len(warnings) >= 2:
        risk_level = "medium"

    return {
        "asset": _position_token(position),
        "title": position.get("title", ""),
        "title_zh": title,
        "outcome": position.get("outcome") or position.get("outcomeLabel") or "",
        "size": round(size, 4),
        "current_value": round(value, 4),
        "price": round(price, 4),
        "cash_pnl": round(pnl, 4),
        "percent_pnl": round(pnl_pct, 2),
        "share_of_portfolio_pct": round(share_of_portfolio * 100, 2),
        "end_date_bj": to_beijing_time(position.get("endDate") or position.get("endDateIso")),
        "hours_left": round(hours_left, 2) if hours_left is not None else None,
        "exit_depth": depth or {},
        "warnings": warnings,
        "blockers": blockers,
        "actions": actions or ["继续观察，保持小额和分散"],
        "risk_level": risk_level,
    }


def _trade_timestamp(item: dict) -> int:
    raw = item.get("timestamp") or item.get("time") or item.get("createdAt") or item.get("created_at")
    ts = _int(raw)
    if ts > 10_000_000_000:
        ts = ts // 1000
    if ts > 0:
        return ts
    dt = _parse_dt(raw)
    return int(dt.timestamp()) if dt else 0


def _recent_trade_summary(trades: list[dict], closed: list[dict], now: datetime) -> dict:
    ts_24h = int((now - timedelta(hours=24)).timestamp())
    ts_7d = int((now - timedelta(days=7)).timestamp())
    trades_24h = [t for t in trades if _trade_timestamp(t) >= ts_24h]
    trades_7d = [t for t in trades if _trade_timestamp(t) >= ts_7d]
    closed_24h = [c for c in closed if _trade_timestamp(c) >= ts_24h]
    closed_7d = [c for c in closed if _trade_timestamp(c) >= ts_7d]
    realized_24h = sum(_num(c.get("realizedPnl")) for c in closed_24h)
    realized_7d = sum(_num(c.get("realizedPnl")) for c in closed_7d)

    buys_24h = sum(1 for t in trades_24h if str(t.get("side", "")).upper() == "BUY")
    sells_24h = sum(1 for t in trades_24h if str(t.get("side", "")).upper() == "SELL")
    largest_loss = min(closed_7d, key=lambda c: _num(c.get("realizedPnl")), default=None)
    largest_win = max(closed_7d, key=lambda c: _num(c.get("realizedPnl")), default=None)

    lessons = []
    if len(trades_24h) >= 20:
        lessons.append("24h 交易次数偏多，注意避免扫描结果驱动的过度交易")
    if realized_7d < 0:
        lessons.append("近 7 天已实现盈亏为负，优先复盘亏损来源再扩大仓位")
    if buys_24h > sells_24h * 3 and buys_24h >= 6:
        lessons.append("24h 买入明显多于卖出，注意资金被长期占用")
    if not lessons:
        lessons.append("最近交易节奏暂无明显异常，继续保持 FOK 与小额分散")

    return {
        "trades_24h": len(trades_24h),
        "trades_7d": len(trades_7d),
        "buys_24h": buys_24h,
        "sells_24h": sells_24h,
        "realized_pnl_24h": round(realized_24h, 4),
        "realized_pnl_7d": round(realized_7d, 4),
        "closed_24h": len(closed_24h),
        "closed_7d": len(closed_7d),
        "largest_loss": _closed_brief(largest_loss),
        "largest_win": _closed_brief(largest_win),
        "lessons": lessons,
    }


def _closed_brief(item: dict | None) -> dict | None:
    if not item:
        return None
    return {
        "title": item.get("title", ""),
        "title_zh": translate_title(item.get("title", "")),
        "realized_pnl": round(_num(item.get("realizedPnl")), 4),
        "timestamp": _trade_timestamp(item),
    }


def _portfolio_actions(risks: list[dict], total_value: float, positions: list[dict]) -> list[str]:
    actions: list[str] = []
    high_count = sum(1 for r in risks if r["risk_level"] in ("high", "critical"))
    expiring = [r for r in risks if r.get("hours_left") is not None and 0 <= r["hours_left"] <= 24]
    illiquid = [r for r in risks if r.get("exit_depth") and not r["exit_depth"].get("fillable", True)]
    if high_count:
        actions.append(f"优先处理 {high_count} 个高风险持仓，先看是否能安全平仓或赎回")
    if expiring:
        actions.append(f"{len(expiring)} 个持仓 24h 内到期，禁止继续盲目加仓")
    if illiquid:
        actions.append(f"{len(illiquid)} 个持仓退出买盘不足，避免再买同类薄盘口")
    if total_value and positions:
        top = max((_position_value(p) for p in positions), default=0)
        if top / total_value >= 0.30:
            actions.append("组合存在单市场集中度过高，后续一键买入建议降低预算")
    if not actions:
        actions.append("组合暂无明显硬风险，保持小额、分散、到期前复核")
    return actions


async def build_portfolio_doctor(user: User, db: AsyncSession) -> dict:
    cred, address = await _active_wallet(user, db)
    now = datetime.now(timezone.utc)
    positions_raw, closed, value_payload, trades = await _load_wallet_snapshot(address)
    positions = [
        p for p in positions_raw
        if _position_size(p) > 0.000001 and not p.get("redeemable") and not p.get("redeemed")
    ]
    for p in positions:
        if p.get("title"):
            p["title_zh"] = translate_title(p["title"])
        for key in ("createdAt", "updatedAt", "startDate", "endDate", "endDateIso"):
            if p.get(key):
                p[f"{key}_bj"] = to_beijing_time(str(p[key]))

    total_value = _portfolio_total_value(value_payload, positions)
    depth_map = await _attach_exit_depth(positions)
    risks = [
        _risk_item(p, total_value, depth_map.get(_position_token(p)), now)
        for p in positions
    ]
    risks.sort(key=lambda r: (
        {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(r["risk_level"], 9),
        -(r.get("current_value") or 0),
    ))

    exposure_groups: dict[str, dict] = {}
    for p in positions:
        title = _position_title(p)
        key = _topic_key(title)
        group = exposure_groups.setdefault(key, {"topic": key, "titles": [], "value": 0.0, "count": 0})
        group["value"] += _position_value(p)
        group["count"] += 1
        if len(group["titles"]) < 3:
            group["titles"].append(title)
    exposures = sorted(exposure_groups.values(), key=lambda g: g["value"], reverse=True)
    for g in exposures:
        g["value"] = round(g["value"], 4)
        g["share_pct"] = round((g["value"] / total_value * 100) if total_value > 0 else 0.0, 2)

    trade_review = _recent_trade_summary(trades, closed, now)
    unrealized = sum(_num(p.get("cashPnl")) for p in positions)
    risk_counts = {
        "critical": sum(1 for r in risks if r["risk_level"] == "critical"),
        "high": sum(1 for r in risks if r["risk_level"] == "high"),
        "medium": sum(1 for r in risks if r["risk_level"] == "medium"),
        "low": sum(1 for r in risks if r["risk_level"] == "low"),
    }

    if risk_counts["critical"] or risk_counts["high"]:
        verdict = "需要处理"
        risk_level = "high" if not risk_counts["critical"] else "critical"
    elif risk_counts["medium"]:
        verdict = "谨慎持有"
        risk_level = "medium"
    else:
        verdict = "正常"
        risk_level = "low"

    return {
        "wallet": address,
        "wallet_address": cred.wallet_address,
        "funder_address": cred.funder_address,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "summary": {
            "verdict": verdict,
            "risk_level": risk_level,
            "positions": len(positions),
            "total_value": round(total_value, 4),
            "unrealized_pnl": round(unrealized, 4),
            "risk_counts": risk_counts,
        },
        "actions": _portfolio_actions(risks, total_value, positions),
        "risks": risks[:80],
        "top_risks": risks[:8],
        "exposures": exposures[:20],
        "trade_review": trade_review,
    }


def portfolio_doctor_markdown(report: dict) -> str:
    summary = report.get("summary") or {}
    lines = [
        f"组合状态: {summary.get('verdict')} / 风险 {summary.get('risk_level')}",
        f"持仓: {summary.get('positions', 0)} 个，总值 ${_num(summary.get('total_value')):.2f}，浮盈亏 ${_num(summary.get('unrealized_pnl')):.2f}",
        "",
        "建议动作:",
    ]
    for action in report.get("actions", [])[:6]:
        lines.append(f"• {action}")
    top_risks = report.get("top_risks") or []
    if top_risks:
        lines.extend(["", "高风险持仓:"])
        for r in top_risks[:5]:
            warn = "；".join(r.get("warnings") or r.get("blockers") or [])
            lines.append(f"• {r.get('title_zh')} ${_num(r.get('current_value')):.2f} [{r.get('risk_level')}]")
            if warn:
                lines.append(f"  {warn}")
    review = report.get("trade_review") or {}
    lines.extend([
        "",
        "交易复盘:",
        f"• 24h 交易 {review.get('trades_24h', 0)} 笔，已实现 ${_num(review.get('realized_pnl_24h')):.2f}",
        f"• 7d 已实现 ${_num(review.get('realized_pnl_7d')):.2f}",
    ])
    for lesson in review.get("lessons", [])[:4]:
        lines.append(f"• {lesson}")
    return "\n".join(lines)


async def recent_local_trades(user: User, db: AsyncSession, limit: int = 50) -> list[dict]:
    result = await db.execute(
        select(Trade)
        .where(Trade.user_id == user.id)
        .order_by(desc(Trade.created_at))
        .limit(limit)
    )
    trades = result.scalars().all()
    return [
        {
            "id": t.id,
            "market_slug": t.market_slug,
            "condition_id": t.condition_id,
            "token_id": t.token_id,
            "side": t.side,
            "order_type": t.order_type,
            "price": t.price,
            "size": t.size,
            "filled": t.filled,
            "status": t.status,
            "order_id": t.order_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in trades
    ]
