from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from hydra.api.deps import db_dependency
from hydra.services import worker_service

router = APIRouter(prefix="/api/workers", tags=["workers"])

class WorkerCreate(BaseModel):
    name: str

class WorkerCreateResponse(BaseModel):
    worker_id: int
    name: str
    token: str

class HeartbeatRequest(BaseModel):
    version: str | None = None
    os_type: str | None = None

class HeartbeatResponse(BaseModel):
    status: str
    server_version: str | None = None

@router.post("/register", response_model=WorkerCreateResponse)
def register(body: WorkerCreate, db: Session = Depends(db_dependency)):
    worker, raw_token = worker_service.register_worker(db, body.name)
    return WorkerCreateResponse(worker_id=worker.id, name=worker.name, token=raw_token)

@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(body: HeartbeatRequest, x_worker_token: str = Header(...), db: Session = Depends(db_dependency)):
    worker = worker_service.verify_token(db, x_worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Invalid worker token")
    worker_service.heartbeat(db, worker, body.version, body.os_type)
    return HeartbeatResponse(status="ok")

@router.get("/")
def list_workers(db: Session = Depends(db_dependency)):
    from hydra.db.models import Worker
    workers = db.query(Worker).all()
    return [{"id": w.id, "name": w.name, "status": w.status, "last_heartbeat": w.last_heartbeat, "current_version": w.current_version, "os_type": w.os_type} for w in workers]
