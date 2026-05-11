"""Task M2.1-3/4: admin Task stats + recent list queries."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func

from hydra.db import session as _db_session
from hydra.db.models import Account, Task, Worker
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()

_STATUSES = ("pending", "running", "done", "failed")

# task_type 별 예상 처리 시간 (분). 이를 N% 초과하면 stale 후보로 표시.
# 실제 데이터 분포 보고 조정 가능. zombie_cleanup 의 30분 임계치보다는 짧게 잡아
# UI 에서 먼저 경고가 보이도록.
EXPECTED_DURATION_MINUTES: dict[str, int] = {
    "comment": 8,
    "reply": 6,
    "like": 3,
    "like_boost": 5,
    "subscribe": 3,
    "warmup": 25,
    "onboard": 35,
    "create_profile": 5,
    "channel_setup": 10,
    "login": 6,
}
_DEFAULT_EXPECTED = 10
_STALE_RATIO = 1.5  # expected 의 1.5배 초과면 stale 표시 (zombie 임계치 < stale 임계치)


def _elapsed_and_stale(task: Task) -> tuple[Optional[int], Optional[int], bool, Optional[str]]:
    """(elapsed_minutes, expected_minutes, is_stale, stale_reason) 계산.

    실행 중(running/assigned) task 만 elapsed 의미가 있음. 나머지는 None.
    """
    if task.status not in ("running", "assigned"):
        return None, None, False, None
    # v2 는 status='running' + started_at, legacy 는 status='assigned' + assigned_at
    start = task.started_at if task.started_at is not None else task.assigned_at
    if start is None:
        return None, None, False, None
    # tz-naive (DB 기본) → UTC 가정
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    elapsed = (datetime.now(UTC) - start).total_seconds() / 60.0
    elapsed_min = int(elapsed)
    expected = EXPECTED_DURATION_MINUTES.get(task.task_type, _DEFAULT_EXPECTED)
    if elapsed >= expected * _STALE_RATIO:
        reason = f"task_type '{task.task_type}' 예상 {expected}분 대비 {int(elapsed/expected*100)}% 경과"
        return elapsed_min, expected, True, reason
    return elapsed_min, expected, False, None


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
    priority: Optional[str] = None
    account_id: Optional[int]
    account_gmail: Optional[str]
    worker_id: Optional[int]
    worker_name: Optional[str]
    created_at: Optional[datetime]
    started_at: Optional[datetime]
    assigned_at: Optional[datetime] = None
    completed_at: Optional[datetime]
    # zombie/elapsed 가시성
    elapsed_minutes: Optional[int] = None
    expected_minutes: Optional[int] = None
    is_stale: bool = False
    stale_reason: Optional[str] = None


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
        items = []
        for (t, gmail, wname) in rows:
            elapsed, expected, is_stale, reason = _elapsed_and_stale(t)
            items.append(RecentTaskItem(
                id=t.id, task_type=t.task_type, status=t.status,
                priority=t.priority,
                account_id=t.account_id, account_gmail=gmail,
                worker_id=t.worker_id, worker_name=wname,
                created_at=t.created_at, started_at=t.started_at,
                assigned_at=t.assigned_at,
                completed_at=t.completed_at,
                elapsed_minutes=elapsed,
                expected_minutes=expected,
                is_stale=is_stale,
                stale_reason=reason,
            ))
        return RecentTasksResponse(items=items)
    finally:
        db.close()


class StaleStatsResponse(BaseModel):
    """현재 in-flight (running/assigned) task 중 stale 후보 개수 + 진짜 zombie 후보."""
    in_flight_total: int
    stale_count: int
    zombie_candidate_count: int       # 30분 초과 — zombie_cleanup 다음 tick 에 정리될 후보
    oldest_elapsed_minutes: Optional[int]


@router.get("/stale-stats", response_model=StaleStatsResponse)
def stale_stats(_session: dict = Depends(admin_session)) -> StaleStatsResponse:
    db = _db_session.SessionLocal()
    try:
        in_flight = (
            db.query(Task)
            .filter(Task.status.in_(("running", "assigned")))
            .all()
        )
        stale_count = 0
        zombie_candidate = 0
        oldest: Optional[int] = None
        zombie_threshold_min = 30  # zombie_cleanup 기본값과 동일
        for t in in_flight:
            elapsed, _expected, is_stale, _reason = _elapsed_and_stale(t)
            if elapsed is None:
                continue
            if oldest is None or elapsed > oldest:
                oldest = elapsed
            if is_stale:
                stale_count += 1
            if elapsed >= zombie_threshold_min:
                zombie_candidate += 1
        return StaleStatsResponse(
            in_flight_total=len(in_flight),
            stale_count=stale_count,
            zombie_candidate_count=zombie_candidate,
            oldest_elapsed_minutes=oldest,
        )
    finally:
        db.close()
