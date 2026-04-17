import asyncio
from hydra.services.alert_service import send_alert


def test_send_alert_no_telegram_configured():
    """텔레그램 미설정 시 에러 없이 통과."""
    asyncio.run(send_alert("test", "test message", "info"))
    # No exception = pass
