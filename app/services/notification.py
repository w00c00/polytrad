import logging
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User, NotificationConfig
from app.crypto import decrypt_secret

logger = logging.getLogger(__name__)


async def send_serverchan(sendkey: str, title: str, content: str = "") -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://sctapi.ftqq.com/{sendkey}.send",
            data={"title": title, "desp": content},
        )
        data = resp.json()
        if data.get("code") != 0:
            logger.warning(f"方糖推送失败: {data}")
        return data


async def send_telegram(bot_token: str, chat_id: str, text: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning(f"Telegram 推送失败: {data}")
        return data


async def notify_user(db: AsyncSession, user: User, title: str, body: str):
    """向用户的所有已配置推送渠道发送消息"""
    result = await db.execute(
        select(NotificationConfig).where(
            NotificationConfig.user_id == user.id,
            NotificationConfig.is_active == True,
        )
    )
    configs = result.scalars().all()

    for cfg in configs:
        try:
            config_data = decrypt_secret(cfg.encrypted_config)
            import json
            data = json.loads(config_data)

            if cfg.channel == "serverchan":
                # ServerChan 用 markdown，\n 需要是真正的换行符
                md_body = body.replace("\n", "\n\n")
                await send_serverchan(data["sendkey"], title, md_body)
            elif cfg.channel == "telegram":
                # Telegram HTML 模式：换行用 \n
                tg_text = f"<b>{title}</b>\n\n{body}"
                await send_telegram(data["bot_token"], data["chat_id"], tg_text)
        except Exception as e:
            logger.error(f"推送失败 (user={user.id}, channel={cfg.channel}): {e}")


async def test_serverchan(sendkey: str) -> dict:
    return await send_serverchan(sendkey, "PolyTrad 测试", "方糖推送配置成功!")


async def test_telegram(bot_token: str, chat_id: str) -> dict:
    return await send_telegram(bot_token, chat_id, "<b>PolyTrad 测试</b>\nTelegram 推送配置成功!")
