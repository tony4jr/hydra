"""태스크 큐 API v2 — fetch (SKIP LOCKED), complete, fail.

Legacy `/api/tasks/fetch`, `/complete`, `/fail` (hydra.api.tasks) 는 공존 유지 —
신규 워커는 `/api/tasks/v2/*` 사용. Phase 1d 전환 완료 후 legacy 제거 예정.

동시성 보장:
- PG: `FOR UPDATE SKIP LOCKED` + ProfileLock UNIQUE partial index
- SQLite (dev): 단순 SELECT + insert (ProfileLock UNIQUE 가 1차 방어)
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from sqlalchemy import func

from hydra.db import session as _db_session
from hydra.db.models import (
    Account, ActionLog, ProfileLock, Task, Worker, WorkerProgress, WorkerSession,
)
from hydra.protocol import (
    AccountSnapshot, SessionHeartbeat, TaskEnvelope, TaskProgress, WorkerConfig,
)
from hydra.services.account_limits import can_execute_task
from hydra.web.routes.worker_api import worker_auth


# legacy task_service 와 동일한 정의 — 워커 역할 분리 가드용
PREPARATION_TYPES = {"login", "channel_setup", "warmup", "onboard"}


def _role_allows(worker: Worker, task_type: str) -> bool:
    """Worker.allow_preparation / allow_campaign 가드.

    None 이면 default True (안전). 모델 default 가 True 인 컬럼에 NULL 이 들어가는
    회귀 방지.
    """
    if task_type in PREPARATION_TYPES:
        # allow_preparation 가 명시적으로 False 일 때만 거절
        return worker.allow_preparation is not False
    return worker.allow_campaign is not False


def _parse_allowed(allowed_json: str | None) -> list[str]:
    """Worker.allowed_task_types (JSON 문자열) → list[str].
    파싱 실패 시 안전 기본값 ['*'] (wildcard).
    """
    if not allowed_json:
        return ["*"]
    try:
        parsed = json.loads(allowed_json)
    except (json.JSONDecodeError, TypeError):
        return ["*"]
    if not isinstance(parsed, list):
        return ["*"]
    return [str(x) for x in parsed]


def _is_task_allowed(task_type: str, allowed: list[str]) -> bool:
    return "*" in allowed or task_type in allowed

router = APIRouter()


_AUTO_ASSIGN_TYPES = {"comment", "reply", "like", "like_boost", "subscribe"}


def _auto_assign_account(db, task: "Task") -> bool:
    """Assign an idle active Account to a pending task that has no account_id.

    Picked account (LRU + 한도):
      - status = 'active', not in open ProfileLock, not in identity_challenge cooldown
      - 오늘 같은 카테고리 액션 수가 daily limit 미만 (hard filter; >=100% 제외)
      - 정렬: 1) 오늘 액션 수 ASC (load balancing) 2) last_active_at ASC (LRU)
      - PG: FOR UPDATE SKIP LOCKED 로 다중 워커 동시 선택 방지

    한도 비율(70% 등) hard reject 안 함 — starvation 방지. 자연 정렬로 충분.
    """
    if task.account_id:
        return True
    if task.task_type not in _AUTO_ASSIGN_TYPES:
        return True  # Other task types may legitimately have no account_id

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    dialect = db.bind.dialect.name

    # task_type 카테고리에 따라 카운트할 ActionLog.action_type + 적용할 limit 컬럼 분기.
    # ActionType enum (core/enums.py:126): COMMENT/REPLY/LIKE_VIDEO/LIKE_COMMENT
    if task.task_type in ("like", "like_boost"):
        relevant_types = ("like_video", "like_comment")
        limit_col = Account.daily_like_limit
    else:  # comment, reply, subscribe — 댓글 카운트로 통일
        relevant_types = ("comment", "reply")
        limit_col = Account.daily_comment_limit

    today_actions_sub = (
        db.query(
            ActionLog.account_id.label("acc_id"),
            func.count().label("today_n"),
        )
        .filter(
            ActionLog.created_at >= today_start,
            ActionLog.action_type.in_(relevant_types),  # fix: ActionLog.type → action_type
        )
        .group_by(ActionLog.account_id)
        .subquery()
    )
    today_n = func.coalesce(today_actions_sub.c.today_n, 0)

    q = (
        db.query(Account)
        .outerjoin(today_actions_sub, Account.id == today_actions_sub.c.acc_id)
        .filter(
            Account.status == "active",
            ~Account.id.in_(
                db.query(ProfileLock.account_id)
                .filter(ProfileLock.released_at.is_(None))
            ),
        )
        .filter(
            (Account.identity_challenge_until.is_(None))
            | (Account.identity_challenge_until <= now)
        )
        # 한도 100% 도달한 계정 제외 (단, limit_col 이 NULL 인 경우는 통과)
        .filter((limit_col.is_(None)) | (today_n < limit_col))
        .order_by(
            today_n.asc(),
            Account.last_active_at.asc().nullsfirst(),
        )
    )
    if dialect == "postgresql":
        q = q.with_for_update(of=Account, skip_locked=True)
    available = q.first()
    if not available:
        return False
    task.account_id = available.id
    return True


# PR-A B++:
# - role pre-filter: 워커 role(allow_preparation/allow_campaign) 과 일치하지 않는
#   task_type 은 LIMIT 점유 못 하도록 SQL 단계에서 제외. 어제 사고 — pc-01 이
#   allow_preparation=False 인데 warmup task 가 scheduled_at NULLS FIRST 정렬로
#   LIMIT 10 을 점유해 campaign task 가 도달하지 못한 회귀 방지.
# - NULLS LAST: 미정렬 scheduled_at(NULL) 은 뒤로 — explicit 시간 잡힌 task 가 우선.
_PREPARATION_SQL_TUPLE = "('login', 'channel_setup', 'warmup', 'onboard')"
_FETCH_SQL_PG = text(f"""
    SELECT t.id
      FROM tasks t
      LEFT JOIN accounts a ON a.id = t.account_id
     WHERE t.status = 'pending'
       AND (t.scheduled_at IS NULL OR t.scheduled_at <= NOW())
       AND (
         (
           t.account_id IS NOT NULL
           AND a.adspower_profile_id IS NOT NULL
           AND t.account_id NOT IN (
             SELECT account_id FROM profile_locks WHERE released_at IS NULL
           )
         )
         OR t.account_id IS NULL
       )
       -- role pre-filter — 워커가 처리 못 할 task 는 후보에서 제외.
       AND (
         (:allow_prep AND t.task_type IN {_PREPARATION_SQL_TUPLE})
         OR (:allow_camp AND t.task_type NOT IN {_PREPARATION_SQL_TUPLE})
       )
     ORDER BY
       CASE t.priority
         WHEN 'urgent' THEN 4
         WHEN 'high' THEN 3
         WHEN 'normal' THEN 2
         WHEN 'low' THEN 1
         ELSE 2
       END DESC,
       t.scheduled_at ASC NULLS LAST,
       t.id ASC
     LIMIT 10
     FOR UPDATE OF t SKIP LOCKED
