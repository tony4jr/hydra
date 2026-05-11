"""PR-Kill: suspend guard 단위 테스트.

scope:
- collect_signals 가 윈도우 안 task/account/error 만 카운트
- _exceeds 가 모든 임계 조건을 정확히 검사
- evaluate 가 임계 초과 시 paused=True + reason 기록
- evaluate 가 이미 paused 면 no-op (이중 발동 방지)
- reset 이 paused=False + reason 클리어
- env override 가 thresholds 반영
"""
from __future__ import annotations

import os
from datetime import datetime, UTC, timedelta

import pytest

from hydra.core import server_config as scfg
from hydra.core import suspend_guard
from hydra.db import session as _db_session
from hydra.db.models import Account, SystemConfig, Task, Worker, WorkerError


@pytest.fixture
def db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from hydra.db.models import Base

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(_db_session, "engine", engine)
    monkeypatch.setattr(_db_session, "SessionLocal", Session)
    monkeypatch.setattr(scfg, "SessionLocal", Session)
    s = Session()
    yield s
    s.close()


def _now_minus(minutes: int) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


def _mk_suspended_account(db, mins_ago: int) -> Account:
    a = Account(
        gmail=f"a{mins_ago}@x.com", password="ENC",
        status="suspended",
        last_active_at=_now_minus(mins_ago).replace(tzinfo=None),
    )
    db.add(a); db.flush()
    return a


def _mk_worker(db) -> Worker:
    w = Worker(name="pc-test", status="online", allow_campaign=True)
    db.add(w); db.flush()
    return w


def _mk_failed_task(db, account, mins_ago: int) -> Task:
    t = Task(
        account_id=account.id, task_type="comment",
        status="failed",
        completed_at=_now_minus(mins_ago).replace(tzinfo=None),
        retry_count=1,
    )
    db.add(t); db.flush()
    return t


def _mk_done_task(db, account, mins_ago: int) -> Task:
    t = Task(
        account_id=account.id, task_type="comment",
        status="done",
        completed_at=_now_minus(mins_ago).replace(tzinfo=None),
    )
    db.add(t); db.flush()
    return t


def _mk_phase_timeout_err(db, worker, mins_ago: int) -> WorkerError:
    t = _now_minus(mins_ago).replace(tzinfo=None)
    e = WorkerError(
        worker_id=worker.id,
        kind="phase_timeout",
        message="phase=cdp_connect elapsed=31s",
        occurred_at=t,
        received_at=t,
    )
    db.add(e); db.flush()
    return e


# ───── collect_signals ─────


def test_collect_signals_inside_window(db):
    a = _mk_suspended_account(db, mins_ago=2)
    w = _mk_worker(db)
    _mk_phase_timeout_err(db, w, mins_ago=3)
    _mk_failed_task(db, a, mins_ago=1)
    _mk_done_task(db, a, mins_ago=4)
    db.commit()

    sig = suspend_guard.collect_signals(db, window_minutes=5)
    assert sig.account_suspended == 1
    assert sig.phase_timeout == 1
    assert sig.task_failed == 1
    assert sig.task_attempts == 2
    assert sig.fail_rate_pct == 50.0


def test_collect_signals_excludes_outside_window(db):
    a = _mk_suspended_account(db, mins_ago=10)  # 윈도우 밖
    w = _mk_worker(db)
    _mk_phase_timeout_err(db, w, mins_ago=15)
    _mk_failed_task(db, a, mins_ago=12)
    db.commit()

    sig = suspend_guard.collect_signals(db, window_minutes=5)
    assert sig.account_suspended == 0
    assert sig.phase_timeout == 0
    assert sig.task_failed == 0


# ───── _exceeds ─────


def test_exceeds_account_suspended():
    sig = suspend_guard.GuardSignal(
        account_suspended=5, phase_timeout=0, task_failed=0, task_attempts=0, fail_rate_pct=0
    )
    reason = suspend_guard._exceeds(sig, suspend_guard.DEFAULT_THRESHOLDS)
    assert reason is not None
    assert "account_suspended" in reason


def test_exceeds_phase_timeout():
    sig = suspend_guard.GuardSignal(
        account_suspended=0, phase_timeout=15, task_failed=0, task_attempts=0, fail_rate_pct=0
    )
    reason = suspend_guard._exceeds(sig, suspend_guard.DEFAULT_THRESHOLDS)
    assert reason is not None
    assert "phase_timeout" in reason


