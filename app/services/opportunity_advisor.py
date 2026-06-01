from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SAFE_MIN_BASKET_PROFIT_PCT = 0.2
SAFE_MIN_BTC_EDGE = 0.04
SAFE_MAX_SIMPLE_BUY_AMOUNT = 100.0
SAFE_MAX_SLIPPAGE_PCT = 5.0


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        if value:
            return str(value)
    return default


def _add_check(checks: list[dict], label: str, status: str, detail: str = "") -> None:
    checks.append({"label": label, "status": status, "detail": detail})


def _level(blockers: list[str], warnings: list[str], forced: str | None = None) -> str:
    if blockers:
        return "critical"
    if forced:
        return forced
    if len(warnings) >= 4:
        return "high"
    if len(warnings) >= 2:
        return "medium"
    return "low"


def _verdict(blockers: list[str], warnings: list[str]) -> str:
    if blockers:
        return "BLOCK"
    if warnings:
        return "CAUTION"
    return "OK"


def _risk_label(level: str) -> str:
    return {
        "low": "低",
        "medium": "中",
        "high": "高",
        "critical": "禁止",
    }.get(level, level)


def _common_title(item: dict) -> str:
    return _first_text(
        item.get("title_zh"),
        item.get("question_zh"),
        item.get("topic_zh"),
        item.get("title"),
        item.get("question"),
        item.get("topic"),
        item.get("event_slug"),
        item.get("slug"),
        default="机会",
    )


def _base_response(kind: str, item: dict, amount: float) -> dict:
    return {
        "kind": kind,
        "title": _common_title(item),
        "amount": round(amount, 4),
        "engine": "规则风控 + 机会解释",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checks": [],
        "blockers": [],
        "warnings": [],
        "tips": [],
        "metrics": {},
    }


def _finish(resp: dict, summary: str, forced_level: str | None = None) -> dict:
    level = _level(resp["blockers"], resp["warnings"], forced_level)
    verdict = _verdict(resp["blockers"], resp["warnings"])
    allowed = not resp["blockers"]
    resp.update({
        "allowed": allowed,
        "verdict": verdict,
        "risk_level": level,
        "risk_label": _risk_label(level),
        "summary": summary,
        "suggested_action": _suggested_action(verdict, level),
        "confirm_text": _confirm_text(resp, summary),
    })
    return resp


def _suggested_action(verdict: str, level: str) -> str:
    if verdict == "BLOCK":
        return "不要下单，先重扫或换市场"
    if level == "high":
        return "只建议小额 FOK，提交后立刻核对订单"
    if verdict == "CAUTION":
        return "可以继续，但先确认提示中的风险"
    return "可按当前参数继续执行"


def _confirm_text(resp: dict, summary: str) -> str:
    lines = [
        f"{summary}",
        f"风险等级：{resp.get('risk_label', '-')}",
    ]
    if resp["blockers"]:
        lines.append("阻断项：" + "；".join(resp["blockers"][:4]))
    if resp["warnings"]:
        lines.append("风险提示：" + "；".join(resp["warnings"][:5]))
    if resp["tips"]:
        lines.append("操作提示：" + "；".join(resp["tips"][:4]))
    return "\n".join(lines)