""")

_FETCH_SQL_SQLITE = text(f"""
    SELECT t.id
      FROM tasks t
      LEFT JOIN accounts a ON a.id = t.account_id
     WHERE t.status = 'pending'
       AND (t.scheduled_at IS NULL OR t.scheduled_at <= datetime('now'))
       AND (
         (
           t.account_id IS NOT NULL
           AND a.adspower_profile_id IS NOT NULL
           AND t.account_id NOT IN (
             SELECT account_id FROM profile_locks WHERE released_at IS NULL
           )
         )
         OR t.account_id IS NULL
       )
       AND (
         (:allow_prep AND t.task_type IN {_PREPARATION_SQL_TUPLE})
         OR (:allow_camp AND t.task_type NOT IN {_PREPARATION_SQL_TUPLE})
       )
     ORDER BY
       CASE t.priority
         WHEN 'urgent' THEN 4
         WHEN 'high' THEN 3
         WHEN 'normal' THEN 2
         WHEN 'low' THEN 1
         ELSE 2
       END DESC,
       -- SQLite: NULL is "smallest", but we want it last → CASE-coalesce.
       CASE WHEN t.scheduled_at IS NULL THEN 1 ELSE 0 END ASC,
       t.scheduled_at ASC,
       t.id ASC
     LIMIT 10
