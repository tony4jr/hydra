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


_FETCH_SQL_PG = text("""
    SELECT t.id
      FROM tasks t
      JOIN accounts a ON a.id = t.account_id
     WHERE t.status = 'pending'
       AND (t.scheduled_at IS NULL OR t.scheduled_at <= NOW())
       AND a.adspower_profile_id IS NOT NULL
       AND t.account_id NOT IN (
           SELECT account_id FROM profile_locks WHERE released_at IS NULL
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
      JOIN accounts a ON a.id = t.account_id
     WHERE t.status = 'pending'
       AND (t.scheduled_at IS NULL OR t.scheduled_at <= datetime('now'))
       AND a.adspower_profile_id IS NOT NULL
       AND t.account_id NOT IN (
           SELECT account_id FROM profile_locks WHERE released_at IS NULL
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
            task = candidate
            break

        if task is None:
            return {"tasks": []}

        account = db.get(Account, task.account_id)
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

        return {"tasks": [{
            "id": task.id,
            "account_id": task.account_id,
            "adspower_profile_id": account.adspower_profile_id,
            "task_type": task.task_type,
            "payload": task.payload,
            "priority": task.priority,
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
        db.commit()
        return {"ok": True}
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
        db.commit()
        return {"ok": True}
    finally:
        db.close()
