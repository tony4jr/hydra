"""System control API — pause/resume, emergency stop, status, maintenance."""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from hydra.db.session import get_db
from hydra.db.models import ActionLog, ErrorLog, IpLog, Campaign, Video

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


@router.post("/api/patrol")
def run_patrol(db: Session = Depends(get_db)):
    """Run comment survival patrol — check recent comments for ghost/deleted."""
    from hydra.ghost.patrol import run_patrol
    try:
        result = run_patrol(db)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/refresh-videos")
def refresh_videos(db: Session = Depends(get_db)):
    """Re-check video status via YouTube Data API."""
    from hydra.collection.youtube_api import refresh_video_status
    try:
        result = refresh_video_status(db)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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


# --- #18: Data Cleanup ---

class CleanupInput(BaseModel):
    action_logs_days: int = 90
    error_logs_days: int = 60
    ip_logs_days: int = 30
    deleted_videos: bool = True
    dry_run: bool = True


@router.get("/api/cleanup/preview")
def cleanup_preview(db: Session = Depends(get_db)):
    """Preview what data cleanup would remove."""
    now = datetime.now(timezone.utc)

    action_logs_90d = db.query(func.count()).filter(
        ActionLog.created_at < now - timedelta(days=90),
    ).scalar()
    error_logs_60d = db.query(func.count()).filter(
        ErrorLog.created_at < now - timedelta(days=60),
        ErrorLog.resolved == True,
    ).scalar()
    ip_logs_30d = db.query(func.count()).filter(
        IpLog.started_at < now - timedelta(days=30),
    ).scalar()
    deleted_videos = db.query(func.count()).filter(
        Video.status == "deleted",
    ).scalar()

    return {
        "action_logs_older_90d": action_logs_90d,
        "resolved_errors_older_60d": error_logs_60d,
        "ip_logs_older_30d": ip_logs_30d,
        "deleted_videos": deleted_videos,
    }


@router.post("/api/cleanup")
def run_cleanup(data: CleanupInput, db: Session = Depends(get_db)):
    """Run data cleanup. Set dry_run=false to actually delete."""
    now = datetime.now(timezone.utc)
    results = {}

    # Action logs
    action_cutoff = now - timedelta(days=data.action_logs_days)
    action_query = db.query(ActionLog).filter(ActionLog.created_at < action_cutoff)
    results["action_logs"] = action_query.count()

    # Resolved error logs
    error_cutoff = now - timedelta(days=data.error_logs_days)
    error_query = db.query(ErrorLog).filter(
        ErrorLog.created_at < error_cutoff,
        ErrorLog.resolved == True,
    )
    results["error_logs"] = error_query.count()

    # IP logs
    ip_cutoff = now - timedelta(days=data.ip_logs_days)
    ip_query = db.query(IpLog).filter(IpLog.started_at < ip_cutoff)
    results["ip_logs"] = ip_query.count()

    # Deleted videos (and their campaigns)
    deleted_count = 0
    if data.deleted_videos:
        deleted_count = db.query(func.count()).filter(Video.status == "deleted").scalar()
        results["deleted_videos"] = deleted_count

    if data.dry_run:
        return {"dry_run": True, "would_delete": results}

    # Execute deletions
    action_query.delete(synchronize_session="fetch")
    error_query.delete(synchronize_session="fetch")
    ip_query.delete(synchronize_session="fetch")

    if data.deleted_videos:
        # Delete campaigns for deleted videos first (FK constraint)
        deleted_video_ids = [v.id for v in db.query(Video.id).filter(Video.status == "deleted").all()]
        if deleted_video_ids:
            # Delete campaign steps → campaigns → videos
            campaign_ids = [
                c.id for c in
                db.query(Campaign.id).filter(Campaign.video_id.in_(deleted_video_ids)).all()
            ]
            if campaign_ids:
                from hydra.db.models import CampaignStep, LikeBoostQueue
                db.query(CampaignStep).filter(CampaignStep.campaign_id.in_(campaign_ids)).delete(synchronize_session="fetch")
                db.query(LikeBoostQueue).filter(LikeBoostQueue.campaign_id.in_(campaign_ids)).delete(synchronize_session="fetch")
                db.query(Campaign).filter(Campaign.id.in_(campaign_ids)).delete(synchronize_session="fetch")
            db.query(Video).filter(Video.id.in_(deleted_video_ids)).delete(synchronize_session="fetch")

    db.commit()
    return {"dry_run": False, "deleted": results}
