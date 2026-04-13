"""Error log API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import ErrorLog

router = APIRouter()


@router.get("/api/list")
def list_logs(
    level: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(ErrorLog)
    if level:
        query = query.filter(ErrorLog.level == level)
    logs = query.order_by(ErrorLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": l.id, "level": l.level, "source": l.source,
            "message": l.message, "resolved": l.resolved,
            "created_at": str(l.created_at) if l.created_at else None,
        }
        for l in logs
    ]
