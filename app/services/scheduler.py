import json
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User, NotificationConfig
from app.services.scanner import scan_hot_markets, scan_new_political_markets, scan_arbitrage
from app.services.notification import notify_user
from app.services.polymarket import data_api

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def job_hot_scan():
    """定时扫描热门尾盘"""
    async with SessionLocal() as db:
        results = await scan_hot_markets(db, hours_until_expiry=24, min_volume=5000)
        if results:
            # 通知所有有推送配置的用户
            users = (await db.execute(select(User).where(User.status == "approved"))).scalars().all()
            title = f"热门尾盘扫描: 发现 {len(results)} 个市场"
            body = "\n".join([f"- {r['title']} (24h vol: ${r['volume_24h']:,.0f})" for r in results[:5]])
            for user in users:
                await notify_user(db, user, title, body)


async def job_political_scan():
    """定时扫描政治新盘"""
    async with SessionLocal() as db:
        results = await scan_new_political_markets(db)
        if results:
            users = (await db.execute(select(User).where(User.status == "approved"))).scalars().all()
            title = f"政治新盘扫描: 发现 {len(results)} 个新事件"
            body = "\n".join([f"- {r['title']}" for r in results[:5]])
            for user in users:
                await notify_user(db, user, title, body)


async def job_arbitrage_scan():
    """定时扫描套利机会"""
    async with SessionLocal() as db:
        results = await scan_arbitrage(db, threshold=0.02)
        if results:
            users = (await db.execute(select(User).where(User.status == "approved"))).scalars().all()
            title = f"套利机会: 发现 {len(results)} 个"
            body = "\n".join([f"- {r['title']} (偏差: {r['deviation']:.4f})" for r in results[:5]])
            for user in users:
                await notify_user(db, user, title, body)


async def job_position_report():
    """定时推送持仓报告"""
    async with SessionLocal() as db:
        users = (await db.execute(select(User).where(User.status == "approved"))).scalars().all()
        for user in users:
            from app.models import Credential
            from app.crypto import decrypt_secret
            result = await db.execute(
                select(Credential).where(Credential.user_id == user.id, Credential.is_active == True)
            )
            cred = result.scalar_one_or_none()
            if not cred:
                continue
            try:
                addr = cred.funder_address or cred.wallet_address
                positions = await data_api.get_positions(addr)
                # 过滤已结算持仓
                positions = [p for p in positions if float(p.get("size", 0)) > 0.000001 and not p.get("redeemable") and not p.get("redeemed")]
                value = await data_api.get_value(addr)
                # value 是数组格式 [{value: 0.5}]
                total = 0.0
                if isinstance(value, list) and value:
                    total = float(value[0].get("value", 0))
                elif isinstance(value, dict):
                    total = float(value.get("value", 0))
                title = f"持仓报告 - 总价值: ${total:,.2f}"
                body_lines = []
                for p in positions[:10]:
                    body_lines.append(f"- {p.get('title', 'N/A')}: {p.get('size', 0)} shares @ ${float(p.get('currentValue', 0)):.2f}")
                body = "\n".join(body_lines) if body_lines else "暂无持仓"
                await notify_user(db, user, title, body)
            except Exception as e:
                logger.error(f"持仓报告推送失败 user={user.id}: {e}")


async def job_cleanup_scan_results():
    """清理 7 天前的扫描结果"""
    async with SessionLocal() as db:
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        from sqlalchemy import delete
        await db.execute(delete(ScanResult).where(ScanResult.created_at < cutoff))
        await db.commit()
        logger.info("已清理过期扫描结果")


def start_scheduler():
    """启动定时任务"""
    # 每 30 分钟扫描热门尾盘
    scheduler.add_job(job_hot_scan, "interval", minutes=30, id="hot_scan", replace_existing=True)
    # 每 2 小时扫描政治新盘
    scheduler.add_job(job_political_scan, "interval", hours=2, id="political_scan", replace_existing=True)
    # 每小时扫描套利机会
    scheduler.add_job(job_arbitrage_scan, "interval", hours=1, id="arbitrage_scan", replace_existing=True)
    # 每天 UTC 0 点推送持仓报告
    scheduler.add_job(job_position_report, "cron", hour=0, id="position_report", replace_existing=True)
    # 每天清理 7 天前的扫描结果
    scheduler.add_job(job_cleanup_scan_results, "cron", hour=3, id="cleanup_scan", replace_existing=True)
    scheduler.start()
    logger.info("定时任务已启动")


def stop_scheduler():
    scheduler.shutdown(wait=False)
