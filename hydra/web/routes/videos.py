"""Video management API."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from hydra.db.session import get_db
from hydra.db.models import Video, ScrapedComment

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


# --- #7: Comment Scraping UI ---

@router.get("/api/scraped-comments")
def list_scraped_comments(
    video_id: str | None = None,
    min_likes: int = 0,
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
):
    """List scraped comments with filters."""
    query = db.query(ScrapedComment)
    if video_id:
        query = query.filter(ScrapedComment.video_id == video_id)
    if min_likes > 0:
        query = query.filter(ScrapedComment.like_count >= min_likes)

    total = query.count()
    comments = (
        query.order_by(ScrapedComment.like_count.desc())
        .offset((page - 1) * size).limit(size).all()
    )

    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": c.id,
                "video_id": c.video_id,
                "author": c.author_name,
                "content": c.content,
                "like_count": c.like_count,
                "time_text": c.time_text,
                "used_for_training": c.used_for_training,
                "scraped_at": str(c.scraped_at),
            }
            for c in comments
        ],
    }


@router.get("/api/scraped-stats")
def scraped_stats(db: Session = Depends(get_db)):
    """Scraped comments statistics."""
    total = db.query(func.count()).select_from(ScrapedComment).scalar()
    videos = db.query(func.count(func.distinct(ScrapedComment.video_id))).scalar()
    trained = db.query(func.count()).filter(ScrapedComment.used_for_training == True).scalar()
    avg_likes = db.query(func.avg(ScrapedComment.like_count)).scalar()

    return {
        "total_comments": total,
        "unique_videos": videos,
        "used_for_training": trained,
        "avg_likes": round(float(avg_likes or 0), 1),
    }


@router.post("/api/collect")
def collect_videos(brand_id: int = None, db: Session = Depends(get_db)):
    from hydra.services.video_collector import collect_new_videos
    if not brand_id:
        return {"ok": False, "error": "brand_id required"}
    videos = collect_new_videos(db, brand_id)
    return {"ok": True, "collected": len(videos)}


@router.post("/api/collect/initial")
def collect_initial(brand_id: int, db: Session = Depends(get_db)):
    """초기 세팅: 조회수순 대량 수집."""
    from hydra.services.video_collector import collect_initial_videos
    if not brand_id:
        return {"ok": False, "error": "brand_id required"}
    videos = collect_initial_videos(db, brand_id)
    return {"ok": True, "collected": len(videos)}


@router.post("/api/add-manual")
def add_video_manual(url: str, keyword_id: int = None, db: Session = Depends(get_db)):
    from hydra.services.video_collector import add_video_manually
    video = add_video_manually(db, url, keyword_id)
    if not video:
        return {"ok": False, "error": "Invalid YouTube URL"}
    return {"ok": True, "video_id": video.id}


@router.post("/api/refresh-status")
def refresh_video_status(db: Session = Depends(get_db)):
    """Re-check status of stored videos via YouTube Data API."""
    from hydra.collection.youtube_api import refresh_video_status
    try:
        result = refresh_video_status(db)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}
