"""Telegram notification bot — 3 tiers: urgent, warning, info."""

import asyncio
from telegram import Bot
from hydra.core.config import settings
from hydra.core.logger import get_logger

log = get_logger("telegram")

_bot: Bot | None = None


def _get_bot() -> Bot | None:
    global _bot
    if not settings.telegram_bot_token:
        return None
    if _bot is None:
        _bot = Bot(token=settings.telegram_bot_token)
    return _bot


async def _send(text: str):
    bot = _get_bot()
    if not bot:
        log.warning("Telegram bot token not configured, skipping notification")
        return
    try:
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=text,
            parse_mode="HTML",
        )
    except Exception as e:
        log.error(f"Telegram send failed: {e}")


def send_sync(text: str):
    """Fire-and-forget sync wrapper."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send(text))
    except RuntimeError:
        asyncio.run(_send(text))


# --- Convenience helpers ---

def urgent(msg: str):
    """🚨 Level 4-5: account suspended, system crash, etc."""
    send_sync(f"🚨 <b>[긴급]</b> {msg}")
    log.critical(msg)


def warning(msg: str):
    """⚠️ Level 3: ghost detected, login failed, etc."""
    send_sync(f"⚠️ <b>[경고]</b> {msg}")
    log.warning(msg)


def info(msg: str):
    """ℹ️ Info: warmup graduation, campaign complete, etc."""
    send_sync(f"ℹ️ {msg}")
    log.info(msg)


def daily_report(report: str):
    """📊 Daily report (11pm)."""
    send_sync(f"📊 <b>HYDRA 일일 리포트</b>\n\n{report}")
