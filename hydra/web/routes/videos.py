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


# ─── PR-5a: 영상 검색 + 타임라인 ─────────────────────────────────


from datetime import datetime, UTC
from typing import Optional
from fastapi import HTTPException, Query as FQuery
from hydra.db.models import ActionLog, Campaign, Niche, Keyword


@router.get("/api/search")
def search_videos(
    q: Optional[str] = None,
    niche_id: Optional[int] = None,
    state: Optional[str] = None,
    tier: Optional[str] = None,
    sort: str = "recent",
    page: int = 1,
    page_size: int = FQuery(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """영상 검색 + 필터 (PR-5a)."""
    query = db.query(Video)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Video.title.ilike(like)) | (Video.channel_title.ilike(like))
        )
    if niche_id is not None:
        query = query.filter(Video.niche_id == niche_id)
    if state:
        query = query.filter(Video.state == state)
    if tier:
        query = query.filter(Video.l_tier == tier)

    if sort == "views":
        query = query.order_by(Video.view_count.desc().nullslast())
    elif sort == "fitness":
        query = query.order_by(Video.embedding_score.desc().nullslast())
    elif sort == "comment_count":
        query = query.order_by(Video.comment_count.desc().nullslast())
    else:
        query = query.order_by(Video.collected_at.desc())

    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        {
            "id": v.id,
            "title": v.title,
            "channel": v.channel_title,
            "view_count": v.view_count,
            "comment_count": v.comment_count,
            "published_at": v.published_at.isoformat() if v.published_at else None,
            "discovered_at": v.collected_at.isoformat() if v.collected_at else None,
            "state": v.state,
            "tier": v.l_tier,
            "market_fitness": v.embedding_score,
            "niche_id": v.niche_id,
            "url": v.url,
            "is_short": v.is_short,
        }
        for v in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/api/{video_id}/timeline")
def video_timeline(video_id: str, db: Session = Depends(get_db)):
    """영상 타임라인 — 기존 데이터로 최대한 복원 (lean PR-5a).

    이벤트 종류:
    - discovered (Video.collected_at)
    - state_set (Video.state — 현재만, 변경 이력 추적 X)
    - campaign_created (Campaign.created_at)
    - comment_posted / reply_posted (ActionLog)
    - blacklisted (Video.state='blacklisted', blacklist_reason)
    """
    v = db.get(Video, video_id)
    if v is None:
        raise HTTPException(404, "video not found")

    niche = db.get(Niche, v.niche_id) if v.niche_id else None
    keyword = db.get(Keyword, v.keyword_id) if v.keyword_id else None

    events = []

    if v.collected_at:
        events.append({
            "at": v.collected_at.isoformat(),
            "kind": "discovered",
            "actor": "system",
            "actor_detail": f"keyword:{keyword.text}" if keyword else None,
            "metadata": {
                "discovered_via": v.discovered_via,
                "discovery_keyword": v.discovery_keyword,
            },
        })

    if v.state == "blacklisted":
        events.append({
            "at": v.last_action_at.isoformat() if v.last_action_at else (
                v.collected_at.isoformat() if v.collected_at else None
            ),
            "kind": "rejected_filter",
            "actor": "system",
            "actor_detail": v.blacklist_reason,
            "metadata": {"reason": v.blacklist_reason},
        })

    campaigns = (
        db.query(Campaign)
        .filter(Campaign.video_id == video_id)
        .order_by(Campaign.created_at.asc())
        .all()
    )
    for c in campaigns:
        events.append({
            "at": c.created_at.isoformat() if c.created_at else None,
            "kind": "campaign_created",
            "actor": "operator",
            "campaign_id": c.id,
            "campaign_name": c.name,
            "metadata": {"scenario": c.scenario, "status": c.status},
        })

    action_rows = (
        db.query(ActionLog)
        .filter(ActionLog.video_id == video_id)
        .order_by(ActionLog.created_at.asc())
        .limit(500)
        .all()
    )
    for a in action_rows:
        kind = "comment_posted" if a.action_type in ("comment", "reply") else f"action_{a.action_type}"
        events.append({
            "at": a.created_at.isoformat() if a.created_at else None,
            "kind": kind,
            "actor": "worker",
            "actor_detail": f"account:{a.account_id}",
            "campaign_id": a.campaign_id,
            "metadata": {
                "action_type": a.action_type,
                "is_promo": a.is_promo,
                "status": a.status,
                "youtube_comment_id": a.youtube_comment_id,
            },
        })

    events.sort(key=lambda e: e["at"] or "")

    return {
        "video": {
            "id": v.id,
            "title": v.title,
            "channel": v.channel_title,
            "url": v.url,
            "view_count": v.view_count,
            "comment_count": v.comment_count,
            "state": v.state,
            "tier": v.l_tier,
            "market_fitness": v.embedding_score,
            "niche_id": v.niche_id,
            "niche_name": niche.name if niche else None,
        },
        "events": events,
        "upcoming": [],
    }
