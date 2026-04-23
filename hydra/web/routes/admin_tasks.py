"""Task M2.1-3/4: admin Task stats + recent list queries."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func

from hydra.db import session as _db_session
from hydra.db.models import Account, Task, Worker
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()

_STATUSES = ("pending", "running", "done", "failed")


class TasksStatsResponse(BaseModel):
    pending: int
    running: int
    done: int
    failed: int
    by_type: dict


@router.get("/stats", response_model=TasksStatsResponse)
def stats(_session: dict = Depends(admin_session)) -> TasksStatsResponse:
    db = _db_session.SessionLocal()
    try:
        rows = (
            db.query(Task.task_type, Task.status, func.count(Task.id))
            .group_by(Task.task_type, Task.status)
            .all()
        )
        totals = {s: 0 for s in _STATUSES}
        by_type: dict[str, dict[str, int]] = {}
        for task_type, status, count in rows:
            if status not in _STATUSES:
                continue
            totals[status] = totals.get(status, 0) + count
            by_type.setdefault(task_type, {s: 0 for s in _STATUSES})[status] = count
        return TasksStatsResponse(**totals, by_type=by_type)
    finally:
        db.close()


class RecentTaskItem(BaseModel):
    id: int
    task_type: str
    status: str
    account_id: Optional[int]
    account_gmail: Optional[str]
    worker_id: Optional[int]
    worker_name: Optional[str]
    created_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class RecentTasksResponse(BaseModel):
    items: list[RecentTaskItem]


@router.get("/recent", response_model=RecentTasksResponse)
def recent(
    _session: dict = Depends(admin_session),
    limit: int = Query(20, ge=1, le=200),
) -> RecentTasksResponse:
    db = _db_session.SessionLocal()
    try:
        rows = (
            db.query(Task, Account.gmail, Worker.name)
            .outerjoin(Account, Task.account_id == Account.id)
            .outerjoin(Worker, Task.worker_id == Worker.id)
            .order_by(Task.id.desc())
            .limit(limit)
            .all()
        )
        items = [
            RecentTaskItem(
                id=t.id, task_type=t.task_type, status=t.status,
                account_id=t.account_id, account_gmail=gmail,
                worker_id=t.worker_id, worker_name=wname,
                created_at=t.created_at, started_at=t.started_at,
                completed_at=t.completed_at,
            )
            for (t, gmail, wname) in rows
        ]
        return RecentTasksResponse(items=items)
    finally:
        db.close()
