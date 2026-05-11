"""PR-A: WorkerSession 은 AccountSnapshot/WorkerConfig 로 동작.
ensure_safe_ip_from_snapshot 만 호출하고, ORM 객체에 의존하지 않는다.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from hydra.protocol import AccountSnapshot, WorkerConfig


def _snap(**overrides) -> AccountSnapshot:
    defaults = dict(
        id=42,
        gmail="alice@example.com",
        encrypted_password="ENC",
        adspower_profile_id="prof1",
    )
    defaults.update(overrides)
    return AccountSnapshot(**defaults)


@pytest.mark.asyncio
async def test_worker_session_calls_ensure_safe_ip_with_snapshot_args():
    """WorkerSession.start(db=..) calls ensure_safe_ip_from_snapshot with
    account_id + adb_device_id derived from envelope's worker_config."""
    from worker.session import WorkerSession

    calls = []

    async def fake_ensure(db, *, account_id, adb_device_id, cooldown_minutes=None):
        calls.append({"account_id": account_id, "adb_device_id": adb_device_id, "cooldown": cooldown_minutes})
        class Fake:
            id = 1
        return Fake()

    with patch("worker.session.BrowserSession") as BS, \
         patch("worker.session.ensure_safe_ip_from_snapshot", side_effect=fake_ensure):
        instance = MagicMock()
        instance.start = AsyncMock()
        instance.goto = AsyncMock()
        instance.page = None
        BS.return_value = instance

        session = WorkerSession(
            profile_id="p1",
            account_id=42,
            device_id="DEV_local_env",
            account_snapshot=_snap(id=42),
            worker_config=WorkerConfig(adb_device_id="DEV_from_envelope", ip_cooldown_minutes=10),
        )
        ok = await session.start(db=object())
        assert ok
        assert len(calls) == 1
        assert calls[0]["account_id"] == 42
        # envelope-supplied device_id wins over local env fallback
        assert calls[0]["adb_device_id"] == "DEV_from_envelope"
        assert calls[0]["cooldown"] == 10


@pytest.mark.asyncio
async def test_worker_session_skips_hook_when_no_db():
    """If db is not passed, session.start should proceed without IP rotation hook."""
    from worker.session import WorkerSession

    with patch("worker.session.BrowserSession") as BS, \
         patch("worker.session.ensure_safe_ip_from_snapshot") as mock_ensure:
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
    """IPRotationFailed from IP hook must bubble up, not be swallowed."""
    from worker.session import WorkerSession
    from hydra.infra.ip_errors import IPRotationFailed

    async def fake_ensure(db, *, account_id, adb_device_id, cooldown_minutes=None):
        raise IPRotationFailed("test")

    with patch("worker.session.BrowserSession"), \
         patch("worker.session.ensure_safe_ip_from_snapshot", side_effect=fake_ensure):
        session = WorkerSession(
            profile_id="p1",
            account_id=42,
            device_id="DEV",
            account_snapshot=_snap(),
            worker_config=WorkerConfig(adb_device_id="DEV"),
        )

        with pytest.raises(IPRotationFailed):
            await session.start(db=object())


@pytest.mark.asyncio
async def test_worker_session_falls_back_to_local_device_id():
    """If envelope.worker_config.adb_device_id is None, fall back to local device_id arg."""
    from worker.session import WorkerSession

    calls = []

    async def fake_ensure(db, *, account_id, adb_device_id, cooldown_minutes=None):
        calls.append(adb_device_id)
        class Fake:
            id = 1
        return Fake()

    with patch("worker.session.BrowserSession") as BS, \
         patch("worker.session.ensure_safe_ip_from_snapshot", side_effect=fake_ensure):
        instance = MagicMock()
        instance.start = AsyncMock()
        instance.goto = AsyncMock()
        instance.page = None
        BS.return_value = instance

        session = WorkerSession(
            profile_id="p1",
            account_id=42,
            device_id="DEV_local_env",
            account_snapshot=_snap(),
            worker_config=WorkerConfig(adb_device_id=None),  # envelope has no preference
        )
        await session.start(db=object())
        assert calls == ["DEV_local_env"]
