import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_worker_session_calls_ensure_safe_ip():
    """WorkerSession.start(db=..) should call ensure_safe_ip with account+worker."""
    from worker.session import WorkerSession

    calls = []

    async def fake_ensure(db, account, worker):
        calls.append((account, worker))
        class Fake:
            id = 1
        return Fake()

    with patch("worker.session.BrowserSession") as BS, \
         patch("worker.session.ensure_safe_ip", side_effect=fake_ensure):
        instance = MagicMock()
        instance.start = AsyncMock()
        instance.goto = AsyncMock()
        instance.page = None
        BS.return_value = instance

        session = WorkerSession(
            profile_id="p1", account_id=42, device_id="DEV",
            account=type("A", (), {"id": 42})(),
            worker=type("W", (), {"id": 7, "ip_config": json.dumps({"adb_device_id": "DEV"})})(),
        )

        ok = await session.start(db=object())
        assert ok
        assert len(calls) == 1
        assert calls[0][0].id == 42
        assert calls[0][1].id == 7


@pytest.mark.asyncio
async def test_worker_session_skips_hook_when_no_db():
    """If db is not passed, session.start should proceed without calling ensure_safe_ip."""
    from worker.session import WorkerSession

    with patch("worker.session.BrowserSession") as BS, \
         patch("worker.session.ensure_safe_ip") as mock_ensure:
        instance = MagicMock()
        instance.start = AsyncMock()
        instance.goto = AsyncMock()
        instance.page = None
        BS.return_value = instance

        session = WorkerSession(profile_id="p1", account_id=42, device_id="DEV")
        ok = await session.start()  # no db
        assert ok
        mock_ensure.assert_not_called()


@pytest.mark.asyncio
async def test_worker_session_propagates_ip_rotation_failed():
    """IPRotationFailed from ensure_safe_ip must bubble up, not be swallowed."""
    from worker.session import WorkerSession
    from hydra.infra.ip_errors import IPRotationFailed

    async def fake_ensure(db, account, worker):
        raise IPRotationFailed("test")

    with patch("worker.session.BrowserSession"), \
         patch("worker.session.ensure_safe_ip", side_effect=fake_ensure):
        session = WorkerSession(
            profile_id="p1", account_id=42, device_id="DEV",
            account=type("A", (), {"id": 42})(),
            worker=type("W", (), {"id": 7, "ip_config": "{}"})(),
        )

        with pytest.raises(IPRotationFailed):
            await session.start(db=object())
