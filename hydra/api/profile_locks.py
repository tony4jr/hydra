from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, UTC
from hydra.db.session import get_db
from hydra.db.models import ProfileLock
from hydra.services.worker_service import verify_token

router = APIRouter(prefix="/api/profile-locks", tags=["profile-locks"])

class LockRequest(BaseModel):
    account_id: int
    adspower_profile_id: str

class UnlockRequest(BaseModel):
    account_id: int

@router.post("/lock")
def lock_profile(body: LockRequest, x_worker_token: str = Header(...), db: Session = Depends(get_db)):
    worker = verify_token(db, x_worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Invalid worker token")

    # 이미 잠긴 프로필 확인
    existing = db.query(ProfileLock).filter(
        ProfileLock.account_id == body.account_id,
        ProfileLock.released_at.is_(None),
    ).first()
    if existing:
        if existing.worker_id == worker.id:
            return {"ok": True, "already_locked": True}
        raise HTTPException(status_code=409, detail=f"Profile locked by another worker")

    lock = ProfileLock(
        account_id=body.account_id,
        worker_id=worker.id,
        adspower_profile_id=body.adspower_profile_id,
    )
    db.add(lock)
    db.commit()
    return {"ok": True, "lock_id": lock.id}

@router.post("/unlock")
def unlock_profile(body: UnlockRequest, x_worker_token: str = Header(...), db: Session = Depends(get_db)):
    worker = verify_token(db, x_worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Invalid worker token")

    lock = db.query(ProfileLock).filter(
        ProfileLock.account_id == body.account_id,
        ProfileLock.worker_id == worker.id,
        ProfileLock.released_at.is_(None),
    ).first()
    if lock:
        lock.released_at = datetime.now(UTC)
        db.commit()
    return {"ok": True}

@router.get("/active")
def list_active_locks(db: Session = Depends(get_db)):
    locks = db.query(ProfileLock).filter(ProfileLock.released_at.is_(None)).all()
    return [
        {"account_id": l.account_id, "worker_id": l.worker_id,
         "adspower_profile_id": l.adspower_profile_id, "locked_at": str(l.locked_at)}
        for l in locks
    ]
