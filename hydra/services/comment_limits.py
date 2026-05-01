"""댓글 한도 검증 + 추적 phase 진행 (PR-8g)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from hydra.db.models import CommentExecution, SystemConfig, Video


_DEFAULTS = {
    "large_max": 5,
    "medium_max": 3,
    "small_max": 1,
    "min_interval_minutes": 5,
    "channel_daily_max": 5,
    "video_pct_max": 0.05,
    "large_view_threshold": 1_000_000,
    "small_view_threshold": 10_000,
    "viral_likes_threshold": 10,
}


def _load_limits(db: Session) -> dict:
    cfg = db.get(SystemConfig, "comment_limits")
    if not cfg or not cfg.value:
        return _DEFAULTS
    try:
        return {**_DEFAULTS, **json.loads(cfg.value)}
    except Exception:
        return _DEFAULTS


def _classify_video(video: Video, limits: dict) -> str:
    v = video.view_count or 0
    if v >= limits["large_view_threshold"]:
        return "large"
    if v <= limits["small_view_threshold"]:
        return "small"
    return "medium"


def can_post_comment(
    db: Session,
    video_id: str,
    worker_id: int,
) -> tuple[bool, Optional[str]]:
    """캠페인 시작 전 한도 검증.

    Returns: (allowed, reason). 거부 시 reason 에 사유 코드.
    """
    video = db.get(Video, video_id)
    if video is None:
        return False, "video_not_found"

    limits = _load_limits(db)
    size = _classify_video(video, limits)
    size_max = {"large": limits["large_max"], "medium": limits["medium_max"],
                "small": limits["small_max"]}[size]

    now = datetime.now(UTC)
    cutoff_24h = now - timedelta(hours=24)

    # 1. 영상 크기별 24h 한도
    posted_24h = (
        db.query(func.count(CommentExecution.id))
        .filter(
            CommentExecution.video_id == video_id,
            CommentExecution.posted_at >= cutoff_24h,
        )
        .scalar()
        or 0
    )
    if posted_24h >= size_max:
        return False, f"video_24h_limit:{posted_24h}/{size_max}"

    # 2. 5분 간격
    last = (
        db.query(CommentExecution)
        .filter(CommentExecution.video_id == video_id)
        .order_by(CommentExecution.posted_at.desc())
        .first()
    )
    if last:
        last_posted = last.posted_at
        if last_posted.tzinfo is None:
            last_posted = last_posted.replace(tzinfo=UTC)
        if (now - last_posted) < timedelta(minutes=int(limits["min_interval_minutes"])):
            return False, "too_soon_after_last"

    # 3. 같은 워커 같은 영상 (30분 간격)
    same_worker = (
        db.query(CommentExecution)
        .filter(
            CommentExecution.video_id == video_id,
            CommentExecution.worker_id == worker_id,
        )
        .order_by(CommentExecution.posted_at.desc())
        .first()
    )
    if same_worker:
        last_posted = same_worker.posted_at
        if last_posted.tzinfo is None:
            last_posted = last_posted.replace(tzinfo=UTC)
        if (now - last_posted) < timedelta(minutes=30):
            return False, "same_worker_too_soon"

    # 4. 채널당 일 한도
    if video.channel_id:
        cutoff_today = now - timedelta(hours=24)
        channel_count = (
            db.query(func.count(func.distinct(CommentExecution.video_id)))
            .join(Video, Video.id == CommentExecution.video_id)
            .filter(
                CommentExecution.worker_id == worker_id,
                Video.channel_id == video.channel_id,
                CommentExecution.posted_at >= cutoff_today,
            )
            .scalar()
            or 0
        )
        if channel_count >= int(limits["channel_daily_max"]):
            return False, f"channel_daily_limit:{channel_count}"

    # 5. 영상 댓글 % 한도
    if video.comment_count and video.comment_count > 0:
        max_pct = float(limits["video_pct_max"])
        if posted_24h >= max(1, int(video.comment_count * max_pct)):
            return False, f"video_pct_limit:{posted_24h}/{video.comment_count}"

    return True, None


def compute_next_check_at(execution: CommentExecution, viral_threshold: int) -> Optional[datetime]:
    """추적 phase 별 다음 추적 시점 계산.

    hour: 0~24h, 6h 마다 (4회)
    day:  1~7일, 1일 1회 (6회)
    week: 7~30일, 화력 받은 댓글만 7일 1회
    ended: 30일+ 종료
    """
    now = datetime.now(UTC)
    posted = execution.posted_at
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    age_h = (now - posted).total_seconds() / 3600

    if age_h < 24:
        execution.tracking_phase = "hour"
        return now + timedelta(hours=6)
    if age_h < 24 * 7:
        execution.tracking_phase = "day"
        return now + timedelta(days=1)
    if age_h < 24 * 30:
        # week phase: viral 댓글만 추적
        if (execution.likes_count or 0) >= viral_threshold:
            execution.tracking_phase = "week"
            return now + timedelta(days=7)
        else:
            execution.tracking_phase = "ended"
            execution.tracking_status = "ended"
            return None
    execution.tracking_phase = "ended"
    execution.tracking_status = "ended"
    return None
