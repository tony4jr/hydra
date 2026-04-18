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