def _advice_basket(item: dict, amount: float, context: dict) -> dict:
    resp = _base_response("basket", item, amount)
    checks = resp["checks"]
    blockers = resp["blockers"]
    warnings = resp["warnings"]
    tips = resp["tips"]
    metrics = resp["metrics"]

    integrity = item.get("integrity") or {}
    captured = integrity.get("captured_count") or len(item.get("markets") or item.get("legs") or [])
    official = integrity.get("official_count") or "?"
    profit = _num(item.get("estimated_profit"))
    profit_pct = _num(item.get("estimated_profit_pct"))
    yes_sum = _num(item.get("yes_sum"))
    direction = item.get("direction")

    metrics.update({
        "budget": amount or _num(item.get("budget_usdc")),
        "estimated_profit": profit,
        "estimated_profit_pct": profit_pct,
        "yes_sum": yes_sum,
        "captured_count": captured,
        "official_count": official,
    })

    if integrity.get("ok"):
        _add_check(checks, "池子完整性", "pass", f"{captured}/{official}")
    else:
        _add_check(checks, "池子完整性", "fail", integrity.get("note") or f"{captured}/{official}")
        blockers.append(integrity.get("note") or "池子完整性未通过，存在漏腿黑天鹅风险")

    if direction == "BUY_YES" and item.get("executable"):
        _add_check(checks, "执行方向", "pass", "BUY_YES 可一键买入")
    else:
        _add_check(checks, "执行方向", "fail", f"{direction or '-'} / executable={bool(item.get('executable'))}")
        blockers.append("不是可直接执行的 BUY_YES 整篮机会")

    if item.get("can_shadow"):
        warnings.append("有缺盘口腿，只能先影子挂单补腿，不应直接一键买入")

    min_profit = _num(context.get("min_profit_pct"), SAFE_MIN_BASKET_PROFIT_PCT)
    if profit <= 0 or profit_pct < min_profit:
        blockers.append(f"预估毛利 {profit_pct:.2f}% 低于阈值 {min_profit:.2f}%")
        _add_check(checks, "预算毛利", "fail", f"${profit:.2f} / {profit_pct:.2f}%")
    elif profit_pct < 1:
        warnings.append(f"毛利率只有 {profit_pct:.2f}%，盘口轻微变化就可能吃掉利润")
        _add_check(checks, "预算毛利", "warn", f"${profit:.2f} / {profit_pct:.2f}%")
    else:
        _add_check(checks, "预算毛利", "pass", f"${profit:.2f} / {profit_pct:.2f}%")

    if yes_sum and (yes_sum < 0.90 or yes_sum > 0.995):
        warnings.append(f"YES 总和 {yes_sum:.4f} 超出保守执行区间，必须以最新预检为准")

    tips.extend([
        "整篮提交前后端会重新预检盘口深度和完整性",
        "FOK 可避免单腿残留挂单，但交易所不保证多腿原子成交",
        "提交后立即到订单/持仓页核对每条腿是否成交",
    ])
    return _finish(resp, f"篮子机会：预算约 ${metrics['budget']:.2f}，预估毛利 ${profit:.2f}（{profit_pct:.2f}%）。")


def _advice_slippage(item: dict, amount: float, context: dict) -> dict:
    resp = _base_response("slippage", item, amount)
    checks = resp["checks"]
    blockers = resp["blockers"]
    warnings = resp["warnings"]
    tips = resp["tips"]
    depth = item.get("depth") or {}
    max_slippage = _num(context.get("max_slippage_pct"), SAFE_MAX_SLIPPAGE_PCT)
    slippage = _num(depth.get("slippage_pct"))
    avg_price = _num(depth.get("avg_price"))
    worst_price = _num(depth.get("worst_price"))
    shares = _num(depth.get("shares"))
    gross_profit = _num(depth.get("gross_profit_if_win"))

    resp["metrics"].update({
        "amount": amount,
        "avg_price": avg_price,
        "worst_price": worst_price,
        "slippage_pct": slippage,
        "shares": shares,
        "gross_profit_if_win": gross_profit,
    })

    if not depth.get("fillable", True):
        blockers.append("当前盘口吃不满设置金额")
        _add_check(checks, "盘口深度", "fail", "fillable=false")
    elif shares < 5:
        blockers.append("可买份额不足 5 份，交易所会拒单")
        _add_check(checks, "盘口深度", "fail", f"{shares:.2f} 份")
    else:
        _add_check(checks, "盘口深度", "pass", f"{shares:.2f} 份")

    if slippage > max_slippage:
        blockers.append(f"价格冲击 {slippage:.2f}% 超过阈值 {max_slippage:.2f}%")
        _add_check(checks, "价格冲击", "fail", f"{slippage:.2f}%")
    elif slippage > 2:
        warnings.append(f"价格冲击 {slippage:.2f}% 偏高，成交均价可能明显变差")
        _add_check(checks, "价格冲击", "warn", f"{slippage:.2f}%")
    else:
        _add_check(checks, "价格冲击", "pass", f"{slippage:.2f}%")

    if avg_price < 0.02 or avg_price > 0.98:
        blockers.append("价格接近 0/1，容易是过期、结算或极端盘口，不从滑点页执行")
    elif avg_price > 0.90 or avg_price < 0.05:
        warnings.append("价格处于极端区间，需确认不是已结算或信息已充分反应")

    if amount > SAFE_MAX_SIMPLE_BUY_AMOUNT:
        warnings.append(f"单盘口买入金额 ${amount:.2f} 偏大，建议拆单或降低金额")

    tips.extend([
        "兑付毛利是假设该结果最终兑付 1，不是确定套利利润",
        "买入前后端会用 FOK 按最新订单簿重新提交",
    ])
    return _finish(resp, f"滑点机会：${amount:.2f} 预计买 {shares:.2f} 份，均价 ${avg_price:.4f}，冲击 {slippage:.2f}%。")


