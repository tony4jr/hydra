from datetime import datetime, UTC, timedelta


def _add_account(db, gmail):
    from hydra.db.models import Account
    a = Account(gmail=gmail, password="x", status="active")
    db.add(a)
    db.flush()
    return a


def _add_ip_log(db, account_id, ip, minutes_ago=0):
    from hydra.db.models import IpLog
    log = IpLog(
        account_id=account_id,
        ip_address=ip,
        device_id="test",
        started_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    db.add(log)
    db.flush()
    return log


def test_check_ip_available_true_when_no_log(db_session):
    from hydra.infra.ip import check_ip_available
    a = _add_account(db_session, "a@g.com")
    assert check_ip_available(db_session, "1.2.3.4", a.id) is True


def test_check_ip_available_true_for_same_account(db_session):
    from hydra.infra.ip import check_ip_available
    a = _add_account(db_session, "a@g.com")
    _add_ip_log(db_session, a.id, "1.2.3.4", minutes_ago=5)
    assert check_ip_available(db_session, "1.2.3.4", a.id) is True


def test_check_ip_available_false_for_other_account_within_cooldown(db_session):
    from hydra.infra.ip import check_ip_available
    a = _add_account(db_session, "a@g.com")
    b = _add_account(db_session, "b@g.com")
    _add_ip_log(db_session, a.id, "1.2.3.4", minutes_ago=10)
    assert check_ip_available(db_session, "1.2.3.4", b.id) is False


def test_check_ip_available_true_for_other_account_after_cooldown(db_session):
    from hydra.infra.ip import check_ip_available
    a = _add_account(db_session, "a@g.com")
    b = _add_account(db_session, "b@g.com")
    _add_ip_log(db_session, a.id, "1.2.3.4", minutes_ago=31)
    assert check_ip_available(db_session, "1.2.3.4", b.id) is True


def test_check_ip_available_custom_cooldown(db_session):
    from hydra.infra.ip import check_ip_available
    a = _add_account(db_session, "a@g.com")
    b = _add_account(db_session, "b@g.com")
    _add_ip_log(db_session, a.id, "1.2.3.4", minutes_ago=10)
    assert check_ip_available(db_session, "1.2.3.4", b.id,
                              cooldown_minutes=5) is True


import pytest


@pytest.mark.asyncio
async def test_rotate_and_verify_succeeds_on_first_attempt(db_session, monkeypatch):
    from hydra.infra import ip as ip_mod

    calls = []

    async def fake_shell(device_id, cmd):
        calls.append(cmd)
        return ""

    async def fake_get_ip(device_id):
        return "2.2.2.2" if len(calls) >= 2 else "1.1.1.1"

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(ip_mod, "_adb_shell", fake_shell)
    monkeypatch.setattr(ip_mod, "_get_current_ip", fake_get_ip)
    monkeypatch.setattr(ip_mod.asyncio, "sleep", fake_sleep)

    a = _add_account(db_session, "a@g.com")
    result = await ip_mod.rotate_and_verify(db_session, "DEV", a.id)
    assert result == "2.2.2.2"


@pytest.mark.asyncio
async def test_rotate_and_verify_retries_on_conflict(db_session, monkeypatch):
    from hydra.infra import ip as ip_mod

    toggles = {"n": 0}

    async def fake_shell(device_id, cmd):
        if "enable" in cmd:
            toggles["n"] += 1
        return ""

    sequence = iter(["1.1.1.1", "9.9.9.9", "2.2.2.2"])

    async def fake_get_ip(device_id):
        return next(sequence)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(ip_mod, "_adb_shell", fake_shell)
    monkeypatch.setattr(ip_mod, "_get_current_ip", fake_get_ip)
    monkeypatch.setattr(ip_mod.asyncio, "sleep", fake_sleep)

    a = _add_account(db_session, "a@g.com")
    b = _add_account(db_session, "b@g.com")
    _add_ip_log(db_session, a.id, "9.9.9.9", minutes_ago=1)
    db_session.commit()

    result = await ip_mod.rotate_and_verify(db_session, "DEV", b.id)
    assert result == "2.2.2.2"
    assert toggles["n"] == 2


@pytest.mark.asyncio
async def test_rotate_and_verify_raises_after_three_failures(db_session, monkeypatch):
    from hydra.infra import ip as ip_mod
    from hydra.infra.ip_errors import IPRotationFailed

    async def fake_shell(device_id, cmd):
        return ""

    async def fake_get_ip(device_id):
        return "1.1.1.1"

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(ip_mod, "_adb_shell", fake_shell)
    monkeypatch.setattr(ip_mod, "_get_current_ip", fake_get_ip)
    monkeypatch.setattr(ip_mod.asyncio, "sleep", fake_sleep)

    import hydra.infra.telegram as telegram
    monkeypatch.setattr(telegram, "warning", lambda *a, **k: None)

    a = _add_account(db_session, "a@g.com")

    with pytest.raises(IPRotationFailed):
        await ip_mod.rotate_and_verify(db_session, "DEV", a.id)
