"""T17 다영상 캠페인 + T20 좋아요 부스트 타이밍.

Endpoints:
- POST /api/campaigns/{id}/videos: 영상 추가 (단건 / bulk)
- GET  /api/campaigns/{id}/videos: 진행 현황
- DELETE /api/campaigns/{id}/videos/{video_id}: 제외
- POST /api/campaigns/{id}/schedule-boosts: 댓글 게시된 작업들 → like_boost 예약
"""
from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hydra.db import session as _db_session
from hydra.db.models import (
    Account, Campaign, CampaignVideo, ProfileLock, Task, Video, Worker,
)
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()


# ───────────── 영상 추가 / 조회 ─────────────

class CampaignVideoIn(BaseModel):
    video_id: str
    funnel_stage: Optional[str] = None
    target_count: int = Field(default=1, ge=1, le=200)
    priority: int = Field(default=0)


class CampaignVideoOut(BaseModel):
    id: int
    campaign_id: int
    video_id: str
    funnel_stage: Optional[str] = None
    target_count: int
    completed_count: int
    priority: int
    progress_pct: float


@router.post("/{campaign_id}/videos", response_model=list[CampaignVideoOut])
def add_videos(
    campaign_id: int,
    videos: list[CampaignVideoIn],
    _session: dict = Depends(admin_session),
) -> list[CampaignVideoOut]:
    """캠페인에 영상 1+ 추가. 이미 있는 영상은 갱신 (target_count, priority)."""
    if not videos:
        raise HTTPException(400, "videos 비어있음")
    db = _db_session.SessionLocal()
    try:
        camp = db.get(Campaign, campaign_id)
        if camp is None:
            raise HTTPException(404, "campaign not found")

        out = []
        for v in videos:
            # 영상 자체는 이미 videos 테이블에 등록돼 있어야 함
            if db.get(Video, v.video_id) is None:
                raise HTTPException(400, f"video not registered: {v.video_id}")

            existing = (
                db.query(CampaignVideo)
                .filter(
                    CampaignVideo.campaign_id == campaign_id,
                    CampaignVideo.video_id == v.video_id,
                )
                .first()
            )
            if existing:
                existing.target_count = v.target_count
                existing.priority = v.priority
                if v.funnel_stage:
                    existing.funnel_stage = v.funnel_stage
                cv = existing
            else:
                cv = CampaignVideo(
                    campaign_id=campaign_id,
                    video_id=v.video_id,
                    funnel_stage=v.funnel_stage,
                    target_count=v.target_count,
                    priority=v.priority,
                    created_at=datetime.now(UTC),
                )
                db.add(cv)
            db.flush()
            db.refresh(cv)
            out.append(_to_out(cv))
        db.commit()
        return out
    finally:
        db.close()


@router.get("/{campaign_id}/videos", response_model=list[CampaignVideoOut])
def list_campaign_videos(
    campaign_id: int,
    _session: dict = Depends(admin_session),
) -> list[CampaignVideoOut]:
    db = _db_session.SessionLocal()
    try:
        rows = (
            db.query(CampaignVideo)
            .filter(CampaignVideo.campaign_id == campaign_id)
            .order_by(CampaignVideo.priority.desc(), CampaignVideo.id)
            .all()
        )
        return [_to_out(r) for r in rows]
    finally:
        db.close()


@router.delete("/{campaign_id}/videos/{video_id}")
def remove_video(
    campaign_id: int,
    video_id: str,
    _session: dict = Depends(admin_session),
) -> dict:
    db = _db_session.SessionLocal()
    try:
        row = (
            db.query(CampaignVideo)
            .filter(
                CampaignVideo.campaign_id == campaign_id,
                CampaignVideo.video_id == video_id,
            )
            .first()
        )
        if row is None:
            raise HTTPException(404, "campaign_video not found")
        db.delete(row)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


def _to_out(cv: CampaignVideo) -> CampaignVideoOut:
    pct = (
        round(100 * cv.completed_count / cv.target_count, 1)
        if cv.target_count > 0 else 0.0
    )
    return CampaignVideoOut(
        id=cv.id, campaign_id=cv.campaign_id, video_id=cv.video_id,
        funnel_stage=cv.funnel_stage, target_count=cv.target_count,
        completed_count=cv.completed_count, priority=cv.priority,
        progress_pct=pct,
    )


