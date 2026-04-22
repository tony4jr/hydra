"""좀비 태스크 복구 — started_at 이 임계치 초과한 running 태스크를 pending 으로 복원.

워커가 크래시/네트워크 단절로 태스크를 영원히 running 으로 남기면 ProfileLock 이 해제되지
않아 해당 account 가 영구 락됨. 5분마다 크론으로 이 함수를 호출해 정리.

임계치 30분 = 실제 태스크 평균(3~10분)의 3배 이상 — false positive 억제.
향후 heartbeat 기반 감지로 고도화 가능 (Task 34 이후).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from hydra.db import session as _db_session
from hydra.db.models import ProfileLock, Task

log = logging.getLogger("hydra.zombie_cleanup")


def find_and_reset_zombies(stale_minutes: int = 30) -> int:
    """임계치 초과한 running 태스크를 pending 으로 복원.

    Returns: 복구된 태스크 수.
    """
    threshold = datetime.now(UTC) - timedelta(minutes=stale_minutes)
    db = _db_session.SessionLocal()
    try:
        stuck = (
            db.query(Task)
            .filter(
                Task.status == "running",
                Task.started_at.isnot(None),
                Task.started_at < threshold,
            )
            .all()
        )
        for t in stuck:
            log.warning(
                "zombie task id=%s worker=%s started=%s",
                t.id, t.worker_id, t.started_at,
            )
            t.status = "pending"
            t.worker_id = None
            t.started_at = None

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