def _advice_cross(item: dict, amount: float, context: dict) -> dict:
    resp = _base_response("cross", item, amount)
    checks = resp["checks"]
    blockers = resp["blockers"]
    warnings = resp["warnings"]
    tips = resp["tips"]
    depth = item.get("pair_depth") or {}
    relation_type = item.get("relation_type") or depth.get("relation_type") or ""
    profit = _num(depth.get("expected_profit"))
    profit_pct = _num(depth.get("expected_profit_pct"))
    total_cost = _num(depth.get("total_cost") or depth.get("capacity_usdc"))
    max_capacity = _num(depth.get("max_capacity_usdc"))
    shares = _num(depth.get("target_shares"))

    resp["metrics"].update({
        "requested_budget": amount,
        "total_cost": total_cost,
        "expected_profit": profit,
        "expected_profit_pct": profit_pct,
        "max_capacity_usdc": max_capacity,
        "target_shares": shares,
        "relation_type": relation_type,
    })

    if item.get("executable") and depth.get("fillable"):
        _add_check(checks, "双边深度", "pass", f"{shares:.2f} 份 / 成本 ${total_cost:.2f}")
    else:
        blockers.append(depth.get("reason") or "当前可盈利双边深度不足")
        _add_check(checks, "双边深度", "fail", depth.get("reason") or "fillable=false")

    if profit <= 0 or profit_pct <= 0:
        blockers.append("双边预估毛利不为正")
        _add_check(checks, "预算毛利", "fail", f"${profit:.2f} / {profit_pct:.2f}%")
    elif profit_pct < SAFE_MIN_BASKET_PROFIT_PCT:
        warnings.append(f"毛利率 {profit_pct:.2f}% 很薄，单腿盘口变化即可吞掉利润")
        _add_check(checks, "预算毛利", "warn", f"${profit:.2f} / {profit_pct:.2f}%")
    else:
        _add_check(checks, "预算毛利", "pass", f"${profit:.2f} / {profit_pct:.2f}%")

    if shares < 5:
        blockers.append("双边可执行份额不足 5 份")
    if relation_type != "EXACT_DUPLICATE":
        warnings.append("不是完全同题重复盘，必须人工确认规则包含关系")
    if amount and max_capacity and amount > max_capacity * 1.2:
        warnings.append(f"预算高于当前可盈利盘口容量 ${max_capacity:.2f}，实际可能只成交一小部分")

    tips.extend([
        "双边订单不是交易所原子成交，任意一腿失败都需要立即核对",
        "低价端买 YES，高价参考端买 NO；不要手动改方向",
        "到期包含价差只在规则文本严格包含时成立",
    ])
    return _finish(resp, f"同题价差：预计成本 ${total_cost:.2f}，兑付 ${shares:.2f}，毛利 ${profit:.2f}（{profit_pct:.2f}%）。", "high")


def _advice_resolution(item: dict, amount: float, context: dict) -> dict:
    resp = _base_response("resolution", item, amount)
    checks = resp["checks"]
    blockers = resp["blockers"]
    warnings = resp["warnings"]
    tips = resp["tips"]
    hours_left = _num(item.get("hours_left"), -1)
    status = str(item.get("uma_status") or "").lower()
    yes_price = _num(item.get("yes_price"))

    resp["metrics"].update({
        "amount": amount,
        "hours_left": hours_left,
        "uma_status": status,
        "yes_price": yes_price,
    })

    if not item.get("can_buy", True):
        blockers.append(item.get("trade_disabled_reason") or "临近结算市场当前不可下单")
        _add_check(checks, "交易状态", "fail", item.get("trade_disabled_reason") or "can_buy=false")
    else:
        _add_check(checks, "交易状态", "pass", "可下单")

    if status and status not in ("ending_soon", "active", "open"):
        blockers.append(f"UMA/结算状态为 {status}，只观察不下单")
    if hours_left <= 0:
        blockers.append("市场已过期或缺少有效剩余时间")
    elif hours_left < 0.25:
        warnings.append("距离结束不足 15 分钟，盘口和结算状态可能快速变化")
    elif hours_left < 1:
        warnings.append("距离结束不足 1 小时，只适合小额 FOK")

    if yes_price > 0.95 or yes_price < 0.05:
        warnings.append("价格接近 0/1，可能已被事件结果充分定价")

    tips.extend([
        "临近结算买入不是套利，主要是信息优势/结算判断",
        "只用 FOK 小额执行，不要留 GTC 残单",
        "下单前确认市场没有进入 proposed/resolved/disputed",
    ])
    return _finish(resp, f"临近结算：剩余约 {hours_left:.2f} 小时，YES ${yes_price:.3f}，本次金额 ${amount:.2f}。", "high")


