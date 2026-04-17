from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from hydra.db.session import get_db
from hydra.db.models import Account
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
