"""T7 Circuit Breaker — 연속 실패 시 워커 자동 pause."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hydra.core.orchestrator import (
    CIRCUIT_BREAKER_THRESHOLD,
    on_task_complete,
    on_task_fail,
)
from hydra.db.models import Account, Base, Task, Worker


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    engine.dispose()


def _create_worker_account_task(db) -> tuple[int, int, int]:
    w = Worker(name="w1", status="online")
    a = Account(gmail="a@x.com", password="enc", adspower_profile_id="p1", status="active")
    db.add(w); db.add(a); db.commit()
    db.refresh(w); db.refresh(a)

    t = Task(
        account_id=a.id, worker_id=w.id, task_type="comment",
        status="failed", retry_count=0, max_retries=3,
    )
    db.add(t); db.commit(); db.refresh(t)
    return w.id, a.id, t.id


def test_circuit_breaker_trips_after_threshold_failures(db):
    """N=THRESHOLD 회 연속 실패 시 워커 status=paused."""
    w_id, a_id, _ = _create_worker_account_task(db)

    # THRESHOLD 회 실패
    for i in range(CIRCUIT_BREAKER_THRESHOLD):
        t = Task(
            account_id=a_id, worker_id=w_id, task_type="comment",
            status="failed", retry_count=0,
        )
        db.add(t); db.commit(); db.refresh(t)
        on_task_fail(t.id, db)

    db.commit()
    w = db.get(Worker, w_id)
    assert w.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD
    assert w.status == "paused"
    assert "circuit-breaker" in (w.paused_reason or "")


def test_circuit_breaker_does_not_trip_below_threshold(db):
    w_id, a_id, _ = _create_worker_account_task(db)
    for i in range(CIRCUIT_BREAKER_THRESHOLD - 1):
        t = Task(
            account_id=a_id, worker_id=w_id, task_type="comment",
            status="failed", retry_count=0,
        )
        db.add(t); db.commit(); db.refresh(t)
        on_task_fail(t.id, db)

    db.commit()
    w = db.get(Worker, w_id)
    assert w.status == "online"
    assert w.consecutive_failures == CIRCUIT_BREAKER_THRESHOLD - 1


def test_task_complete_resets_failure_counter(db):
    w_id, a_id, _ = _create_worker_account_task(db)

    # 실패 누적
    for i in range(3):
        t = Task(
            account_id=a_id, worker_id=w_id, task_type="comment",
            status="failed", retry_count=0,
        )
        db.add(t); db.commit(); db.refresh(t)
        on_task_fail(t.id, db)
    db.commit()
    assert db.get(Worker, w_id).consecutive_failures == 3

    # 1 회 성공 → 리셋
    success = Task(
        account_id=a_id, worker_id=w_id, task_type="comment",
        status="done", retry_count=0,
    )
    db.add(success); db.commit(); db.refresh(success)
    on_task_complete(success.id, db)
    db.commit()
    assert db.get(Worker, w_id).consecutive_failures == 0


def test_already_paused_worker_does_not_double_count(db):
    """수동 pause 된 워커는 추가 실패해도 paused_reason 변경 X."""
    w = Worker(name="w1", status="paused", paused_reason="manual")
    a = Account(gmail="a@x.com", password="enc", adspower_profile_id="p1", status="active")
    db.add(w); db.add(a); db.commit()
    db.refresh(w); db.refresh(a)

    t = Task(
        account_id=a.id, worker_id=w.id, task_type="comment",
        status="failed", retry_count=0,
    )
    db.add(t); db.commit(); db.refresh(t)
    on_task_fail(t.id, db)
    db.commit()

    w_after = db.get(Worker, w.id)
    assert w_after.status == "paused"
    assert w_after.paused_reason == "manual"  # 변경 X
