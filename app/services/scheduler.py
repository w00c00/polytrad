import json
import hashlib
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User, NotificationConfig
from app.services.scanner import scan_hot_markets, scan_new_political_markets, scan_arbitrage
from app.services.notification import notify_user
from app.services.polymarket import data_api, translate_title

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

# 推送去重：记录上次推送内容的 hash，相同内容不重复推送
_last_notify_hash: dict[str, str] = {}


def _content_hash(title: str, body: str) -> str:
    return hashlib.md5(f"{title}|{body}".encode()).hexdigest()


def _should_notify(job_key: str, title: str, body: str) -> bool:
    h = _content_hash(title, body)
    if _last_notify_hash.get(job_key) == h:
        logger.info(f"[{job_key}] 内容未变化，跳过推送")
        return False
    _last_notify_hash[job_key] = h
    return True


async def job_hot_scan():
    """定时扫描热门尾盘"""
    async with SessionLocal() as db:
        results = await scan_hot_markets(db, hours_until_expiry=24, min_volume=5000)
        if not results:
            return
        title = f"热门尾盘扫描 - {len(results)} 个市场"
        lines = []
        for r in results[:5]:
            name = r.get("title_zh") or r.get("title", "")
            lines.append(f"• {name}")
            lines.append(f"  成交量: ${r['volume_24h']:,.0f}")
        body = "\n".join(lines)
        if not _should_notify("hot_scan", title, body):
            return
        users = (await db.execute(select(User).where(User.status == "approved"))).scalars().all()
        for user in users:
            await notify_user(db, user, title, body)


async def job_political_scan():
    """定时扫描政治新盘"""
    async with SessionLocal() as db:
        results = await scan_new_political_markets(db)
        if not results:
            return
        title = f"政治新盘 - {len(results)} 个新事件"
        lines = []
        for r in results[:5]:
            name = r.get("title_zh") or r.get("title", "")
            lines.append(f"• {name}")
        body = "\n".join(lines)
        if not _should_notify("political_scan", title, body):
            return
        users = (await db.execute(select(User).where(User.status == "approved"))).scalars().all()
        for user in users:
            await notify_user(db, user, title, body)


async def job_arbitrage_scan():
    """定时扫描套利机会"""
    async with SessionLocal() as db:
        results = await scan_arbitrage(db, threshold=0.02)
        if not results:
            return
        title = f"套利机会 - {len(results)} 个"
        lines = []
        for r in results[:5]:
            name = r.get("title_zh") or r.get("title", "")
            lines.append(f"• {name}")
            lines.append(f"  偏差: {r['deviation']:.1%}  方向: {r['direction']}")
        body = "\n".join(lines)
        if not _should_notify("arbitrage_scan", title, body):
            return
        users = (await db.execute(select(User).where(User.status == "approved"))).scalars().all()
        for user in users:
            await notify_user(db, user, title, body)


async def job_position_report():
    """定时推送持仓报告"""
    async with SessionLocal() as db:
        users = (await db.execute(select(User).where(User.status == "approved"))).scalars().all()
        for user in users:
            from app.models import Credential
            result = await db.execute(
                select(Credential).where(Credential.user_id == user.id, Credential.is_active == True)
            )
            cred = result.scalar_one_or_none()
            if not cred:
                continue
            try:
                addr = cred.funder_address or cred.wallet_address
                positions = await data_api.get_positions(addr)
                positions = [p for p in positions if float(p.get("size", 0)) > 0.000001 and not p.get("redeemable") and not p.get("redeemed")]
                value = await data_api.get_value(addr)
                total = 0.0
                if isinstance(value, list) and value:
                    total = float(value[0].get("value", 0))
                elif isinstance(value, dict):
                    total = float(value.get("value", 0))
                title = f"持仓报告 - ${total:,.2f}"
                lines = []
                for p in positions[:10]:
                    pnl = float(p.get("cashPnl", 0))
                    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
                    t = translate_title(p.get("title", "N/A"))
                    lines.append(f"• {t}")
                    lines.append(f"  {p.get('size', 0)} 份 · ${float(p.get('currentValue', 0)):.2f} ({pnl_str})")
                body = "\n".join(lines) if lines else "暂无持仓"
                if _should_notify(f"position_report_{user.id}", title, body):
                    await notify_user(db, user, title, body)
            except Exception as e:
                logger.error(f"持仓报告推送失败 user={user.id}: {e}")


