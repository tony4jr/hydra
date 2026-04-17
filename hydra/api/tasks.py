from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from hydra.db.session import get_db
from hydra.db.models import Account, Task
from hydra.services import worker_service, task_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskResponse(BaseModel):
    id: int
    task_type: str
    priority: str
    payload: str | None
    account_id: int | None
    adspower_profile_id: str | None = None


class TaskCompleteRequest(BaseModel):
    task_id: int
    result: str | None = None


class TaskFailRequest(BaseModel):
    task_id: int
    error: str


@router.post("/fetch", response_model=list[TaskResponse])
def fetch_tasks(x_worker_token: str = Header(...), db: Session = Depends(get_db)):
    worker = worker_service.verify_token(db, x_worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Invalid worker token")
    tasks = task_service.fetch_tasks(db, worker)
    results = []
    for t in tasks:
        account = db.get(Account, t.account_id) if t.account_id else None
        results.append(TaskResponse(
            id=t.id,
            task_type=t.task_type,
            priority=t.priority,
            payload=t.payload,
            account_id=t.account_id,
            adspower_profile_id=account.adspower_profile_id if account else None,
        ))
    return results


@router.post("/complete")
def complete_task(body: TaskCompleteRequest, x_worker_token: str = Header(...), db: Session = Depends(get_db)):
    worker = worker_service.verify_token(db, x_worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Invalid worker token")
    task = task_service.complete_task(db, body.task_id, body.result)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "task_id": task.id}


@router.post("/fail")
def fail_task(body: TaskFailRequest, x_worker_token: str = Header(...), db: Session = Depends(get_db)):
    worker = worker_service.verify_token(db, x_worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Invalid worker token")
    task = task_service.fail_task(db, body.task_id, body.error)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "task_id": task.id, "will_retry": task.status == "pending"}


# --- 워밍업 일괄 생성 ---

class WarmupBatchRequest(BaseModel):
    account_ids: list[int]
    day: int = 1


@router.post("/warmup/batch")
def create_warmup_tasks(
    body: WarmupBatchRequest,
    db: Session = Depends(get_db),
):
    """워밍업 태스크 일괄 생성."""
    import json

    created = []
    for account_id in body.account_ids:
        account = db.get(Account, account_id)
        if not account:
            continue

        persona = None
        if account.persona:
            try:
                persona = json.loads(account.persona)
            except (json.JSONDecodeError, TypeError):
                pass

        task = Task(
            account_id=account_id,
            task_type="warmup",
            priority="normal",
            status="pending",
            payload=json.dumps({
                "day": body.day,
                "persona": persona,
                "account_gmail": account.gmail,
            }, ensure_ascii=False),
            scheduled_at=datetime.now(UTC),
        )
        db.add(task)
        created.append(task)

    db.commit()
    return {"ok": True, "created": len(created)}


# --- 캠페인 일괄 취소 ---

class CancelBatchRequest(BaseModel):
    campaign_id: int


@router.post("/cancel/batch")
def cancel_campaign_tasks(body: CancelBatchRequest, db: Session = Depends(get_db)):
    """캠페인의 미완료 태스크 일괄 취소."""
    tasks = db.query(Task).filter(
        Task.campaign_id == body.campaign_id,
        Task.status.in_(["pending", "assigned"]),
    ).all()
    for task in tasks:
        task.status = "cancelled"
    db.commit()
    return {"ok": True, "cancelled": len(tasks)}
