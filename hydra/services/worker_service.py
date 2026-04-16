import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from sqlalchemy.orm import Session
from hydra.db.models import Worker

def generate_worker_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed

def verify_token(db: Session, raw_token: str) -> Worker | None:
    hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    return db.query(Worker).filter(Worker.token_hash == hashed).first()

def register_worker(db: Session, name: str) -> tuple[Worker, str]:
    raw, hashed = generate_worker_token()
    worker = Worker(name=name, token_hash=hashed, status="offline")
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker, raw

def heartbeat(db: Session, worker: Worker, version: str = None, os_type: str = None):
    worker.last_heartbeat = datetime.now(UTC)
    worker.status = "online"
    if version:
        worker.current_version = version
    if os_type:
        worker.os_type = os_type
    db.commit()

def check_stale_workers(db: Session, timeout_seconds: int = 60):
    cutoff = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
    stale = db.query(Worker).filter(
        Worker.status == "online",
        Worker.last_heartbeat < cutoff,
    ).all()
    for w in stale:
        w.status = "offline"
    db.commit()
    return stale
