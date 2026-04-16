from datetime import datetime
from sqlalchemy.orm import Session
from hydra.db.models import Task, ProfileLock, Worker


def fetch_tasks(db: Session, worker: Worker, limit: int = 5) -> list[Task]:
    """Worker에게 배정할 태스크 가져오기 (프로필 잠금 고려)."""
    now = datetime.utcnow()
    tasks = db.query(Task).filter(
        Task.status == "pending",
        Task.scheduled_at <= now,
    ).order_by(
        Task.priority.desc(),
        Task.created_at.asc(),
    ).limit(limit * 2).all()

    assigned = []
    for task in tasks:
        if len(assigned) >= limit:
            break
        if task.account_id:
            existing_lock = db.query(ProfileLock).filter(
                ProfileLock.account_id == task.account_id,
                ProfileLock.released_at.is_(None),
            ).first()
            if existing_lock and existing_lock.worker_id != worker.id:
                continue
        task.status = "assigned"
        task.worker_id = worker.id
        task.assigned_at = now
        assigned.append(task)

    db.commit()
    return assigned


def complete_task(db: Session, task_id: int, result: str = None):
    task = db.query(Task).get(task_id)
    if not task:
        return None
    task.status = "completed"
    task.completed_at = datetime.utcnow()
    if result:
        task.result = result
    if task.account_id:
        lock = db.query(ProfileLock).filter(
            ProfileLock.account_id == task.account_id,
            ProfileLock.released_at.is_(None),
        ).first()
        if lock:
            lock.released_at = datetime.utcnow()
    db.commit()
    return task


def fail_task(db: Session, task_id: int, error: str):
    task = db.query(Task).get(task_id)
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
        task.completed_at = datetime.utcnow()
    if task.account_id:
        lock = db.query(ProfileLock).filter(
            ProfileLock.account_id == task.account_id,
            ProfileLock.released_at.is_(None),
        ).first()
        if lock:
            lock.released_at = datetime.utcnow()
    db.commit()
    return task
