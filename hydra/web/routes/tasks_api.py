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

from hydra.db import session as _db_session
from hydra.db.models import Account, ProfileLock, Task, Worker
from hydra.web.routes.worker_api import worker_auth


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

    Returns True if assigned, False if no idle account available.

    Picked account:
      - status = 'active'
      - not in any open ProfileLock
      - not in identity_challenge cooldown
    """
    if task.account_id:
        return True
    if task.task_type not in _AUTO_ASSIGN_TYPES:
        return True  # Other task types may legitimately have no account_id
    now = datetime.now(UTC)
    available = (
        db.query(Account)
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
        .first()
    )
    if not available:
        return False
    task.account_id = available.id
    return True


_FETCH_SQL_PG = text("""
    SELECT t.id
      FROM tasks t
      LEFT JOIN accounts a ON a.id = t.account_id
     WHERE t.status = 'pending'
       AND (t.scheduled_at IS NULL OR t.scheduled_at <= NOW())
       AND (
         -- already-assigned: account exists and has a profile and isn't locked
         (
           t.account_id IS NOT NULL
           AND a.adspower_profile_id IS NOT NULL
           AND t.account_id NOT IN (
             SELECT account_id FROM profile_locks WHERE released_at IS NULL
           )
         )
         -- unassigned: scenario/campaign tasks pending account auto-assignment
         OR t.account_id IS NULL
       )
     ORDER BY
       CASE t.priority
         WHEN 'high' THEN 3
         WHEN 'normal' THEN 2
         WHEN 'low' THEN 1
         ELSE 0
       END DESC,
       t.scheduled_at ASC NULLS FIRST,
       t.id ASC
     LIMIT 10
     FOR UPDATE OF t SKIP LOCKED
""")

_FETCH_SQL_SQLITE = text("""
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
     ORDER BY
       CASE t.priority
         WHEN 'high' THEN 3
         WHEN 'normal' THEN 2
         WHEN 'low' THEN 1
         ELSE 0
       END DESC,
       t.scheduled_at ASC,
       t.id ASC
     LIMIT 10
""")


@router.post("/fetch")
def fetch_tasks(worker: Worker = Depends(worker_auth)) -> dict:
    db = _db_session.SessionLocal()
    try:
        dialect = db.bind.dialect.name
        q = _FETCH_SQL_PG if dialect == "postgresql" else _FETCH_SQL_SQLITE
        rows = db.execute(q).fetchall()  # 최대 10개 후보
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
            # Auto-assign account_id for unassigned campaign/scenario tasks.
            # Skips candidate if no idle active account is available right now —
            # next fetch round will retry once a worker frees an account.
            if not _auto_assign_account(db, candidate):
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

        # Task 35: 로컬 DB 없이도 태스크 실행 가능하도록 account_snapshot 동봉
        snapshot = {
            "id": account.id,
            "gmail": account.gmail,
            "encrypted_password": account.password,  # 이미 암호화된 채 저장됨
            "recovery_email": account.recovery_email,
            "adspower_profile_id": account.adspower_profile_id,
            "persona": account.persona,  # JSON 문자열
            "encrypted_totp_secret": account.totp_secret,
            "status": account.status,
            "ipp_flagged": account.ipp_flagged,
            "youtube_channel_id": account.youtube_channel_id,
        }
        return {"tasks": [{
            "id": task.id,
            "account_id": task.account_id,
            "adspower_profile_id": account.adspower_profile_id,
            "task_type": task.task_type,
            "payload": task.payload,
            "priority": task.priority,
            "account_snapshot": snapshot,
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
