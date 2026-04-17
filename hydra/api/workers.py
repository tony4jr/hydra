from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from hydra.api.deps import db_dependency
from hydra.core.config import settings
from hydra.services import worker_service

router = APIRouter(prefix="/api/workers", tags=["workers"])

class WorkerCreate(BaseModel):
    name: str
    registration_secret: str

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
    if body.registration_secret != settings.worker_token_secret:
        raise HTTPException(status_code=403, detail="Invalid registration secret")
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


@router.post("/{worker_id}/pause")
def pause_worker(worker_id: int, db: Session = Depends(db_dependency)):
    from hydra.db.models import Worker
    worker = db.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker.status = "paused"
    db.commit()
    return {"ok": True, "status": "paused"}


@router.post("/{worker_id}/resume")
def resume_worker(worker_id: int, db: Session = Depends(db_dependency)):
    from hydra.db.models import Worker
    worker = db.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker.status = "online"
    db.commit()
    return {"ok": True, "status": "online"}