def test_exceeds_task_failed():
    sig = suspend_guard.GuardSignal(
        account_suspended=0, phase_timeout=0, task_failed=30, task_attempts=30, fail_rate_pct=100.0
    )
    reason = suspend_guard._exceeds(sig, suspend_guard.DEFAULT_THRESHOLDS)
    assert reason is not None
    # task_failed 가 먼저 매치 (우선순위 순서)
    assert "task_failed" in reason


def test_exceeds_fail_rate_requires_min_attempts():
    """attempts 가 적으면 (노이즈) fail rate 임계 무시."""
    sig = suspend_guard.GuardSignal(
        account_suspended=0, phase_timeout=0,
        task_failed=2, task_attempts=2, fail_rate_pct=100.0,  # attempts < min
    )
    reason = suspend_guard._exceeds(sig, suspend_guard.DEFAULT_THRESHOLDS)
    assert reason is None  # min_attempts_for_rate=5 미달이라 통과


def test_exceeds_fail_rate_with_enough_attempts():
    sig = suspend_guard.GuardSignal(
        account_suspended=0, phase_timeout=0,
        task_failed=4, task_attempts=6, fail_rate_pct=66.7,
    )
    reason = suspend_guard._exceeds(sig, suspend_guard.DEFAULT_THRESHOLDS)
    assert reason is not None
    assert "fail_rate" in reason


def test_safe_signals_no_trip():
    sig = suspend_guard.GuardSignal(
        account_suspended=1, phase_timeout=3, task_failed=5, task_attempts=20, fail_rate_pct=25.0
    )
    reason = suspend_guard._exceeds(sig, suspend_guard.DEFAULT_THRESHOLDS)
    assert reason is None


# ───── evaluate ─────


def test_evaluate_safe(db):
    """안전 시그널 → no-op, paused 변화 없음."""
    scfg.set_paused(False, session=db); db.commit()
    a = _mk_suspended_account(db, mins_ago=2)
    _mk_failed_task(db, a, mins_ago=1)
    db.commit()

    reason = suspend_guard.evaluate(session=db, notify=False)
    db.commit()
    assert reason is None
    assert scfg.is_paused(session=db) is False
    assert suspend_guard.get_kill_reason(session=db) is None


def test_evaluate_trips_on_excess(db):
    """임계 초과 → paused=True + reason 기록."""
    scfg.set_paused(False, session=db); db.commit()
    # account_suspended 4건 > threshold 3
    for i in range(4):
        _mk_suspended_account(db, mins_ago=i + 1)
    db.commit()

    reason = suspend_guard.evaluate(session=db, notify=False)
    db.commit()
    assert reason is not None
    assert scfg.is_paused(session=db) is True
    saved = suspend_guard.get_kill_reason(session=db)
    assert saved is not None
    assert "account_suspended" in saved


def test_evaluate_skips_when_already_paused(db):
    """이미 paused → no-op (이중 발동 방지)."""
    scfg.set_paused(True, session=db); db.commit()
    # 충분히 많은 사고를 만들어도 트립 메시지 추가 안 됨.
    for i in range(10):
        _mk_suspended_account(db, mins_ago=i + 1)
    db.commit()

    reason = suspend_guard.evaluate(session=db, notify=False)
    assert reason is None  # skip
    # reason 이 기록 안 됨 (이미 paused 라 evaluate 자체가 skip)
    assert suspend_guard.get_kill_reason(session=db) is None


def test_reset_clears_paused_and_reason(db):
    scfg.set_paused(True, session=db)
    suspend_guard.set_kill_reason("test reason", session=db)
    db.commit()
    assert scfg.is_paused(session=db) is True
    assert suspend_guard.get_kill_reason(session=db) == "test reason"

    suspend_guard.reset(session=db)
    db.commit()
    assert scfg.is_paused(session=db) is False
    assert suspend_guard.get_kill_reason(session=db) is None


# ───── env override ─────


def test_env_override_thresholds(monkeypatch):
    monkeypatch.setenv("HYDRA_KILL_ACCOUNT_SUSPENDED_IN_WINDOW", "10")
    monkeypatch.setenv("HYDRA_KILL_FAIL_RATE_PCT", "75.0")
    thr = suspend_guard._load_thresholds()
    assert thr["account_suspended_in_window"] == 10
    assert thr["fail_rate_pct"] == 75.0
    # untouched
    assert thr["phase_timeout_in_window"] == suspend_guard.DEFAULT_THRESHOLDS["phase_timeout_in_window"]


