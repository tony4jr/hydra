"""M1 상태 전이 엔진 (Task M1-1~M1-5).

task 완료/실패 시 account 상태를 전이시키고 다음 단계 태스크를 큐에 넣는다.
on_task_complete/on_task_fail 은 호출자 세션에 참여 (같은 트랜잭션, flush 만).
sweep_stuck_accounts 는 top-level scheduler 진입점 — 스스로 commit.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from hydra.db.models import Account, Task


def on_task_complete(task_id: int, session: Session) -> None:
    """task가 done 으로 커밋되기 직전에 호출. 같은 세션 공유."""
    task = session.get(Task, task_id)
    if task is None or task.account_id is None:
        return
    account = session.get(Account, task.account_id)
    if account is None:
        return

    if task.task_type == "onboarding_verify" and account.status == "registered":
        account.status = "warmup"
        account.warmup_day = 1
        account.onboard_completed_at = datetime.now(UTC)
        session.add(Task(
            account_id=account.id,
            task_type="warmup",
            status="pending",
            priority="normal",
        ))
        session.flush()

    if task.task_type == "warmup" and account.status == "warmup":
        if account.warmup_day < 3:
            account.warmup_day += 1
            session.add(Task(
                account_id=account.id,
                task_type="warmup",
                status="pending",
            ))
        else:
            # day 3 → active 졸업
            account.warmup_day = 4
            account.status = "active"
        session.flush()


def on_task_fail(task_id: int, session: Session) -> None:
    """task가 failed 로 커밋되기 직전 호출. 같은 세션 공유."""
    task = session.get(Task, task_id)
    if task is None or task.account_id is None:
        return
    account = session.get(Account, task.account_id)
    if account is None:
        return

    if account.status in ("suspended", "banned", "retired"):
        return  # terminal — 더 이상 전이 없음

    max_retries = task.max_retries if task.max_retries is not None else 3
    if task.retry_count >= max_retries:
        account.status = "suspended"
        session.flush()
        return

    # 재시도: 같은 task_type 으로 새 태스크 (retry_count + 1)
    session.add(Task(
        account_id=account.id,
        task_type=task.task_type,
        status="pending",
        priority=task.priority,
        retry_count=task.retry_count + 1,
        max_retries=task.max_retries,
    ))
    session.flush()


_ACTIVE_STATUSES = ("registered", "warmup")


def sweep_stuck_accounts(session: Session) -> int:
    """Top-level scheduler entry — pending/running 태스크 없는 활성 계정 재복구.

    Commit 책임: 이 함수는 on_task_complete/on_task_fail 과 달리 외부 트랜잭션에
    포함되지 않고 **스스로 commit** 한다 (background m1_tick 에서 직접 호출되는
    top-level 이기 때문). 호출자는 commit 하지 말 것.

    Returns: 복구한 account 수.
    """
    candidates = (
        session.query(Account)
        .filter(Account.status.in_(_ACTIVE_STATUSES))
        .all()
    )
    recovered = 0
    for acc in candidates:
        has_pending = (
            session.query(Task)
            .filter_by(account_id=acc.id, status="pending")
            .first()
            is not None
        )
        has_running = (
            session.query(Task)
            .filter_by(account_id=acc.id, status="running")
            .first()
            is not None
        )
        if has_pending or has_running:
            continue
        # 현재 상태에 맞는 태스크 재생성
        if acc.status == "registered":
            tt = "onboarding_verify"
        else:  # warmup
            tt = "warmup"
        session.add(Task(
            account_id=acc.id, task_type=tt,
            status="pending",
        ))
        recovered += 1
    if recovered:
        session.commit()
    return recovered