""")


@router.post("/fetch")
def fetch_tasks(worker: Worker = Depends(worker_auth)) -> dict:
    # PR-A B++: paused worker 가드 (legacy fetch_tasks 패리티 회복).
    # 어제 사고 — mac-dryrun 이 status=paused 인데 v2/fetch 에 가드가 없어
    # task 가로채고 실세션 실패 → 계정 mass suspended 트리거.
    if worker.status == "paused":
        return {"tasks": []}

    db = _db_session.SessionLocal()
    try:
        dialect = db.bind.dialect.name
        q = _FETCH_SQL_PG if dialect == "postgresql" else _FETCH_SQL_SQLITE
        # SQL role pre-filter — 워커 권한 binding
        params = {
            "allow_prep": bool(worker.allow_preparation),
            "allow_camp": bool(worker.allow_campaign),
        }
        # 양쪽 다 False 면 후보 0 — 일찍 종료해서 SQL 도 안 때림.
        if not params["allow_prep"] and not params["allow_camp"]:
            return {"tasks": []}
        rows = db.execute(q, params).fetchall()  # 최대 10개 후보
        if not rows:
            return {"tasks": []}

        # Task 37: allowed_task_types 필터 (wildcard 포함)
        allowed = _parse_allowed(worker.allowed_task_types)

        task = None
        for (tid,) in rows:
            candidate = db.get(Task, tid)
            if candidate is None or candidate.status != "pending":
                continue
            if not _is_task_allowed(candidate.task_type, allowed):
                continue
            # 워커 역할(allow_preparation/allow_campaign) 가드 — legacy 와 동일 정책.
            if not _role_allows(worker, candidate.task_type):
                continue
            # Auto-assign account_id for unassigned campaign/scenario tasks.
            # Skips candidate if no idle active account is available right now —
            # next fetch round will retry once a worker frees an account.
            if not _auto_assign_account(db, candidate):
                continue
            # 일일/주간 한도 가드 — legacy 에서 빠진 채로 v2 만 돌 때 한도 초과 위험.
            # 가용 계정이 있어도 그 계정이 한도 초과면 skip 하고 다음 task 시도.
            if candidate.account_id:
                allowed_now, _reason = can_execute_task(
                    db, candidate.account_id, candidate.task_type
                )
                if not allowed_now:
                    continue
            task = candidate
            break

        if task is None:
            return {"tasks": []}

        account = db.get(Account, task.account_id)
        if account is None or not account.adspower_profile_id:
            # Defensive: race against another worker assigning + freeing
            return {"tasks": []}
        task.status = "running"
        task.worker_id = worker.id
        task.started_at = datetime.now(UTC)

        db.add(ProfileLock(
            account_id=task.account_id,
            worker_id=worker.id,
            task_id=task.id,
            adspower_profile_id=account.adspower_profile_id,
        ))
        db.commit()

        # PR-A: TaskEnvelope — self-contained dispatch. Worker must not query local
        # Account/Worker tables. Server is source of truth.
        # Transitional: keep legacy flat fields (id, account_id, ..., account_snapshot)
        # alongside `envelope` so old workers still parse the response.
        account_snapshot = AccountSnapshot(
            id=account.id,
            gmail=account.gmail,
            encrypted_password=account.password,
            recovery_email=account.recovery_email,
            adspower_profile_id=account.adspower_profile_id,
            persona=account.persona,
            encrypted_totp_secret=account.totp_secret,
            status=account.status,
            ipp_flagged=account.ipp_flagged,
            youtube_channel_id=account.youtube_channel_id,
        )
        ip_config_data: dict = {}
        if worker.ip_config:
            try:
                ip_config_data = json.loads(worker.ip_config)
            except (json.JSONDecodeError, TypeError):
                ip_config_data = {}
        worker_config = WorkerConfig(
            adb_device_id=ip_config_data.get("adb_device_id"),
        )
        envelope = TaskEnvelope(
            task_id=task.id,
            task_type=task.task_type,
            priority=task.priority or "normal",
            payload=task.payload,
            account=account_snapshot,
            worker_config=worker_config,
        )
        envelope_dump = envelope.model_dump(mode="json")
        return {"tasks": [{
            # Legacy flat fields — keep for transitional compatibility.
            "id": task.id,
            "account_id": task.account_id,
            "adspower_profile_id": account.adspower_profile_id,
            "task_type": task.task_type,
            "payload": task.payload,
            "priority": task.priority,
            "account_snapshot": envelope_dump["account"],
            # New canonical shape — envelope-based workers parse this.
            "envelope": envelope_dump,
        }]}
    finally:
        db.close()


class TaskCompleteRequest(BaseModel):
    task_id: int
    result: str | None = None


def _release_lock(db, task_id: int) -> None:
    lock = (
        db.query(ProfileLock)
        .filter_by(task_id=task_id, released_at=None)
        .first()
    )
    if lock is not None:
        lock.released_at = datetime.now(UTC)


@router.post("/complete")
def complete(
    req: TaskCompleteRequest,
    worker: Worker = Depends(worker_auth),
) -> dict:
    db = _db_session.SessionLocal()
    try:
        t = db.get(Task, req.task_id)
        if t is None:
            raise HTTPException(404, "task not found")
        if t.worker_id != worker.id:
            raise HTTPException(403, "task not owned by this worker")
        t.status = "done"
        t.completed_at = datetime.now(UTC)
        t.result = req.result
        _release_lock(db, t.id)
        # M1-7: 상태 전이 훅 — 같은 트랜잭션에서
        from hydra.core.orchestrator import on_task_complete
        on_task_complete(t.id, db)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


class AccountCreationResult(BaseModel):
    gmail: str
    encrypted_password: str
    adspower_profile_id: str
    persona: dict = {}
    recovery_email: str | None = None
    encrypted_totp_secret: str | None = None
    youtube_channel_id: str | None = None
    phone_number: str | None = None
    fingerprint_snapshot: str | None = None


@router.post("/{task_id}/result/account-created")
def account_created(
    task_id: int,
    req: AccountCreationResult,
    worker: Worker = Depends(worker_auth),
) -> dict:
    """create_account 태스크의 결과 업로드 — 새 Account row 생성 + task 완료.

    요구사항:
    - 소유 워커만 (task.worker_id == worker.id)
    - task_type == "create_account"
    - gmail / adspower_profile_id 중복 시 409
    원자적 커밋: Account INSERT + Task UPDATE + Lock release 한 트랜잭션.
    """
    import json as _json

    db = _db_session.SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task is None:
            raise HTTPException(404, "task not found")
        if task.worker_id != worker.id:
            raise HTTPException(403, "task not owned by this worker")
        if task.task_type != "create_account":
            raise HTTPException(400, "not a create_account task")

        if db.query(Account).filter_by(gmail=req.gmail).first() is not None:
            raise HTTPException(409, f"gmail already exists: {req.gmail}")
        if db.query(Account).filter_by(
            adspower_profile_id=req.adspower_profile_id
        ).first() is not None:
            raise HTTPException(
                409,
                f"adspower_profile_id already exists: {req.adspower_profile_id}",
            )

        account = Account(
            gmail=req.gmail,
            password=req.encrypted_password,  # 이미 Fernet 암호화된 상태로 저장
            recovery_email=req.recovery_email,
            adspower_profile_id=req.adspower_profile_id,
            youtube_channel_id=req.youtube_channel_id,
            phone_number=req.phone_number,
            totp_secret=req.encrypted_totp_secret,
            persona=_json.dumps(req.persona, ensure_ascii=False) if req.persona else None,
            status="registered",
        )
        db.add(account)
        db.flush()  # id 필요

        task.account_id = account.id
        task.status = "done"
        task.completed_at = datetime.now(UTC)
        task.result = _json.dumps({"created_account_id": account.id})
        _release_lock(db, task.id)
        db.commit()

        return {"ok": True, "account_id": account.id}
    finally:
        db.close()


class TaskFailRequest(BaseModel):
    task_id: int
    error: str
    screenshot_url: str | None = None


@router.post("/fail")
def fail(
    req: TaskFailRequest,
    worker: Worker = Depends(worker_auth),
) -> dict:
    db = _db_session.SessionLocal()
    try:
        t = db.get(Task, req.task_id)
        if t is None:
            raise HTTPException(404, "task not found")
        if t.worker_id != worker.id:
            raise HTTPException(403, "task not owned by this worker")
        t.status = "failed"
        t.completed_at = datetime.now(UTC)
        t.error_message = req.error
        _release_lock(db, t.id)
        # M1-7: 실패 전이 훅
        from hydra.core.orchestrator import on_task_fail
        on_task_fail(t.id, db)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# ───────── PR-C: phase progress + session heartbeat endpoints ─────────
# Router prefix 가 이미 /api/tasks/v2 라서 route path 는 /progress, /session-heartbeat 로만.

@router.post("/progress")
def report_progress(
    progress: TaskProgress,
    worker: Worker = Depends(worker_auth),
) -> dict:
    """워커가 phase 변경 또는 30초 heartbeat 마다 호출.

    - is_phase_change=True → worker_progress INSERT + tasks UPDATE
    - is_phase_change=False → tasks UPDATE only (heartbeat)
    소유권 검증 (PR-C v2 — Codex 검토):
      - task_id 가 있으면 task.worker_id == worker.id 강제 (NULL 우회 차단)
      - 위반 시 409 (task_not_claimed) — claim 안 된 task progress 주입 막음
    """
    db = _db_session.SessionLocal()
    try:
        if progress.task_id is not None:
            t = db.get(Task, progress.task_id)
            if t is None:
                raise HTTPException(404, "task not found")
            # PR-C v2: NULL 우회 차단. progress 는 claim API 가 아니므로 worker_id 가
            # 박혀있어야만 보고 허용.
            if t.worker_id is None:
                raise HTTPException(409, "task_not_claimed: cannot report progress on unclaimed task")
            if t.worker_id != worker.id:
                raise HTTPException(403, "task not owned by this worker")
            t.last_progress_at = datetime.now(UTC)
            t.last_phase = progress.phase
            t.session_uuid = progress.session_uuid

        if progress.is_phase_change:
            db.add(WorkerProgress(
                session_uuid=progress.session_uuid,
                task_id=progress.task_id,
                worker_id=worker.id,
                attempt_no=progress.attempt_no,
                sequence_no=progress.sequence_no,
                phase=progress.phase,
                message=progress.message,
            ))

        # session heartbeat 도 동시에 갱신.
        sess = (
            db.query(WorkerSession)
            .filter(WorkerSession.session_uuid == progress.session_uuid)
            .first()
        )
        if sess is not None:
            if sess.worker_id is not None and sess.worker_id != worker.id:
                raise HTTPException(403, "session not owned by this worker")
            sess.last_heartbeat_at = datetime.now(UTC)

        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/session-heartbeat")
def session_heartbeat(
    hb: SessionHeartbeat,
    worker: Worker = Depends(worker_auth),
) -> dict:
    """WorkerSession 단위 30초 heartbeat.

    PR-C v2 — Codex 검토: body 의 worker_id 무시. auth 된 worker.id 만 사용.
    워커가 -1 같은 placeholder 보내도 서버가 정확히 식별.
    """
    db = _db_session.SessionLocal()
    try:
        sess = (
            db.query(WorkerSession)
            .filter(WorkerSession.session_uuid == hb.session_uuid)
            .first()
        )
        now = datetime.now(UTC)
        if sess is None:
            sess = WorkerSession(
                session_uuid=hb.session_uuid,
                worker_id=worker.id,           # auth 기준
                account_id=hb.account_id,
                started_at=now,
                last_heartbeat_at=now,
                status=hb.status,
            )
            db.add(sess)
        else:
            if sess.worker_id is not None and sess.worker_id != worker.id:
                raise HTTPException(403, "session not owned by this worker")
            sess.last_heartbeat_at = now
            if hb.status != sess.status:
                sess.status = hb.status
                if hb.status in ("ended", "failed"):
                    sess.ended_at = now
        db.commit()
        return {"ok": True}
    finally:
        db.close()
