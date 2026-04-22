"""Task 22 — 좀비 태스크 복구."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.zombie_cleanup import find_and_reset_zombies
from hydra.db.models import Account, Base, ProfileLock, Task, Worker


@pytest.fixture
def db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)
    yield TestSession
    engine.dispose()


def _seed_account_worker(session):
    s = session()
    acc = Account(gmail="z@x.com", adspower_profile_id="p-1", password="x", status="active")
    w = Worker(name="w-test", token_hash="hash")
    s.add_all([acc, w])
    s.commit()
    ids = (acc.id, w.id)
    s.close()
    return ids


def test_stale_running_reset_to_pending_and_lock_released(db):
    acc_id, w_id = _seed_account_worker(db)
    s = db()
    stale = datetime.now(UTC) - timedelta(minutes=45)
    t = Task(account_id=acc_id, task_type="test", status="running",
             started_at=stale, worker_id=w_id, priority="normal")
    s.add(t); s.flush()
    s.add(ProfileLock(account_id=acc_id, worker_id=w_id, task_id=t.id,
                      adspower_profile_id="p-1"))
    s.commit(); task_id = t.id
    s.close()

    n = find_and_reset_zombies(stale_minutes=30)
    assert n == 1

    s = db()
    t = s.get(Task, task_id)
    assert t.status == "pending"
    assert t.worker_id is None
    assert t.started_at is None
    lock = s.query(ProfileLock).filter_by(task_id=task_id).first()
    assert lock.released_at is not None
    s.close()


def test_fresh_running_not_touched(db):
    acc_id, w_id = _seed_account_worker(db)
    s = db()
    fresh = datetime.now(UTC) - timedelta(minutes=5)
    t = Task(account_id=acc_id, task_type="test", status="running",
             started_at=fresh, worker_id=w_id)
    s.add(t); s.commit(); task_id = t.id
    s.close()

    n = find_and_reset_zombies(stale_minutes=30)
    assert n == 0

    s = db()
    t = s.get(Task, task_id)
    assert t.status == "running"
    assert t.worker_id == w_id
    s.close()


def test_running_without_started_at_skipped(db):
    """started_at NULL 은 비교 불가 → skip."""
    acc_id, w_id = _seed_account_worker(db)
    s = db()
    t = Task(account_id=acc_id, task_type="test", status="running",
             started_at=None, worker_id=w_id)
    s.add(t); s.commit(); task_id = t.id
    s.close()

    n = find_and_reset_zombies(stale_minutes=30)
    assert n == 0

    s = db()
    assert s.get(Task, task_id).status == "running"
    s.close()


def test_pending_tasks_not_affected(db):
    acc_id, w_id = _seed_account_worker(db)
    s = db()
    t = Task(account_id=acc_id, task_type="test", status="pending",
             started_at=datetime.now(UTC) - timedelta(hours=5))
    s.add(t); s.commit(); task_id = t.id
    s.close()

    n = find_and_reset_zombies(stale_minutes=30)
    assert n == 0

    s = db()
    assert s.get(Task, task_id).status == "pending"
    s.close()