async def send_trade_report(user: User, db):
    """手动推送交易报告（含24h盈亏）"""
    from app.models import Credential
    from datetime import datetime, timezone, timedelta

    result = await db.execute(
        select(Credential).where(Credential.user_id == user.id, Credential.is_active == True)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        return "未配置钱包"

    addr = cred.funder_address or cred.wallet_address
    now = datetime.now(timezone.utc)
    bj = timezone(timedelta(hours=8))

    # 并发获取数据
    import asyncio
    positions_raw, closed, value, trades = await asyncio.gather(
        data_api.get_positions(addr),
        data_api.get_closed_positions(addr),
        data_api.get_value(addr),
        data_api.get_trades(addr, limit=100),
    )

    # 当前持仓（过滤无效）
    positions = [p for p in positions_raw if float(p.get("size", 0)) > 0.000001 and not p.get("redeemable") and not p.get("redeemed")]

    # 总资产
    total = 0.0
    if isinstance(value, list) and value:
        total = float(value[0].get("value", 0))
    elif isinstance(value, dict):
        total = float(value.get("value", 0))

    # 24h 已实现盈亏（从已平仓）
    ts_24h = int((now - timedelta(hours=24)).timestamp())
    pnl_24h_realized = 0.0
    closed_24h = []
    for c in (closed or []):
        cts = int(c.get("timestamp", 0))
        if cts >= ts_24h:
            pnl_24h_realized += float(c.get("realizedPnl", 0))
            closed_24h.append(c)

    # 当前持仓未实现盈亏
    pnl_unrealized = sum(float(p.get("cashPnl", 0)) for p in positions)

    # 24h 交易次数
    trades_24h = [t for t in (trades or []) if int(t.get("timestamp", 0)) >= ts_24h]

    # 构建报告
    pnl_24h_total = pnl_24h_realized + pnl_unrealized
    pnl_sign = "+" if pnl_24h_total >= 0 else ""
    title = f"交易报告 - ${total:,.2f} ({pnl_sign}${pnl_24h_total:.2f}/24h)"

    lines = []
    # 24h 盈亏摘要
    lines.append(f"24h 盈亏: {pnl_sign}${pnl_24h_total:.2f}")
    r_sign = "+" if pnl_24h_realized >= 0 else ""
    lines.append(f"  已实现: {r_sign}${pnl_24h_realized:.2f} ({len(closed_24h)} 笔)")
    u_sign = "+" if pnl_unrealized >= 0 else ""
    lines.append(f"  持仓浮盈: {u_sign}${pnl_unrealized:.2f}")
    lines.append(f"24h 交易: {len(trades_24h)} 笔")
    lines.append(f"总资产: ${total:,.2f}")

    # 当前持仓
    if positions:
        lines.append("")
        lines.append(f"当前持仓 ({len(positions)} 个):")
        for p in positions[:5]:
            pnl = float(p.get("cashPnl", 0))
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            t = translate_title(p.get("title", "N/A"))
            lines.append(f"• {t}")
            lines.append(f"  ${float(p.get('currentValue', 0)):.2f} ({pnl_str})")
        if len(positions) > 5:
            lines.append(f"  ...还有 {len(positions) - 5} 个")

    # 24h 已平仓盈亏明细
    if closed_24h:
        lines.append("")
        lines.append("24h 已平仓:")
        for c in closed_24h[:5]:
            pnl = float(c.get("realizedPnl", 0))
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            t = translate_title(c.get("title", "N/A"))
            lines.append(f"• {t} {pnl_str}")
        if len(closed_24h) > 5:
            lines.append(f"  ...还有 {len(closed_24h) - 5} 笔")

    # 最近交易
    if trades_24h:
        lines.append("")
        lines.append("24h 交易记录:")
        for t in trades_24h[:5]:
            ts = t.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                    ts = dt.astimezone(bj).strftime("%m-%d %H:%M")
                except (ValueError, TypeError):
                    pass
            trade_title = translate_title(t.get("title", ""))
            lines.append(f"• [{ts}] {t.get('side', '')} {trade_title}")
            lines.append(f"  {float(t.get('size', 0)):.0f}份 @ ${float(t.get('price', 0)):.3f}")
        if len(trades_24h) > 5:
            lines.append(f"  ...还有 {len(trades_24h) - 5} 笔")

    body = "\n".join(lines)
    await notify_user(db, user, title, body)
    return "交易报告已推送"


async def job_cleanup_scan_results():
    """清理 7 天前的扫描结果"""
    async with SessionLocal() as db:
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        from sqlalchemy import delete
        from app.models import ScanResult
        await db.execute(delete(ScanResult).where(ScanResult.created_at < cutoff))
        await db.commit()
        logger.info("已清理过期扫描结果")


def start_scheduler():
    """启动定时任务"""
    scheduler.add_job(job_hot_scan, "interval", hours=2, id="hot_scan", replace_existing=True)
    scheduler.add_job(job_political_scan, "interval", hours=6, id="political_scan", replace_existing=True)
    scheduler.add_job(job_arbitrage_scan, "interval", hours=2, id="arbitrage_scan", replace_existing=True)
    scheduler.add_job(job_position_report, "cron", hour=0, id="position_report", replace_existing=True)
    scheduler.add_job(job_cleanup_scan_results, "cron", hour=3, id="cleanup_scan", replace_existing=True)
    scheduler.start()
    logger.info("定时任务已启动")


def stop_scheduler():
    scheduler.shutdown(wait=False)