def test_env_override_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("HYDRA_KILL_ACCOUNT_SUSPENDED_IN_WINDOW", "not-a-number")
    thr = suspend_guard._load_thresholds()
    # default 유지
    assert thr["account_suspended_in_window"] == suspend_guard.DEFAULT_THRESHOLDS["account_suspended_in_window"]


# ───── 통합 — on_task_fail 모든 경로에서 evaluate 호출 검증 ─────


def _mk_active_account(db) -> Account:
    a = Account(gmail=f"active{db.query(Account).count()}@x.com", password="ENC", status="active")
    db.add(a); db.flush()
    return a


def _mk_running_task(db, account, error_message=None, retry_count=0, max_retries=1) -> Task:
    t = Task(
        account_id=account.id,
        task_type="comment",
        status="running",
        error_message=error_message,
        retry_count=retry_count,
        max_retries=max_retries,
    )
    db.add(t); db.flush()
    return t


def test_on_task_fail_permanent_error_path_triggers_kill_switch(db):
    """permanent error → suspend account + kill switch evaluate.
    3번째 계정 suspend 가 임계 도달 시 kill switch 발동."""
    from hydra.core.orchestrator import on_task_fail
    scfg.set_paused(False, session=db); db.commit()

    # 이미 윈도우 안에 2개 suspended account (직접 last_active_at 세팅).
    for i in range(2):
        a = Account(
            gmail=f"prev{i}@x.com", password="ENC", status="suspended",
            last_active_at=_now_minus(1).replace(tzinfo=None),
        )
        db.add(a)
    db.flush()
    db.commit()

    # 3번째 fail — permanent error 로 suspend → 임계 3 도달.
    new_acct = _mk_active_account(db)
    task = _mk_running_task(db, new_acct, error_message="account suspended permanent")
    db.commit()
    on_task_fail(task.id, db)
    db.commit()

    assert new_acct.status == "suspended"
    assert scfg.is_paused(session=db) is True  # kill switch 발동
    assert "account_suspended" in (suspend_guard.get_kill_reason(session=db) or "")


def test_on_task_fail_max_retry_path_triggers_evaluate(db):
    """max retry → suspend account + evaluate 호출 (finally 패턴).
    이미 paused=False 에서 시작, 3번째 suspend 로 임계 충족."""
    from hydra.core.orchestrator import on_task_fail
    scfg.set_paused(False, session=db); db.commit()
    for i in range(2):
        a = Account(
            gmail=f"prev{i}@x.com", password="ENC", status="suspended",
            last_active_at=_now_minus(1).replace(tzinfo=None),
        )
        db.add(a)
    db.flush(); db.commit()

    new_acct = _mk_active_account(db)
    # retry_count >= max → suspend 경로
    task = _mk_running_task(db, new_acct, retry_count=1, max_retries=1)
    db.commit()
    on_task_fail(task.id, db)
    db.commit()

    assert new_acct.status == "suspended"
    assert scfg.is_paused(session=db) is True


def test_on_task_fail_worker_env_error_does_not_suspend(db):
    """워커 환경 에러 → 계정 suspend 안 함. evaluate 는 호출되지만 account_suspended 증가 안 함."""
    from hydra.core.orchestrator import on_task_fail
    scfg.set_paused(False, session=db); db.commit()

    new_acct = _mk_active_account(db)
    task = _mk_running_task(db, new_acct, error_message="Session start failed")
    db.commit()
    on_task_fail(task.id, db)
    db.commit()

    assert new_acct.status == "active"  # 보호됨
    assert scfg.is_paused(session=db) is False  # kill switch X
    # 새 재큐 task 생성됨 (retry_count 증가 없이)
    requeued = db.query(Task).filter(
        Task.account_id == new_acct.id, Task.status == "pending"
    ).all()
    assert len(requeued) == 1
    assert requeued[0].retry_count == 0


def test_on_task_fail_retry_path_does_not_trip_unless_threshold(db):
    """retry 경로는 suspend 안 만들므로 단독으로는 kill switch 발동 X."""
    from hydra.core.orchestrator import on_task_fail
    scfg.set_paused(False, session=db); db.commit()

    new_acct = _mk_active_account(db)
    task = _mk_running_task(db, new_acct, retry_count=0, max_retries=3)
    db.commit()
    on_task_fail(task.id, db)
    db.commit()

    assert new_acct.status == "active"
    assert scfg.is_paused(session=db) is False
    # retry task 1개 생성
    retries = db.query(Task).filter(
        Task.account_id == new_acct.id, Task.status == "pending"
    ).all()
    assert len(retries) == 1
    assert retries[0].retry_count == 1
