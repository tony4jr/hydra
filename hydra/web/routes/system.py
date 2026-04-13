"""System control API — pause/resume, emergency stop, status."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from hydra.db.session import get_db

router = APIRouter()


@router.post("/api/pause")
def pause_system():
    from hydra.core.scheduler import pause
    pause()
    return {"ok": True, "status": "paused"}


@router.post("/api/resume")
def resume_system():
    from hydra.core.scheduler import resume
    resume()
    return {"ok": True, "status": "running"}


@router.post("/api/emergency-stop")
def emergency_stop(db: Session = Depends(get_db)):
    """Emergency stop: pause scheduler + release all locks."""
    from hydra.core.scheduler import pause
    from hydra.core.lock import release_all
    pause()
    release_all(db)
    return {"ok": True, "status": "emergency_stopped"}


@router.get("/api/status")
def system_status(db: Session = Depends(get_db)):
    from hydra.core.scheduler import is_paused
    from hydra.core.lock import _get_locks
    locks = _get_locks(db)
    return {
        "paused": is_paused(),
        "running_accounts": len(locks),
        "locked_account_ids": list(locks.keys()),
    }