def _advice_btc(item: dict, amount: float, context: dict) -> dict:
    resp = _base_response("btc", item, amount)
    checks = resp["checks"]
    blockers = resp["blockers"]
    warnings = resp["warnings"]
    tips = resp["tips"]
    signal = item.get("signal") or {}
    edge = _num(item.get("edge"))
    action = str(item.get("action") or "")
    market = item.get("market") or {}

    resp["metrics"].update({
        "amount": amount,
        "edge": edge,
        "action": action,
        "prob_up": _num(signal.get("prob_up")),
        "prob_down": _num(signal.get("prob_down")),
    })

    token_ids = market.get("token_ids") or item.get("token_ids") or []
    if not token_ids:
        blockers.append("缺少 BTC 市场 token，无法安全下单")
        _add_check(checks, "token", "fail", "token_ids missing")
    else:
        _add_check(checks, "token", "pass", f"{len(token_ids)} 个")

    if edge < SAFE_MIN_BTC_EDGE:
        warnings.append(f"edge 只有 {edge * 100:.1f}%，低于建议阈值 {SAFE_MIN_BTC_EDGE * 100:.1f}%")
        _add_check(checks, "模型边际", "warn", f"{edge * 100:.1f}%")
    else:
        _add_check(checks, "模型边际", "pass", f"{edge * 100:.1f}%")

    if amount > 50:
        warnings.append("BTC 短周期波动快，单笔金额偏大")

    tips.extend([
        "BTC 短周期是概率交易，不是套利",
        "edge 来自本地动量模型，遇到新闻/插针会失效",
        "距离结算越近越要小额 FOK，成交后不要忘记核对方向",
    ])
    return _finish(resp, f"BTC 提醒：{action or '买入'}，edge {edge * 100:.1f}%，本次金额 ${amount:.2f}。", "medium")


def _advice_rewards(item: dict, amount: float, context: dict) -> dict:
    resp = _base_response("rewards", item, amount)
    checks = resp["checks"]
    blockers = resp["blockers"]
    warnings = resp["warnings"]
    tips = resp["tips"]
    spread = _num(item.get("spread"))
    max_spread = _num(item.get("rewards_max_spread"))
    min_size = _num(item.get("rewards_min_size"))

    resp["metrics"].update({
        "amount_per_side": amount,
        "spread": spread,
        "rewards_max_spread": max_spread,
        "rewards_min_size": min_size,
    })

    if not item.get("slug"):
        blockers.append("缺少市场 slug，无法挂双边做市单")
    if max_spread and spread > max_spread:
        warnings.append(f"当前点差 {spread * 100:.2f}% 高于奖励要求 {max_spread * 100:.2f}%")
        _add_check(checks, "奖励点差", "warn", f"{spread * 100:.2f}%")
    else:
        _add_check(checks, "奖励点差", "pass", f"{spread * 100:.2f}%")

    if min_size and amount < min_size * 0.02:
        warnings.append("单边金额可能不足奖励最小份额，后端可能拒绝提交")

    tips.extend([
        "做市挂单只用 post-only，不主动吃单",
        "挂出后要观察是否 scoring、是否偏离中间价",
        "行情突变时使用紧急全撤",
    ])
    return _finish(resp, f"奖励做市：YES/NO 两边各约 ${amount:.2f}，当前点差 {spread * 100:.2f}%。", "medium")


def build_opportunity_advice(kind: str, item: dict, amount: float = 0, context: dict | None = None) -> dict:
    context = context or {}
    kind = (kind or "").lower().strip()
    amount = _num(amount)

    if kind == "basket":
        return _advice_basket(item, amount, context)
    if kind == "slippage":
        return _advice_slippage(item, amount, context)
    if kind == "cross":
        return _advice_cross(item, amount, context)
    if kind == "resolution":
        return _advice_resolution(item, amount, context)
    if kind == "btc":
        return _advice_btc(item, amount, context)
    if kind == "rewards":
        return _advice_rewards(item, amount, context)

    resp = _base_response(kind or "unknown", item, amount)
    resp["warnings"].append("未知机会类型，只能做通用检查")
    if amount <= 0:
        resp["blockers"].append("下单金额必须大于 0")
    if not (item.get("token_id") or item.get("token_ids") or item.get("slug") or item.get("event_slug")):
        resp["blockers"].append("缺少可交易标识")
    resp["tips"].append("请回到对应扫描页重新扫描，再从标准按钮执行")
    return _finish(resp, "通用机会检查。", "high")
