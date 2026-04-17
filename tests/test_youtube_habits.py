"""YouTube 습관 테스트."""
from worker.youtube_habits import maybe_check_notifications, maybe_visit_own_channel


def test_imports():
    """모듈 임포트 정상 확인."""
    from worker import youtube_habits
    assert hasattr(youtube_habits, "maybe_check_notifications")
    assert hasattr(youtube_habits, "maybe_visit_own_channel")


def test_maybe_check_notifications_is_async():
    """maybe_check_notifications가 코루틴 함수인지 확인."""
    import asyncio
    assert asyncio.iscoroutinefunction(maybe_check_notifications)


def test_maybe_visit_own_channel_is_async():
    """maybe_visit_own_channel이 코루틴 함수인지 확인."""
    import asyncio
    assert asyncio.iscoroutinefunction(maybe_visit_own_channel)
