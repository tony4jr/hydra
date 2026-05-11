"""PR-C2: admin gauge — 실시간 phase + last_progress_at 시각화.

엔드포인트:
- GET /api/admin/phase-gauge — 모든 활성 task 의 현재 phase, last_progress_at, age.
- GET /api/admin/phase-gauge/sessions — 활성 WorkerSession 목록.
- GET /api/admin/phase-gauge/recent-history?limit=50 — 최근 phase 변경 history.

용도: 야간 smoke 후 아침 로그 분석 시각화. 워커별/세션별/phase별 현재 상태 1초 안에 파악.
"""
from __future__ import annotations

from datetime import datetime, UTC, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func

from hydra.db.session import get_db
from hydra.db.models import Account, Task, Worker, WorkerProgress, WorkerSession
from hydra.protocol.phase_config import get_phase_spec
from hydra.web.routes.admin_auth import admin_session


router = APIRouter()


def _age_seconds(dt: Optional[datetime]) -> Optional[float]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds()


@router.get("/phase-gauge")
def phase_gauge(
    _session: dict = Depends(admin_session),
    db=Depends(get_db),
):
    """현재 진행 중 task 의 phase + last_progress_at + 임계 대비 age 비율.

    출력:
    {
      "tasks": [{
        task_id, account_id, worker_id, task_type, status,
        last_phase, last_progress_age_sec, started_age_sec,
        phase_timeout_sec, phase_progress_pct
      }, ...]
    }
    """
    rows = (
        db.query(Task, Account.gmail, Worker.name)
        .outerjoin(Account, Task.account_id == Account.id)
        .outerjoin(Worker, Task.worker_id == Worker.id)
        .filter(Task.status.in_(["running", "assigned"]))
        .order_by(Task.id.desc())
        .limit(100)
        .all()
    )
    items = []
    for t, acct_gmail, worker_name in rows:
        progress_age = _age_seconds(t.last_progress_at)
        started_age = _age_seconds(t.started_at)
        phase_threshold = None
        progress_pct = None
        if t.last_phase:
            spec = get_phase_spec(t.last_phase)
            phase_threshold = spec.timeout_sec
            if progress_age is not None and phase_threshold:
                progress_pct = round(progress_age / phase_threshold * 100, 1)
        items.append({
            "task_id": t.id,
            "task_type": t.task_type,
            "status": t.status,
            "account_id": t.account_id,
            "account_gmail": acct_gmail,
            "worker_id": t.worker_id,
            "worker_name": worker_name,
            "last_phase": t.last_phase,
            "session_uuid": t.session_uuid,
            "last_progress_age_sec": progress_age,
            "started_age_sec": started_age,
            "phase_timeout_sec": phase_threshold,
            "phase_progress_pct": progress_pct,
        })
    return {"tasks": items}


@router.get("/phase-gauge/sessions")
def active_sessions(
    _session: dict = Depends(admin_session),
    db=Depends(get_db),
):
    """활성 WorkerSession (status='active', 최근 heartbeat) 목록."""
    cutoff = datetime.now(UTC) - timedelta(minutes=30)
    cutoff_naive = cutoff.replace(tzinfo=None)
    rows = (
        db.query(WorkerSession, Worker.name)
        .outerjoin(Worker, WorkerSession.worker_id == Worker.id)
        .filter(WorkerSession.status == "active")
        .filter(WorkerSession.last_heartbeat_at >= cutoff_naive)
        .order_by(WorkerSession.id.desc())
        .limit(50)
        .all()
    )
    items = []
    for s, worker_name in rows:
        items.append({
            "session_uuid": s.session_uuid,
            "worker_id": s.worker_id,
            "worker_name": worker_name,
            "account_id": s.account_id,
            "started_at": s.started_at,
            "started_age_sec": _age_seconds(s.started_at),
            "last_heartbeat_age_sec": _age_seconds(s.last_heartbeat_at),
            "status": s.status,
        })
    return {"sessions": items}


@router.get("/phase-gauge/recent-history")
def recent_phase_history(
    _session: dict = Depends(admin_session),
    db=Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    session_uuid: Optional[str] = Query(None, description="특정 세션만 필터"),
):
    """최근 phase 변경 history. 사고 후 시퀀스 reconstruction 용.

    session_uuid 필터하면 그 세션의 phase 흐름 순서대로 (sequence_no ASC).
    아니면 모든 세션 across 최신 limit건 (occurred_at DESC).
    """
    q = db.query(WorkerProgress)
    if session_uuid:
        q = q.filter(WorkerProgress.session_uuid == session_uuid).order_by(
            WorkerProgress.sequence_no.asc()
        )
    else:
        q = q.order_by(WorkerProgress.occurred_at.desc())
    rows = q.limit(limit).all()
    items = [
        {
            "id": r.id,
            "session_uuid": r.session_uuid,
            "task_id": r.task_id,
            "worker_id": r.worker_id,
            "attempt_no": r.attempt_no,
            "sequence_no": r.sequence_no,
            "phase": r.phase,
            "message": r.message,
            "occurred_at": r.occurred_at,
        }
        for r in rows
    ]
    return {"events": items}
