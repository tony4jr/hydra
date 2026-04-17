from datetime import UTC, datetime
import json
from sqlalchemy import case, or_
from sqlalchemy.orm import Session
from hydra.db.models import Task, ProfileLock, Worker
from hydra.services.account_limits import can_execute_task
from hydra.services.video_protection import check_account_video_duplicate, check_account_video_like_duplicate


PREPARATION_TYPES = {"login", "channel_setup", "warmup"}


def fetch_tasks(db: Session, worker: Worker, limit: int = 5) -> list[Task]:
    """Worker에게 배정할 태스크 가져오기 (프로필 잠금 + 역할 필터링)."""
    now = datetime.now(UTC)
    priority_order = case(
        (Task.priority == "urgent", 0),
        (Task.priority == "high", 1),
        (Task.priority == "normal", 2),
        (Task.priority == "low", 3),
        else_=4,
    )
    tasks = db.query(Task).filter(
        Task.status == "pending",
        or_(Task.scheduled_at <= now, Task.scheduled_at.is_(None)),
    ).order_by(
        priority_order,
        Task.created_at.asc(),
    ).limit(limit * 2).all()

    assigned = []
    for task in tasks:
        if len(assigned) >= limit:
            break
        # 역할 필터링: 준비/캠페인 태스크 분리
        if task.task_type in PREPARATION_TYPES and not worker.allow_preparation:
            continue
        if task.task_type not in PREPARATION_TYPES and not worker.allow_campaign:
            continue
        if task.account_id:
            existing_lock = db.query(ProfileLock).filter(
                ProfileLock.account_id == task.account_id,
                ProfileLock.released_at.is_(None),
            ).first()
            if existing_lock and existing_lock.worker_id != worker.id:
                continue
        # Account limit check
        if task.account_id:
            allowed, reason = can_execute_task(db, task.account_id, task.task_type)
            if not allowed:
                continue

        # Video duplicate check
        if task.account_id and task.payload:
            try:
                payload = json.loads(task.payload)
                video_id = payload.get("video_id", "")
                if video_id and task.task_type in ("comment", "reply"):
                    if not check_account_video_duplicate(db, task.account_id, video_id):
                        continue  # 이미 댓글 달은 영상 → 건너뜀
                if video_id and task.task_type in ("like", "like_boost"):
                    if not check_account_video_like_duplicate(db, task.account_id, video_id):
                        continue
            except (json.JSONDecodeError, TypeError):
                pass
        task.status = "assigned"
        task.worker_id = worker.id
        task.assigned_at = now
        assigned.append(task)

    db.commit()
    return assigned


def complete_task(db: Session, task_id: int, result: str = None):
    task = db.get(Task, task_id)
    if not task:
        return None
    task.status = "completed"
    task.completed_at = datetime.now(UTC)
    if result:
        task.result = result
    if task.account_id:
        lock = db.query(ProfileLock).filter(
            ProfileLock.account_id == task.account_id,
            ProfileLock.released_at.is_(None),
        ).first()
        if lock:
            lock.released_at = datetime.now(UTC)
    db.commit()
    return task


def fail_task(db: Session, task_id: int, error: str):
    task = db.get(Task, task_id)
    if not task:
        return None
    task.retry_count += 1
    if task.retry_count < task.max_retries:
        task.status = "pending"
        task.worker_id = None
        task.assigned_at = None
        task.error_message = error
    else:
        task.status = "failed"
        task.error_message = error
        task.completed_at = datetime.now(UTC)
    if task.account_id:
        lock = db.query(ProfileLock).filter(
            ProfileLock.account_id == task.account_id,
            ProfileLock.released_at.is_(None),
        ).first()
        if lock:
            lock.released_at = datetime.now(UTC)
    db.commit()
    return task
