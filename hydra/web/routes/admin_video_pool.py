"""Phase 1 — 영상 풀 어드민 API.

- GET /api/admin/video-pool/list  — 풀 영상 목록 (필터링)
- POST /api/admin/video-pool/{id}/toggle-state  — active ↔ blacklisted 수동 전환
- POST /api/admin/video-pool/{id}/reclassify  — 분류 재실행
- GET /api/admin/video-pool/quota  — YouTube API quota 사용량
- GET /api/admin/video-pool/global-state/{youtube_video_id}  — 글로벌 상태
"""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from hydra.db import session as _db_session
from hydra.db.models import (
    Video, Keyword, Brand, YoutubeVideoGlobalState,
)
from hydra.services.youtube_quota import check_throttle_state
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()


@router.get("/list")
def list_pool(
    target_id: int = Query(..., description="Brand id (= target id)"),
    state: Optional[str] = Query(None, description="active|blacklisted|pending|paused|completed"),
    l_tier: Optional[str] = Query(None, description="L1|L2|L3|L4"),
    lifecycle_phase: Optional[int] = Query(None, ge=1, le=4),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _session: dict = Depends(admin_session),
) -> dict:
    db = _db_session.SessionLocal()
    try:
        brand = db.get(Brand, target_id)
        if brand is None:
            raise HTTPException(404, "target not found")

        keyword_ids = [
            k.id for k in db.query(Keyword.id).filter(Keyword.brand_id == target_id).all()
        ]
        if not keyword_ids:
            return {"total": 0, "items": []}

        q = db.query(Video).filter(Video.keyword_id.in_(keyword_ids))
        if state:
            q = q.filter(Video.state == state)
        if l_tier:
            q = q.filter(Video.l_tier == l_tier)
        if lifecycle_phase is not None:
            q = q.filter(Video.lifecycle_phase == lifecycle_phase)

        total = q.count()
        items = (
            q.order_by(Video.collected_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "total": total,
            "items": [
                {
                    "id": v.id,
                    "url": v.url,
                    "title": v.title,
                    "channel_title": v.channel_title,
                    "view_count": v.view_count,
                    "like_count": v.like_count,
                    "comment_count": v.comment_count,
                    "duration_sec": v.duration_sec,
                    "is_short": v.is_short,
                    "published_at": v.published_at.isoformat() if v.published_at else None,
                    "collected_at": v.collected_at.isoformat() if v.collected_at else None,
                    "state": v.state,
                    "blacklist_reason": v.blacklist_reason,
                    "l_tier": v.l_tier,
                    "lifecycle_phase": v.lifecycle_phase,
                    "embedding_score": v.embedding_score,
                    "popularity_score": v.popularity_score,
                    "last_action_at": v.last_action_at.isoformat() if v.last_action_at else None,
                    "next_revisit_at": v.next_revisit_at.isoformat() if v.next_revisit_at else None,
                    "top_comment_likes": v.top_comment_likes,
                }
                for v in items
            ],
        }
    finally:
        db.close()


class ToggleStateRequest(BaseModel):
    state: str  # active | blacklisted | paused | completed
    reason: Optional[str] = None


@router.post("/{video_id}/toggle-state")
def toggle_state(
    video_id: str,
    req: ToggleStateRequest,
    _session: dict = Depends(admin_session),
) -> dict:
    """LLM/임베딩이 잘못 분류한 경우 운영자가 수동 전환.

    state: active|blacklisted|paused|completed.
    """
    if req.state not in ("active", "blacklisted", "paused", "completed", "pending"):
        raise HTTPException(400, "invalid state")

    db = _db_session.SessionLocal()
    try:
        v = db.get(Video, video_id)
        if v is None:
            raise HTTPException(404, "video not found")

        prev = v.state
        v.state = req.state
        if req.state == "blacklisted":
            v.blacklist_reason = req.reason or "manual"
        elif req.state == "active" and v.blacklist_reason:
            # 운영자가 수동으로 풀어줄 때 reason 클리어
            v.blacklist_reason = None
        db.commit()

        return {
            "video_id": video_id,
            "previous_state": prev,
            "new_state": req.state,
        }
    finally:
        db.close()


@router.post("/{video_id}/reclassify")
def reclassify(
    video_id: str,
    target_id: int = Query(...),
    _session: dict = Depends(admin_session),
) -> dict:
    """단일 영상 분류 재실행 (운영자가 임계값 바꾼 후 등)."""
    from hydra.services.video_pipeline import process_video

    db = _db_session.SessionLocal()
    try:
        v = db.get(Video, video_id)
        if v is None:
            raise HTTPException(404, "video not found")

        # blacklisted 일 경우 일단 pending 으로 되돌려야 재평가
        if v.state == "blacklisted":
            v.state = "pending"
            v.blacklist_reason = None
            v.embedding_score = None  # 재평가
        result = process_video(db, v, target_id)
        db.commit()

        return {
            "video_id": video_id,
            "result": result,
            "state": v.state,
            "l_tier": v.l_tier,
            "lifecycle_phase": v.lifecycle_phase,
            "embedding_score": v.embedding_score,
            "blacklist_reason": v.blacklist_reason,
        }
    finally:
        db.close()


@router.get("/quota")
def quota_status(_session: dict = Depends(admin_session)) -> dict:
    """YouTube API quota 사용 현황."""
    from hydra.collection.youtube_api import _load_keys_from_db
    from hydra.core.config import settings

    db = _db_session.SessionLocal()
    try:
        keys = _load_keys_from_db() or settings.youtube_api_keys
        num_keys = max(len(keys or []), 1)
        return check_throttle_state(db, num_keys)
    finally:
        db.close()


@router.get("/global-state/{youtube_video_id}")
def global_state(
    youtube_video_id: str,
    _session: dict = Depends(admin_session),
) -> dict:
    """특정 YouTube 영상의 글로벌 상태 (다중 타겟 추적)."""
    db = _db_session.SessionLocal()
    try:
        row = db.get(YoutubeVideoGlobalState, youtube_video_id)
        if row is None:
            return {"youtube_video_id": youtube_video_id, "exists": False}
        return {
            "youtube_video_id": youtube_video_id,
            "exists": True,
            "total_actions_24h": row.total_actions_24h,
            "total_actions_7d": row.total_actions_7d,
            "active_target_count": row.active_target_count,
            "active_scenario_count": row.active_scenario_count,
            "last_action_at": row.last_action_at.isoformat() if row.last_action_at else None,
            "last_main_comment_at": row.last_main_comment_at.isoformat() if row.last_main_comment_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    finally:
        db.close()
