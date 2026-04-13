"""Video management API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import Video

router = APIRouter()


@router.get("/api/list")
def list_videos(
    status: str | None = None,
    priority: str | None = None,
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Video)
    if status:
        query = query.filter(Video.status == status)
    if priority:
        query = query.filter(Video.priority == priority)

    total = query.count()
    videos = query.order_by(Video.collected_at.desc()).offset((page - 1) * size).limit(size).all()

    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": v.id, "title": v.title, "channel": v.channel_title,
                "views": v.view_count, "comments": v.comment_count,
                "is_short": v.is_short, "status": v.status,
                "priority": v.priority,
                "published_at": str(v.published_at) if v.published_at else None,
                "collected_at": str(v.collected_at),
            }
            for v in videos
        ],
    }
