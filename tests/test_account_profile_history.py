import json
import pytest
from datetime import datetime, UTC, timedelta
from sqlalchemy.exc import IntegrityError


def test_profile_history_row_can_be_inserted(db_session):
    from hydra.db.models import Account, AccountProfileHistory
    acc = Account(gmail="a@gmail.com", password="pw", status="registered")
    db_session.add(acc)
    db_session.flush()

    h = AccountProfileHistory(
        account_id=acc.id,
        worker_id=None,
        adspower_profile_id="k1bim9ga",
        fingerprint_snapshot=json.dumps({"any": "json"}),
        created_source="auto",
        device_hint="windows_heavy",
    )
    db_session.add(h)
    db_session.commit()

    got = db_session.query(AccountProfileHistory).filter_by(account_id=acc.id).one()
    assert got.adspower_profile_id == "k1bim9ga"
    assert got.retired_at is None
    assert got.created_source == "auto"


def test_adspower_profile_id_unique_constraint(db_session):
    """Two accounts cannot share the same AdsPower profile_id."""
    from hydra.db.models import Account
    a1 = Account(gmail="one@g.com", password="x",
                 adspower_profile_id="dup123", status="profile_set")
    a2 = Account(gmail="two@g.com", password="y",
                 adspower_profile_id="dup123", status="profile_set")
    db_session.add(a1)
    db_session.add(a2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_null_adspower_profile_id_allows_multiple(db_session):
    """NULL adspower_profile_id must be allowed for many accounts."""
    from hydra.db.models import Account
    a1 = Account(gmail="n1@g.com", password="x", status="registered")
    a2 = Account(gmail="n2@g.com", password="y", status="registered")
    db_session.add(a1)
    db_session.add(a2)
    db_session.commit()  # should NOT raise


def test_retire_then_recreate_keeps_history(db_session):
    """Retiring a profile then creating a new one leaves two history rows."""
    from hydra.db.models import Account, AccountProfileHistory
    acc = Account(gmail="r@g.com", password="x",
                  adspower_profile_id="old", status="profile_set")
    db_session.add(acc)
    db_session.flush()
    old = AccountProfileHistory(
        account_id=acc.id, adspower_profile_id="old",
        created_source="auto", device_hint="windows_heavy",
    )
    db_session.add(old)
    db_session.commit()

    # retire
    old.retired_at = datetime.now(UTC)
    old.retire_reason = "ghost"
    acc.adspower_profile_id = None
    db_session.commit()

    # recreate
    acc.adspower_profile_id = "new"
    new = AccountProfileHistory(
        account_id=acc.id, adspower_profile_id="new",
        created_source="auto", device_hint="windows_heavy",
    )
    db_session.add(new)
    db_session.commit()

    rows = (db_session.query(AccountProfileHistory)
            .filter_by(account_id=acc.id).order_by(AccountProfileHistory.id).all())
    assert len(rows) == 2
    assert rows[0].retired_at is not None
    assert rows[1].retired_at is None
