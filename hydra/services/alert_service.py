"""알림 서비스 — 텔레그램 + 대시보드 알림 통합."""
from hydra.core.config import settings


async def send_alert(event_type: str, message: str, level: str = "info"):
    """알림 전송 (텔레그램 + WebSocket)."""
    # 텔레그램
    if settings.telegram_bot_token and settings.telegram_chat_id:
        await _send_telegram(event_type, message, level)

    # WebSocket (대시보드 실시간)
    try:
        from hydra.services.realtime import manager
        await manager.broadcast("alert", {
            "event_type": event_type,
            "message": message,
            "level": level,
        })
    except Exception:
        pass


async def _send_telegram(event_type: str, message: str, level: str):
    """텔레그램 메시지 전송."""
    import httpx

    emoji = {"critical": "\U0001f534", "warning": "\U0001f7e0", "info": "\U0001f7e2"}.get(level, "\u2139\ufe0f")
    text = f"{emoji} [{event_type}] {message}"

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
    except Exception:
        pass


# 편의 함수들
async def alert_worker_disconnected(worker_name: str):
    await send_alert("worker_offline", f"Worker '{worker_name}' 연결 끊김", "critical")


async def alert_account_suspended(gmail: str):
    await send_alert("account_suspended", f"계정 정지: {gmail}", "critical")


async def alert_ghost_detected(campaign_id: int, account_gmail: str):
    await send_alert("ghost_detected", f"고스트 감지: 캠페인 {campaign_id}, 계정 {account_gmail}", "warning")


async def alert_error_repeated(error_source: str, count: int):
    await send_alert("error_repeated", f"{error_source} 에러 {count}회 반복", "warning")


async def alert_weekly_goal(brand_name: str, achieved: int, target: int):
    level = "info" if achieved >= target else "warning"
    await send_alert("weekly_goal", f"{brand_name}: 주간 목표 {achieved}/{target}", level)


async def alert_backup_failed(error: str):
    await send_alert("backup_failed", f"백업 실패: {error}", "critical")