# ───────────── T20 좋아요 부스트 타이밍 ─────────────

class BoostScheduleRequest(BaseModel):
    """댓글 작업이 done 된 것들에 대해 like_boost 태스크를 시간차 분산 예약.

    같은 댓글에 여러 워커가 좋아요 → 클러스터링 회피 위해 다른 워커 + 시간차.
    """
    delay_min_minutes: int = Field(default=15, ge=1, le=240)
    delay_max_minutes: int = Field(default=120, ge=1, le=240)
    likes_per_comment: int = Field(default=3, ge=1, le=20)
    same_worker_excluded: bool = True  # 댓글 단 워커는 좋아요에서 제외


class BoostScheduleResult(BaseModel):
    scheduled: int
    skipped: list[dict]  # [{comment_task_id, reason}]


@router.post("/{campaign_id}/schedule-boosts", response_model=BoostScheduleResult)
def schedule_boosts(
    campaign_id: int,
    req: BoostScheduleRequest,
    _session: dict = Depends(admin_session),
) -> BoostScheduleResult:
    """캠페인 댓글 done → 좋아요 부스트 자동 예약.

    각 댓글에 대해:
    - likes_per_comment 개의 like 태스크 생성
    - scheduled_at = now + random(delay_min, delay_max) (각각 다른 시점)
    - worker_id 미지정 (큐 fetch 시 다른 워커 선택)
    - same_worker_excluded: 댓글 단 워커 ID 를 메타에 기록 (큐가 회피)
    """
    if req.delay_max_minutes < req.delay_min_minutes:
        raise HTTPException(400, "delay_max < delay_min")

    db = _db_session.SessionLocal()
    try:
        # 캠페인의 done 댓글 작업들 — 아직 부스트 예약 안 된 것
        comment_tasks = (
            db.query(Task)
            .filter(
                Task.campaign_id == campaign_id,
                Task.task_type == "comment",
                Task.status == "done",
            )
            .all()
        )

        scheduled = 0
        skipped: list[dict] = []
        active_workers = (
            db.query(Worker.id)
            .filter(Worker.status == "online", Worker.token_hash.isnot(None))
            .all()
        )
        available_worker_ids = [w[0] for w in active_workers]

        if len(available_worker_ids) < 2 and req.same_worker_excluded:
            # 워커 1대뿐이면 배제 정책 못 지킴 → 경고 후 진행
            pass

        for ct in comment_tasks:
            # 이미 boost 가 있는지 체크 (중복 예약 방지) — payload 에 source_comment_id 매칭
            already = (
                db.query(Task)
                .filter(
                    Task.task_type == "like",
                    Task.campaign_id == campaign_id,
                    Task.payload.like(f'%"source_comment_id": {ct.id}%'),
                )
                .first()
            )
            if already is not None:
                skipped.append({"comment_task_id": ct.id, "reason": "already scheduled"})
                continue

            # account_id 가 있어야 (큐 SKIP LOCKED 가 ProfileLock 사용)
            if ct.account_id is None:
                skipped.append({"comment_task_id": ct.id, "reason": "no account_id"})
                continue

            for i in range(req.likes_per_comment):
                # 시간차 — uniform 분포
                delay_min = random.uniform(req.delay_min_minutes, req.delay_max_minutes) * 60
                scheduled_at = datetime.now(UTC) + timedelta(seconds=delay_min)

                payload = {
                    "source_comment_id": ct.id,
                    "video_id": (json.loads(ct.payload).get("video_id") if ct.payload else None),
                    "exclude_worker_id": ct.worker_id if req.same_worker_excluded else None,
                }
                like_task = Task(
                    campaign_id=campaign_id,
                    account_id=None,  # 큐 fetch 시 사용 가능한 다른 계정 선택
                    task_type="like",
                    status="pending",
                    priority="normal",
                    payload=json.dumps(payload, ensure_ascii=False),
                    scheduled_at=scheduled_at,
                )
                db.add(like_task)
                scheduled += 1
        db.commit()
        return BoostScheduleResult(scheduled=scheduled, skipped=skipped)
    finally:
        db.close()
