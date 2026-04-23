"""Task M1-1~M1-5: 상태 전이 엔진."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hydra.core.orchestrator import on_task_complete, on_task_fail, sweep_stuck_accounts
from hydra.db.models import Account, Base, Task


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = S()
    yield s
    s.close()
    engine.dispose()


def test_onboarding_complete_promotes_to_warmup_day1(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="registered",
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="onboarding_verify",
        status="done", completed_at=datetime.now(UTC),
    )
    session.add(t)
    session.flush()

    on_task_complete(t.id, session)

    session.refresh(acc)
    assert acc.status == "warmup"
    assert acc.warmup_day == 1
    assert acc.onboard_completed_at is not None

    queued = session.query(Task).filter_by(
        account_id=acc.id, task_type="warmup", status="pending",
    ).first()
    assert queued is not None


def test_warmup_day1_complete_advances_to_day2(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=1,
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="warmup",
        status="done", completed_at=datetime.now(UTC),
    )
    session.add(t)
    session.flush()

    on_task_complete(t.id, session)

    session.refresh(acc)
    assert acc.warmup_day == 2
    assert acc.status == "warmup"
    nxt = session.query(Task).filter_by(
        account_id=acc.id, task_type="warmup", status="pending",
    ).first()
    assert nxt is not None


def test_warmup_day3_complete_promotes_to_active(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=3,
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="warmup",
        status="done", completed_at=datetime.now(UTC),
    )
    session.add(t)
    session.flush()

    on_task_complete(t.id, session)

    session.refresh(acc)
    assert acc.status == "active"
    assert acc.warmup_day == 4
    pending_warmup = session.query(Task).filter_by(
        account_id=acc.id, task_type="warmup", status="pending",
    ).count()
    assert pending_warmup == 0


def test_task_fail_below_threshold_re_enqueues(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=1,
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="warmup",
        status="failed", retry_count=1, max_retries=3,
    )
    session.add(t)
    session.flush()

    on_task_fail(t.id, session)

    session.refresh(acc)
    assert acc.status == "warmup"  # 유지
    nxt = session.query(Task).filter_by(
        account_id=acc.id, task_type="warmup", status="pending",
    ).first()
    assert nxt is not None
    assert nxt.retry_count == 2  # 증가된 값으로 새 태스크


def test_task_fail_at_max_retries_suspends_account(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=1,
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="warmup",
        status="failed", retry_count=3, max_retries=3,
    )
    session.add(t)
    session.flush()

    on_task_fail(t.id, session)

    session.refresh(acc)
    assert acc.status == "suspended"
    # 재시도 안 함
    pending = session.query(Task).filter_by(
        account_id=acc.id, status="pending",
    ).count()
    assert pending == 0


def test_task_fail_with_max_retries_zero_suspends_immediately(session):
    """max_retries=0 이면 즉시 suspended (0 or 3 collapse 방지)."""
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=1,
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="warmup",
        status="failed", retry_count=0, max_retries=0,
    )
    session.add(t)
    session.flush()

    on_task_fail(t.id, session)

    session.refresh(acc)
    assert acc.status == "suspended"
    pending = session.query(Task).filter_by(
        account_id=acc.id, status="pending",
    ).count()
    assert pending == 0


def test_sweep_detects_warmup_without_pending_task_and_reenqueues(session):
    """warmup 중인데 pending 태스크가 없으면 재enqueue."""
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=2,
    )
    session.add(acc)
    session.commit()

    count = sweep_stuck_accounts(session)
    assert count == 1

    nxt = session.query(Task).filter_by(
        account_id=acc.id, task_type="warmup", status="pending",
    ).first()
    assert nxt is not None


def test_sweep_ignores_accounts_with_pending_task(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=1,
    )
    session.add(acc)
    session.flush()
    session.add(Task(
        account_id=acc.id, task_type="warmup", status="pending",
    ))
    session.commit()

    count = sweep_stuck_accounts(session)
    assert count == 0


def test_sweep_ignores_active_and_suspended(session):
    session.add_all([
        Account(gmail="a@x.com", password="x", adspower_profile_id="p1",
                status="active", warmup_day=4),
        Account(gmail="b@x.com", password="x", adspower_profile_id="p2",
                status="suspended"),
        Account(gmail="c@x.com", password="x", adspower_profile_id="p3",
                status="retired"),
    ])
    session.commit()

    assert sweep_stuck_accounts(session) == 0


def test_task_fail_on_suspended_account_is_noop(session):
    """이미 suspended 된 계정은 fail 재진입에도 태스크 생성 금지."""
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="suspended", warmup_day=2,
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="warmup",
        status="failed", retry_count=1, max_retries=3,
    )
    session.add(t)
    session.flush()

    on_task_fail(t.id, session)

    session.refresh(acc)
    assert acc.status == "suspended"  # 유지
    pending = session.query(Task).filter_by(
        account_id=acc.id, status="pending",
    ).count()
    assert pending == 0


def test_sweep_reenqueues_onboarding_verify_for_registered(session):
    """registered 상태 account 에 태스크 없으면 onboarding_verify 재생성."""
    acc = Account(
        gmail="r@x.com", password="x",
        adspower_profile_id="p-r", status="registered",
    )
    session.add(acc)
    session.commit()

    assert sweep_stuck_accounts(session) == 1
    task = session.query(Task).filter_by(
        account_id=acc.id, task_type="onboarding_verify", status="pending",
    ).first()
    assert task is not None


def test_sweep_ignores_done_tasks_and_reenqueues(session):
    """오래된 done/failed 태스크만 있는 활성 계정은 새 태스크 재생성."""
    acc = Account(
        gmail="d@x.com", password="x",
        adspower_profile_id="p-d", status="warmup", warmup_day=2,
    )
    session.add(acc)
    session.flush()
    # 과거 태스크들 (done/failed) 만 있는 상태
    session.add_all([
        Task(account_id=acc.id, task_type="warmup", status="done"),
        Task(account_id=acc.id, task_type="warmup", status="failed"),
    ])
    session.commit()

    assert sweep_stuck_accounts(session) == 1
    pending = session.query(Task).filter_by(
        account_id=acc.id, status="pending",
    ).count()
    assert pending == 1
