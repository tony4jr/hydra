"""Video score 계산 (PR-8f).

100점 (최신성 40 + 조회수 30 + 키워드 30) + 부스트 + 안전필터.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from typing import Optional

from sqlalchemy.orm import Session

from hydra.db.models import SystemConfig, Video, VideoScore


_DEFAULT_WEIGHTS = {
    "recency": 40,
    "view": 30,
    "keyword": 30,
    "boost_channel": 20,
    "boost_video": 50,
    "longrun_threshold": 10000,
}


def _load_weights(db: Session) -> dict:
    cfg = db.get(SystemConfig, "video_score_weights")
    if not cfg or not cfg.value:
        return _DEFAULT_WEIGHTS
    try:
        return {**_DEFAULT_WEIGHTS, **json.loads(cfg.value)}
    except Exception:
        return _DEFAULT_WEIGHTS


def _recency_score(video: Video, max_pts: int) -> int:
    if not video.published_at:
        return 0
    pub = video.published_at
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=UTC)
    age_h = (datetime.now(UTC) - pub).total_seconds() / 3600
    if age_h < 24:
        return max_pts
    if age_h < 24 * 3:
        return int(max_pts * 0.75)
    if age_h < 24 * 7:
        return int(max_pts * 0.5)
    if age_h < 24 * 14:
        return int(max_pts * 0.25)
    return 0


def _view_score(video: Video, max_pts: int) -> int:
    v = video.view_count or 0
    if v >= 1_000_000:
        return max_pts
    if v <= 10_000:
        return 0
    # linear 1만~100만
    ratio = (v - 10_000) / (1_000_000 - 10_000)
    return int(max_pts * ratio)


def _keyword_score(video: Video, max_pts: int) -> int:
    es = video.embedding_score or 0
    return int(max_pts * max(0.0, min(1.0, es)))


def _safety_filter(video: Video) -> Optional[str]:
    """절대 제외 사유. None = 통과."""
    es = video.embedding_score
    if es is not None and es < 0.05:
        return "low_keyword_match"
    # FavoriteVideo / ProtectedVideo 는 PR-8h 후 통합
    return None


def compute_score(db: Session, video: Video) -> VideoScore:
    """단일 영상 점수 계산 + DB upsert."""
    w = _load_weights(db)

    safety = _safety_filter(video)
    if safety:
        recency = view = keyword = 0
        total = 0
    else:
        recency = _recency_score(video, int(w["recency"]))
        view = _view_score(video, int(w["view"]))
        keyword = _keyword_score(video, int(w["keyword"]))
        total = recency + view + keyword

    # PR-8h FavoriteChannel/FavoriteVideo 후 boost 적용
    boost_ch = 0
    boost_v = 0
    total += boost_ch + boost_v

    existing = db.get(VideoScore, video.id)
    if existing is None:
        existing = VideoScore(video_id=video.id)
        db.add(existing)
    existing.recency_score = recency
    existing.view_score = view
    existing.keyword_score = keyword
    existing.boost_favorite_channel = boost_ch
    existing.boost_favorite_video = boost_v
    existing.total_score = total
    existing.safety_filter_reason = safety
    existing.calculated_at = datetime.now(UTC)

    # is_longrun 자동 분류 (일평균 조회수 ≥ longrun_threshold)
    if video.view_count and video.collected_at:
        days = max(1, (datetime.now(UTC) - (
            video.collected_at if video.collected_at.tzinfo
            else video.collected_at.replace(tzinfo=UTC)
        )).days)
        avg = video.view_count / days
        if avg >= int(w["longrun_threshold"]):
            video.is_longrun = True

    return existing
