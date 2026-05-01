"""Comment execution endpoints (PR-8g)."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import CommentExecution, SystemConfig
from hydra.services.comment_limits import _load_limits, can_post_comment


router = APIRouter()


@router.get("")
def list_executions(
    video_id: Optional[str] = None,
    campaign_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(CommentExecution)
    if video_id:
        q = q.filter(CommentExecution.video_id == video_id)
    if campaign_id is not None:
        q = q.filter(CommentExecution.campaign_id == campaign_id)
    if status:
        q = q.filter(CommentExecution.status == status)
    total = q.count()
    rows = q.order_by(CommentExecution.posted_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": e.id,
                "video_id": e.video_id,
                "slot_id": e.slot_id,
                "campaign_id": e.campaign_id,
                "worker_id": e.worker_id,
                "text": e.text[:200],
                "posted_at": e.posted_at.isoformat() if e.posted_at else None,
                "youtube_comment_id": e.youtube_comment_id,
                "status": e.status,
                "likes_count": e.likes_count,
                "tracking_status": e.tracking_status,
                "tracking_phase": e.tracking_phase,
                "last_checked_at": e.last_checked_at.isoformat() if e.last_checked_at else None,
                "next_check_at": e.next_check_at.isoformat() if e.next_check_at else None,
            }
            for e in rows
        ],
    }


@router.get("/{execution_id}")
def get_execution(execution_id: int, db: Session = Depends(get_db)):
    e = db.get(CommentExecution, execution_id)
    if e is None:
        raise HTTPException(404, "execution not found")
    return {
        "id": e.id, "video_id": e.video_id, "slot_id": e.slot_id,
        "campaign_id": e.campaign_id, "worker_id": e.worker_id,
        "text": e.text,
        "posted_at": e.posted_at.isoformat() if e.posted_at else None,
        "youtube_comment_id": e.youtube_comment_id,
        "status": e.status, "likes_count": e.likes_count,
        "tracking_status": e.tracking_status, "tracking_phase": e.tracking_phase,
        "last_checked_at": e.last_checked_at.isoformat() if e.last_checked_at else None,
        "next_check_at": e.next_check_at.isoformat() if e.next_check_at else None,
    }


# ─── 한도 설정 ────────────────────────────────────────────────────


@router.get("/limits/config")
def get_limits_config(db: Session = Depends(get_db)):
    return _load_limits(db)


class LimitsUpdate(BaseModel):
    large_max: Optional[int] = None
    medium_max: Optional[int] = None
    small_max: Optional[int] = None
    min_interval_minutes: Optional[int] = None
    channel_daily_max: Optional[int] = None
    video_pct_max: Optional[float] = None
    large_view_threshold: Optional[int] = None
    small_view_threshold: Optional[int] = None
    viral_likes_threshold: Optional[int] = None


@router.patch("/limits/config")
def update_limits_config(data: LimitsUpdate, db: Session = Depends(get_db)):
    cfg = db.get(SystemConfig, "comment_limits")
    current = _load_limits(db)
    payload = data.model_dump(exclude_unset=True)
    current.update(payload)
    if cfg is None:
        cfg = SystemConfig(key="comment_limits", value=json.dumps(current))
        db.add(cfg)
    else:
        cfg.value = json.dumps(current)
    db.commit()
    return current


@router.post("/limits/check")
def check_limit(video_id: str, worker_id: int, db: Session = Depends(get_db)):
    """단일 한도 사전 검증 (UI 또는 외부 호출용)."""
    allowed, reason = can_post_comment(db, video_id, worker_id)
    return {"allowed": allowed, "reason": reason}
