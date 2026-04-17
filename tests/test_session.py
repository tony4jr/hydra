from worker.session import WorkerSession
from datetime import datetime, UTC


def test_session_init():
    session = WorkerSession("profile_123", account_id=1, device_id="device1")
    assert session.profile_id == "profile_123"
    assert session.account_id == 1
    assert session.tasks_completed == 0
    assert 3 <= session.max_tasks_per_session <= 8
    assert 20 <= session.max_session_minutes <= 45


def test_session_should_continue_no_start():
    import asyncio
    session = WorkerSession("profile_123", account_id=1)
    result = asyncio.run(session.should_continue())
    assert result is False


def test_session_max_tasks():
    import asyncio
    session = WorkerSession("profile_123", account_id=1)
    session.started_at = datetime.now(UTC)
    session.max_tasks_per_session = 3
    session.tasks_completed = 3
    result = asyncio.run(session.should_continue())
    assert result is False
