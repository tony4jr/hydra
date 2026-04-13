"""Error log API."""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from hydra.db.session import get_db
from hydra.db.models import ErrorLog

router = APIRouter()


@router.get("/api/list")
def list_logs(
    level: str | None = None,
    source: str | None = None,
    resolved: bool | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(ErrorLog)
    if level:
        query = query.filter(ErrorLog.level == level)
    if source:
        query = query.filter(ErrorLog.source == source)
    if resolved is not None:
        query = query.filter(ErrorLog.resolved == resolved)
    logs = query.order_by(ErrorLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": l.id, "level": l.level, "source": l.source,
            "account_id": l.account_id, "video_id": l.video_id,
            "campaign_id": l.campaign_id,
            "message": l.message, "resolved": l.resolved,
            "resolved_at": str(l.resolved_at) if l.resolved_at else None,
            "created_at": str(l.created_at) if l.created_at else None,
        }
        for l in logs
    ]


@router.get("/api/stats")
def log_stats(db: Session = Depends(get_db)):
    """Error log summary stats."""
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    by_level = dict(
        db.query(ErrorLog.level, func.count())
        .filter(ErrorLog.resolved == False)
        .group_by(ErrorLog.level)
        .all()
    )
    by_source = dict(
        db.query(ErrorLog.source, func.count())
        .filter(ErrorLog.resolved == False)
        .group_by(ErrorLog.source)
        .all()
    )
    today_count = (
        db.query(func.count())
        .filter(ErrorLog.created_at >= today)
        .scalar()
    )
    unresolved = (
        db.query(func.count())
        .filter(ErrorLog.resolved == False)
        .scalar()
    )

    return {
        "unresolved_total": unresolved,
        "today_total": today_count,
        "by_level": by_level,
        "by_source": by_source,
    }


@router.post("/api/{log_id}/resolve")
def resolve_log(log_id: int, db: Session = Depends(get_db)):
    """Mark a single error log as resolved."""
    log_entry = db.query(ErrorLog).get(log_id)
    if not log_entry:
        return {"error": "not found"}
    log_entry.resolved = True
    log_entry.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "id": log_id}


class BulkResolveInput(BaseModel):
    ids: list[int] | None = None
    level: str | None = None
    source: str | None = None
    before_hours: int | None = None


@router.post("/api/bulk-resolve")
def bulk_resolve(data: BulkResolveInput, db: Session = Depends(get_db)):
    """Bulk resolve error logs by IDs, level, source, or age."""
    now = datetime.now(timezone.utc)
    query = db.query(ErrorLog).filter(ErrorLog.resolved == False)

    if data.ids:
        query = query.filter(ErrorLog.id.in_(data.ids))
    if data.level:
        query = query.filter(ErrorLog.level == data.level)
    if data.source:
        query = query.filter(ErrorLog.source == data.source)
    if data.before_hours:
        cutoff = now - timedelta(hours=data.before_hours)
        query = query.filter(ErrorLog.created_at <= cutoff)

    count = query.update(
        {"resolved": True, "resolved_at": now},
        synchronize_session="fetch",
    )
    db.commit()
    return {"ok": True, "resolved_count": count}
