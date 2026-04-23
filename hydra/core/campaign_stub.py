"""M1 Task M1-5: 스텁 캠페인.

env M1_TEST_VIDEO_ID 에 설정된 영상 1개에 대해,
active 상태이지만 아직 처리 안 된 계정에 comment/like 태스크 1회씩 생성.
"""
from __future__ import annotations

import json
import os

from sqlalchemy.orm import Session

from hydra.db.models import Account, Task


def _target_video_id() -> str | None:
    return os.getenv("M1_TEST_VIDEO_ID", "").strip() or None


def scan_active_accounts(session: Session) -> int:
    """active 계정 중 이번 스텁 캠페인 미처리 건 대상으로 comment/like 태스크 생성.

    Returns: 처리한 account 수.
    """
    video_id = _target_video_id()
    if not video_id:
        return 0

    actives = (
        session.query(Account)
        .filter(Account.status == "active")
        .all()
    )
    processed = 0
    for acc in actives:
        existing = (
            session.query(Task)
            .filter(
                Task.account_id == acc.id,
                Task.task_type.in_(("comment", "like")),
            )
            .first()
        )
        if existing is not None:
            continue

        payload_base = {"video_id": video_id, "m1_stub": True}
        session.add_all([
            Task(
                account_id=acc.id,
                task_type="comment",
                status="pending",
                payload=json.dumps({**payload_base, "ai_generated": True}),
            ),
            Task(
                account_id=acc.id,
                task_type="like",
                status="pending",
                payload=json.dumps(payload_base),
            ),
        ])
        processed += 1
    if processed:
        session.commit()
    return processed
