"""PR-A B++: reschedule-ip-failure 경로의 ProfileLock 누수 차단.

Codex 최종 검토 발견: fail-closed ensure_safe_ip_from_snapshot 가
IPRotationFailed 던지면 워커가 reschedule-ip-failure 호출 → 기존 코드는
ProfileLock 해제 안 해서 account 영구 lock. 그 위에 task 자체도 running 으로
잡혀있어 다른 워커가 picked up 못 함.

이 테스트는 reschedule_task_for_ip_failure 가 commit 후 ProfileLock.released_at
+ worker_id None + started_at None 보장하는지 검증.
"""
from __future__ import annotations

from datetime import datetime, UTC

import pytest

from hydra.db import session as _db_session
from hydra.db.models import Account, Brand, ProfileLock, Task, Worker
from hydra.core.executor import reschedule_task_for_ip_failure


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Fresh SQLite for this test only."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from hydra.db.models import Base

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(_db_session, "engine", engine)
    monkeypatch.setattr(_db_session, "SessionLocal", Session)
    session = Session()
    yield session
    session.close()


def _make_brand(db) -> Brand:
    b = Brand(name="모렉신")
    db.add(b); db.flush()
    return b


def _make_acct(db, **overrides) -> Account:
    defaults = dict(
        gmail="test@example.com", password="ENC",
        adspower_profile_id="p1", status="active",
    )
    defaults.update(overrides)
    a = Account(**defaults)
    db.add(a); db.flush()
    return a


def _make_worker(db) -> Worker:
    w = Worker(name="pc-test", status="online", allow_campaign=True)
    db.add(w); db.flush()
    return w


def _make_task_running(db, account, worker, brand=None) -> Task:
    """Simulate post-fetch state: task=running, worker_id set, started_at set."""
    t = Task(
        account_id=account.id,
        task_type="comment",
        status="running",
        worker_id=worker.id,
        started_at=datetime.now(UTC),
        campaign_id=None,
        retry_count=0,
    )
    db.add(t); db.flush()
    pl = ProfileLock(
        account_id=account.id,
        worker_id=worker.id,
        task_id=t.id,
        adspower_profile_id=account.adspower_profile_id,
    )
    db.add(pl); db.flush()
    return t


def test_reschedule_releases_profile_lock(db_session):
    """ProfileLock.released_at must be set after reschedule."""
    db = db_session
    _make_brand(db)
    acct = _make_acct(db)
    worker = _make_worker(db)
    task = _make_task_running(db, acct, worker)
    db.commit()

    # sanity: lock active
    assert db.query(ProfileLock).filter(
        ProfileLock.task_id == task.id, ProfileLock.released_at.is_(None)
    ).count() == 1

    reschedule_task_for_ip_failure(db, task)

    # Lock released
    locks = db.query(ProfileLock).filter(ProfileLock.task_id == task.id).all()
    assert len(locks) == 1
    assert locks[0].released_at is not None


def test_reschedule_clears_worker_id_and_started_at(db_session):
    db = db_session
    _make_brand(db)
    acct = _make_acct(db)
    worker = _make_worker(db)
    task = _make_task_running(db, acct, worker)
    db.commit()

    reschedule_task_for_ip_failure(db, task)

    assert task.worker_id is None
    assert task.started_at is None


def test_reschedule_sets_task_back_to_pending_below_threshold(db_session, monkeypatch):
    db = db_session
    from hydra.core.config import settings
    monkeypatch.setattr(settings, "ip_rotation_task_retry_max", 5, raising=False)

    _make_brand(db)
    acct = _make_acct(db)
    worker = _make_worker(db)
    task = _make_task_running(db, acct, worker)
    db.commit()

    reschedule_task_for_ip_failure(db, task)

    assert task.status == "pending"
    assert task.retry_count == 1
    assert task.error_message == "ip_rotation_failed"
    assert task.scheduled_at is not None  # delayed retry


def test_reschedule_escalates_to_failed_above_threshold(db_session, monkeypatch):
    db = db_session
    from hydra.core.config import settings
    monkeypatch.setattr(settings, "ip_rotation_task_retry_max", 2, raising=False)

    _make_brand(db)
    acct = _make_acct(db)
    worker = _make_worker(db)
    task = _make_task_running(db, acct, worker)
    task.retry_count = 1  # one prior failure
    db.commit()

    reschedule_task_for_ip_failure(db, task)

    assert task.status == "failed"
    assert task.retry_count == 2
    # Lock still released even on terminal failure
    assert db.query(ProfileLock).filter(
        ProfileLock.task_id == task.id, ProfileLock.released_at.is_(None)
    ).count() == 0
