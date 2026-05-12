"""PR-D: WorkerSession 의 IP 흐름 — server endpoint 호출 only.

이전엔 ensure_safe_ip_from_snapshot (워커 로컬 DB) 을 mock 했음. 이제 server endpoint
호출하는 ensure_safe_ip_via_server 를 mock.
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
async def test_worker_session_calls_ensure_safe_ip_via_server():
    """WorkerSession.start() 가 ensure_safe_ip_via_server (server endpoint) 호출."""
    from worker.session import WorkerSession

    calls = []

    async def fake_ensure(client, *, account_id, adb_device_id, cooldown_minutes=None):
        calls.append({"account_id": account_id, "adb_device_id": adb_device_id, "cooldown": cooldown_minutes})
        return 999  # log_id

    server_client = MagicMock()
    with patch("worker.session.BrowserSession") as BS, \
         patch("worker.session.ensure_safe_ip_via_server", side_effect=fake_ensure):
        instance = MagicMock()
        instance.start = AsyncMock()
        instance.goto = AsyncMock()
        instance.page = None
        BS.return_value = instance

        session = WorkerSession(
            profile_id="p1",
            account_id=42,
            device_id="DEV_local",
            account_snapshot=_snap(id=42),
            worker_config=WorkerConfig(adb_device_id="DEV_envelope", ip_cooldown_minutes=10),
            server_client=server_client,
        )
        ok = await session.start()
        assert ok
        assert len(calls) == 1
        assert calls[0]["account_id"] == 42
        assert calls[0]["adb_device_id"] == "DEV_envelope"
        assert calls[0]["cooldown"] == 10
        assert session.ip_log_id == 999


@pytest.mark.asyncio
async def test_worker_session_skips_ip_when_no_server_client():
    """server_client 가 None 이면 IP 흐름 skip (테스트/dry-run 시나리오)."""
    from worker.session import WorkerSession

    with patch("worker.session.BrowserSession") as BS, \
         patch("worker.session.ensure_safe_ip_via_server") as mock_ensure:
        instance = MagicMock()
        instance.start = AsyncMock()
        instance.goto = AsyncMock()
        instance.page = None
        BS.return_value = instance

        session = WorkerSession(
            profile_id="p1", account_id=42, device_id="DEV",
            account_snapshot=_snap(),
            server_client=None,
        )
        ok = await session.start()
        assert ok
        mock_ensure.assert_not_called()


@pytest.mark.asyncio
async def test_worker_session_propagates_ip_rotation_failed():
    """IPRotationFailed 가 server endpoint 에서 raise 되면 그대로 propagate."""
    from worker.session import WorkerSession
    from hydra.infra.ip_errors import IPRotationFailed

    async def fake_ensure(client, *, account_id, adb_device_id, cooldown_minutes=None):
        raise IPRotationFailed("no_adb_device_configured")

    server_client = MagicMock()
    with patch("worker.session.BrowserSession"), \
         patch("worker.session.ensure_safe_ip_via_server", side_effect=fake_ensure):
        session = WorkerSession(
            profile_id="p1",
            account_id=42,
            device_id="DEV",
            account_snapshot=_snap(),
            worker_config=WorkerConfig(adb_device_id="DEV"),
            server_client=server_client,
        )
        with pytest.raises(IPRotationFailed):
            await session.start()


@pytest.mark.asyncio
async def test_worker_session_close_calls_end_ip_log():
    """세션 종료 시 server endpoint /ip-log/end 호출."""
    from worker.session import WorkerSession

    server_client = MagicMock()
    session = WorkerSession(
        profile_id="p1", account_id=1, account_snapshot=_snap(),
        server_client=server_client,
    )
    session.ip_log_id = 555  # 시작 시 받았다고 가정
    with patch("worker.session.end_ip_log_via_server") as mock_end:
        await session.close()
        mock_end.assert_called_once_with(server_client, 555)
