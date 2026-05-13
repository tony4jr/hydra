"""M1 상태 전이 엔진 (Task M1-1~M1-5).

task 완료/실패 시 account 상태를 전이시키고 다음 단계 태스크를 큐에 넣는다.
on_task_complete/on_task_fail 은 호출자 세션에 참여 (같은 트랜잭션, flush 만).
sweep_stuck_accounts 는 top-level scheduler 진입점 — 스스로 commit.
"""
from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from hydra.db.models import Account, Task

_ENRICH_CHILD_TYPES = ("reply", "like_boost")
_CHILD_DELAY_MINUTES = 5
_CHILD_DELAY_MAX_MINUTES = 30


def _json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_comment_id(result_raw: str | None) -> str:
    result = _json_dict(result_raw)
    for key in ("youtube_comment_id", "comment_id", "reply_id"):
        value = result.get(key)
        if value:
            return str(value).strip()
    return ""


def enrich_child_payloads_for_parent(
    parent_task_id: int,
    session: Session,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """comment/reply 완료 후 자식 reply/like_boost target payload 보강.

    parent result 에 댓글 id 가 없으면 자식은 실행해도 no-op 이므로 pending 자식을
    즉시 failed 로 닫는다. 호출자는 commit 책임을 가진다.
    """
    parent = session.get(Task, parent_task_id)
    stats = {"enriched": 0, "failed": 0, "skipped": 0}
    if parent is None or parent.task_type not in ("comment", "reply"):
        stats["skipped"] += 1
        return stats

    q = (
        session.query(Task)
        .filter(
            Task.parent_task_id == parent.id,
            Task.task_type.in_(_ENRICH_CHILD_TYPES),
            Task.status == "pending",
        )
    )
    if parent.campaign_id is not None:
        q = q.filter(Task.campaign_id == parent.campaign_id)

    children = q.all()
    if not children:
        return stats

    now = now or datetime.now(UTC)
    comment_id = _extract_comment_id(parent.result)
    if not comment_id:
        for child in children:
            child.status = "failed"
            child.error_message = "parent_comment_id_missing"
            child.completed_at = now
            stats["failed"] += 1
        session.flush()
        return stats

    for child in children:
        payload = _json_dict(child.payload)
        payload["target_comment_id"] = comment_id
        payload["target_selector"] = comment_id
        child.payload = json.dumps(payload, ensure_ascii=False)
        child.scheduled_at = now + timedelta(
            minutes=random.uniform(_CHILD_DELAY_MINUTES, _CHILD_DELAY_MAX_MINUTES)
        )
        stats["enriched"] += 1
    session.flush()
    return stats


def on_task_complete(task_id: int, session: Session) -> None:
    """task가 done 으로 커밋되기 직전에 호출. 같은 세션 공유."""
    task = session.get(Task, task_id)
    if task is None or task.account_id is None:
        return

    # T7 Circuit Breaker — 성공 시 카운터 리셋
    if task.worker_id is not None:
        reset_worker_failure_counter(task.worker_id, session)

    enrich_child_payloads_for_parent(task.id, session)

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
# 워커/인프라 귀속 에러: 계정 책임 아니므로 suspend 하지 않고 재시도 무한 (retry_count 증분 안 함)
# Why: 49계정 자동 suspended 사고 (orchestrator가 Session start failed를 계정 문제로 오해)
# How to apply: on_task_fail 진입 시 가장 먼저 검사; 매치되면 account 상태 전이 + retry_count 증가 모두 스킵
WORKER_ENVIRONMENT_ERROR_PATTERNS = (
    "session start failed",
    "local_worker_row_missing",
    "local_account_row_missing",
    "ip_rotation_failed",
    "adspower_open_failed",
    "adspower_api_error",
    "playwright_launch_failed",
    "browser_disconnected",
    "phase_timeout",   # PR-E: 단계별 timeout 도 워커-환경 책임 (계정 보호)
    "envelope_missing",
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


def _is_worker_environment_error(error_msg: str | None) -> bool:
    if not error_msg:
        return False
    norm = error_msg.lower().replace("_", "").replace("-", "").replace(" ", "")
    for p in WORKER_ENVIRONMENT_ERROR_PATTERNS:
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


def _suspend_account(account: Account, session: Session) -> None:
    """계정 정지 + PR-Kill suspend_guard 가 정확히 카운트 하도록 last_active_at 갱신.

    last_active_at 갱신은 'suspended 진입 시각'을 근사하는 marker — audit 테이블 신설 비용 회피.
    suspend_guard.collect_signals 가 status='suspended' AND last_active_at >= window 으로 신규 진입
    카운트한다.
    """
    account.status = "suspended"
    account.last_active_at = datetime.now(UTC).replace(tzinfo=None)
    session.flush()


def on_task_fail(task_id: int, session: Session) -> None:
    """task가 failed 로 커밋되기 직전 호출. 같은 세션 공유.

    PR-Kill v2: 모든 early return 경로에서 마지막에 suspend_guard.evaluate() 호출되도록
    try/finally 패턴. 어떤 종료 경로든 kill switch 평가 누락 안 함.
    """
    task = session.get(Task, task_id)
    if task is None or task.account_id is None:
        return

    # T7 Circuit Breaker — 워커 연속 실패 카운트
    if task.worker_id is not None:
        _trip_circuit_breaker_if_needed(task.worker_id, session)

    account = session.get(Account, task.account_id)
    if account is None:
        return

    try:
        if account.status in ("suspended", "banned", "retired"):
            return  # terminal — 더 이상 전이 없음

        # 워커/인프라 귀속 에러 → 계정 무책임. retry_count 증가 없이 같은 priority/type 으로 재큐.
        # circuit-breaker는 이미 위에서 워커 카운트 잡았으므로 워커 격리는 별도로 동작.
        if _is_worker_environment_error(task.error_message):
            session.add(Task(
                account_id=account.id,
                task_type=task.task_type,
                status="pending",
                priority=task.priority,
                retry_count=task.retry_count,  # 증가 안 함
                max_retries=task.max_retries,
                campaign_id=task.campaign_id,
                slot_id=task.slot_id,
                slot_label=task.slot_label,
                parent_task_id=task.parent_task_id,
                payload=task.payload,
                scheduled_at=task.scheduled_at,
            ))
            session.flush()
            return

        # T10: 영구 에러 → 재시도 없이 즉시 격리
        if _is_permanent_error(task.error_message):
            _suspend_account(account, session)
            return

        # T10: task_type 별 max_retries 차등.
        # 정책은 상한, task.max_retries 는 추가 하한 — min() 으로 결합.
        policy_max = _max_retries_for(task.task_type)
        explicit = task.max_retries if task.max_retries is not None else policy_max
        max_retries = min(explicit, policy_max)
        if task.retry_count >= max_retries:
            _suspend_account(account, session)
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
    finally:
        # PR-Kill: 어떤 종료 경로든 kill switch 평가. 이미 paused 이면 evaluate no-op.
        # evaluate 실패가 on_task_fail 전체 흐름을 막지 않도록 except 로 차단.
        try:
            from hydra.core import suspend_guard
            suspend_guard.evaluate(session=session)
        except Exception as e:
            from hydra.core.logger import get_logger
            get_logger("orchestrator").warning(f"suspend_guard.evaluate failed: {e}")


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
