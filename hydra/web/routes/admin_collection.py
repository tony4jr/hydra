"""영상 수집 트리거 + 진척률 조회 (admin).

POST /api/admin/collection/start/{brand_id}  — initial deep collection (백그라운드)
GET  /api/admin/collection/status/{brand_id} — 풀 진척률 (수집 영상 수, 신규/백로그 분포)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from hydra.db import session as _db_session
from hydra.db.models import Brand, Keyword, Video
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()
log = logging.getLogger(__name__)

# 진행 중 collection 추적 (process-local)
_in_progress: dict[int, dict] = {}


@router.post("/start/{brand_id}")
def start_collection(brand_id: int, _session: dict = Depends(admin_session)) -> dict:
    """초기 깊은 수집 트리거 — 비동기. status 엔드포인트로 진행 확인."""
    db = _db_session.SessionLocal()
    try:
        brand = db.get(Brand, brand_id)
        if not brand:
            raise HTTPException(404, "brand not found")
        if brand_id in _in_progress and _in_progress[brand_id].get("running"):
            return {"started": False, "reason": "already_running", "info": _in_progress[brand_id]}
    finally:
        db.close()

    _in_progress[brand_id] = {
        "running": True,
        "started_at": datetime.now(UTC).isoformat(),
        "result": None,
    }

    async def _runner():
        from hydra.services.smart_video_collector import collect_initial_for_brand
        local_db = _db_session.SessionLocal()
        try:
            result = await asyncio.to_thread(collect_initial_for_brand, local_db, brand_id)
            _in_progress[brand_id]["result"] = result
            _in_progress[brand_id]["finished_at"] = datetime.now(UTC).isoformat()
        except Exception as e:
            _in_progress[brand_id]["error"] = str(e)
            log.exception("initial collection failed for brand %s", brand_id)
        finally:
            _in_progress[brand_id]["running"] = False
            local_db.close()

    asyncio.create_task(_runner())
    return {"started": True, "brand_id": brand_id}


@router.get("/status/{brand_id}")
def collection_status(brand_id: int, _session: dict = Depends(admin_session)) -> dict:
    """풀 통계 + 진행 중 작업 정보."""
    db = _db_session.SessionLocal()
    try:
        brand = db.get(Brand, brand_id)
        if not brand:
            raise HTTPException(404, "brand not found")

        keyword_ids = [
            k.id for k in db.query(Keyword.id).filter(Keyword.brand_id == brand_id).all()
        ]

        if not keyword_ids:
            stats = {"total": 0, "fresh": 0, "popular_backlog": 0, "worked": 0, "untouched": 0}
        else:
            now = datetime.now(UTC)
            seven_days_ago = now - timedelta(days=7)

            total = db.query(Video).filter(Video.keyword_id.in_(keyword_ids)).count()
            fresh = db.query(Video).filter(
                Video.keyword_id.in_(keyword_ids),
                Video.collected_at >= seven_days_ago,
            ).count()
            popular = db.query(Video).filter(
                Video.keyword_id.in_(keyword_ids),
                Video.view_count >= 1_000_000,
                Video.last_worked_at.is_(None),
            ).count()
            worked = db.query(Video).filter(
                Video.keyword_id.in_(keyword_ids),
                Video.last_worked_at.isnot(None),
            ).count()
            untouched = db.query(Video).filter(
                Video.keyword_id.in_(keyword_ids),
                Video.last_worked_at.is_(None),
            ).count()

            stats = {
                "total": total,
                "fresh": fresh,
                "popular_backlog": popular,
                "worked": worked,
                "untouched": untouched,
                "progress_pct": round(worked / total * 100, 1) if total else 0,
            }

        # 키워드 목록 + 변형 수
        roots = db.query(Keyword).filter(
            Keyword.brand_id == brand_id,
            Keyword.is_variant == False,  # noqa: E712
        ).all()
        keyword_breakdown = []
        for r in roots:
            v_count = db.query(Keyword).filter(Keyword.parent_keyword_id == r.id).count()
            videos_count = db.query(Video).filter(Video.keyword_id == r.id).count()
            keyword_breakdown.append({
                "keyword": r.text,
                "videos_direct": videos_count,
                "variant_count": v_count,
                "total_videos_found": r.total_videos_found or 0,
            })

        return {
            "brand_id": brand_id,
            "brand_name": brand.name,
            "collection_depth": brand.collection_depth or "standard",
            "longtail_count": brand.longtail_count or 5,
            "preset_video_limit": brand.preset_video_limit or 1,
            "stats": stats,
            "keywords": keyword_breakdown,
            "in_progress": _in_progress.get(brand_id, {}),
        }
    finally:
        db.close()


@router.post("/daily-new/{brand_id}")
def trigger_daily_new(brand_id: int, _session: dict = Depends(admin_session)) -> dict:
    """수동으로 매일 신규 수집 트리거 (테스트/재시도용)."""
    from hydra.services.smart_video_collector import collect_daily_new
    db = _db_session.SessionLocal()
    try:
        added = collect_daily_new(db, brand_id, hours=24)
        return {"brand_id": brand_id, "videos_added": added}
    finally:
        db.close()


@router.patch("/policy/{brand_id}")
def update_policy(
    brand_id: int,
    policy: dict,
    _session: dict = Depends(admin_session),
) -> dict:
    """Brand 의 수집/픽업 정책 업데이트.

    body: {
      collection_depth: "quick"|"standard"|"deep"|"max",
      longtail_count: int,
      preset_video_limit: int,
      scoring_weights: {freshness, popularity, untouched, random}  // optional
    }
    """
    import json as _json
    db = _db_session.SessionLocal()
    try:
        brand = db.get(Brand, brand_id)
        if not brand:
            raise HTTPException(404, "brand not found")

        if "collection_depth" in policy:
            depth = policy["collection_depth"]
            if depth not in ("quick", "standard", "deep", "max"):
                raise HTTPException(400, "invalid collection_depth")
            brand.collection_depth = depth
        if "longtail_count" in policy:
            brand.longtail_count = max(0, min(50, int(policy["longtail_count"])))
        if "preset_video_limit" in policy:
            brand.preset_video_limit = max(1, min(10, int(policy["preset_video_limit"])))
        if "scoring_weights" in policy and isinstance(policy["scoring_weights"], dict):
            brand.scoring_weights = _json.dumps(policy["scoring_weights"])

        db.commit()
        return {
            "brand_id": brand_id,
            "collection_depth": brand.collection_depth,
            "longtail_count": brand.longtail_count,
            "preset_video_limit": brand.preset_video_limit,
            "scoring_weights": brand.scoring_weights,
        }
    finally:
        db.close()
