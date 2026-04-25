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

    # T7 Circuit Breaker — 성공 시 카운터 리셋
    if task.worker_id is not None:
        reset_worker_failure_counter(task.worker_id, session)

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


# T7 Circuit Breaker 임계치 — 연속 N회 실패 시 워커 자동 pause
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_WINDOW_MINUTES = 10

# T10 태스크 종류별 재시도 정책
# 영구 실패 키워드: 재시도 0회, 즉시 계정 격리
PERMANENT_ERROR_PATTERNS = (
    "account suspended", "captcha_persistent", "profile_locked_elsewhere",
    "banned", "permanent",
)
# task_type → max_retries (None = 모델 기본값 사용)
TASK_RETRY_POLICY = {
    "comment": 1,           # 보수적 — 댓글 실패는 노출 위험
    "like": 3,              # 적극 재시도 — 영향 적음
    "watch_video": 2,
    "warmup": 5,            # 덜 중요 + 자연스러움 우선
    "onboarding_verify": 2,
    "create_account": 1,    # 비싼 작업
}


def _is_permanent_error(error_msg: str | None) -> bool:
    if not error_msg:
        return False
    # 공백/언더스코어/하이픈 제거 후 lower → 다양한 표기 대응
    norm = error_msg.lower().replace("_", "").replace("-", "").replace(" ", "")
    for p in PERMANENT_ERROR_PATTERNS:
        if p.lower().replace("_", "").replace("-", "").replace(" ", "") in norm:
            return True
    return False


def _max_retries_for(task_type: str, fallback: int = 3) -> int:
    return TASK_RETRY_POLICY.get(task_type, fallback)


def _trip_circuit_breaker_if_needed(worker_id: int, session: Session) -> None:
    """워커가 짧은 시간 내 N회 연속 실패하면 자동 pause."""
    from hydra.db.models import Worker
    from datetime import timedelta
    w = session.get(Worker, worker_id)
    if w is None or w.status == "paused":
        return
    w.consecutive_failures = (w.consecutive_failures or 0) + 1
    w.last_failure_at = datetime.now(UTC)

    # 윈도우 내인지 확인 (마지막 실패 이후 10분 넘었으면 카운터 리셋 의미)
    if w.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
        w.status = "paused"
        w.paused_reason = f"circuit-breaker: {w.consecutive_failures} consecutive failures"
    session.flush()


def reset_worker_failure_counter(worker_id: int, session: Session) -> None:
    """태스크 성공 시 호출 — 연속 실패 카운터 0 으로 리셋."""
    from hydra.db.models import Worker
    w = session.get(Worker, worker_id)
    if w is None:
        return
    if w.consecutive_failures > 0:
        w.consecutive_failures = 0
        session.flush()


def on_task_fail(task_id: int, session: Session) -> None:
    """task가 failed 로 커밋되기 직전 호출. 같은 세션 공유."""
    task = session.get(Task, task_id)
    if task is None or task.account_id is None:
        return

    # T7 Circuit Breaker — 워커 연속 실패 카운트
    if task.worker_id is not None:
        _trip_circuit_breaker_if_needed(task.worker_id, session)

    account = session.get(Account, task.account_id)
    if account is None:
        return

    if account.status in ("suspended", "banned", "retired"):
        return  # terminal — 더 이상 전이 없음

    # T10: 영구 에러 → 재시도 없이 즉시 격리
    if _is_permanent_error(task.error_message):
        account.status = "suspended"
        session.flush()
        return

    # T10: task_type 별 max_retries 차등.
    # 정책은 상한, task.max_retries 는 추가 하한 — min() 으로 결합.
    # 안티디텍션 위해 정책보다 더 retry 못 하게 하되, 명시적으로 더 적게 설정한 건 존중.
    policy_max = _max_retries_for(task.task_type)
    explicit = task.max_retries if task.max_retries is not None else policy_max
    max_retries = min(explicit, policy_max)
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
        max_retries=max_retries,
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
