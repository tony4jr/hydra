"""좀비 태스크 복구 — last_progress_at(우선) 또는 started_at 임계 초과 시 pending 복원.

PR-C 이후: 워커가 progress reporter 로 phase 보고. last_progress_at 이 진짜 stale 마커.
구버전 task (PR-C 배포 전 시작) 는 last_progress_at=NULL 이라 started_at fallback.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func

from hydra.db import session as _db_session
from hydra.db.models import ProfileLock, Task

log = logging.getLogger("hydra.zombie_cleanup")


def find_and_reset_zombies(stale_minutes: int = 30) -> int:
    """임계치 초과한 running 태스크를 pending 으로 복원.

    효과적 stale 시각 = COALESCE(last_progress_at, started_at).
    last_progress_at 있는 task 는 phase progress 가 멈춘 시점 기준 — 더 정확.
    """
    threshold = datetime.now(UTC) - timedelta(minutes=stale_minutes)
    db = _db_session.SessionLocal()
    try:
        # COALESCE: PG/SQLite 양쪽 호환.
        effective_at = func.coalesce(Task.last_progress_at, Task.started_at)
        stuck = (
            db.query(Task)
            .filter(
                Task.status == "running",
                effective_at.isnot(None),
                effective_at < threshold,
            )
            .all()
        )
        for t in stuck:
            log.warning(
                "zombie task id=%s worker=%s started=%s last_progress=%s phase=%s",
                t.id, t.worker_id, t.started_at, t.last_progress_at, t.last_phase,
            )
            t.status = "pending"
            t.worker_id = None
            t.started_at = None
            t.last_progress_at = None
            t.last_phase = None

            locks = (
                db.query(ProfileLock)
                .filter_by(task_id=t.id, released_at=None)
                .all()
            )
            for lk in locks:
                lk.released_at = datetime.now(UTC)
        db.commit()
        return len(stuck)
    finally:
        db.close()
