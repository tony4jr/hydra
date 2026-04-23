"""M1 상태 전이 엔진 (Task M1-1~M1-5).

task 완료/실패 시 account 상태를 전이시키고 다음 단계 태스크를 큐에 넣는다.
같은 세션에서 호출되어 하나의 트랜잭션으로 원자성 보장.
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
