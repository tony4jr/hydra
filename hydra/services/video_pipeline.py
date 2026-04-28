"""Phase 1 — 통합 영상 처리 파이프라인.

영상 1건 (search 결과 + 메타) 입력 → 모든 필터·분류 거쳐 풀에 진입.

흐름:
  1. UPSERT Video
  2. Hard Block / 부정 키워드 / 채널 블랙리스트 → 실패 시 blacklisted
  3. 임베딩 분류 → 실패 시 blacklisted
  4. (Phase 2 LLM 분류 — 일단 skip)
  5. L 티어 + Lifecycle Phase + next_revisit_at
  6. 키워드 매칭 기록 (검색 노출도 점수용)
  7. state='active' 로 전환 (필터 통과 시)
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, UTC
from sqlalchemy.orm import Session

from hydra.db.models import (
    Video, Keyword, VideoKeywordMatch,
)
from hydra.services.video_filter import evaluate_video
from hydra.services.video_embedding import classify_by_embedding
from hydra.services.video_classifier import classify_video

log = logging.getLogger(__name__)


def _upsert_keyword_match(
    db: Session,
    video_id: str,
    keyword_id: int,
    search_rank: int | None = None,
) -> None:
    """검색 노출 기록 (UPSERT). 호출자가 commit."""
    existing = (
        db.query(VideoKeywordMatch)
        .filter(
            VideoKeywordMatch.video_id == video_id,
            VideoKeywordMatch.keyword_id == keyword_id,
        )
        .first()
    )
    if existing:
        if search_rank is not None and (existing.search_rank is None or search_rank < existing.search_rank):
            existing.search_rank = search_rank
        return
    db.add(VideoKeywordMatch(
        video_id=video_id,
        keyword_id=keyword_id,
        search_rank=search_rank,
    ))


def _set_blacklist(video: Video, reason: str) -> None:
    video.state = "blacklisted"
    video.blacklist_reason = reason


def process_video(
    db: Session,
    video: Video,
    target_id: int,
    keyword: Keyword | None = None,
    search_rank: int | None = None,
    skip_embedding: bool = False,
) -> str:
    """영상 1건 파이프라인 실행. video 는 이미 DB 에 INSERT 또는 UPDATE 된 상태.

    Returns: 'active' | 'blacklisted' | 'pending'.
    호출자가 commit.
    """
    # 키워드 매칭 (검색 노출도 점수용 — 항상 기록, 필터 결과와 무관)
    if keyword is not None:
        _upsert_keyword_match(db, video.id, keyword.id, search_rank)

    # 이미 blacklisted 면 재평가 안 함 (운영자가 수동 active 로 풀어준 경우만 다시 들어옴)
    if video.state == "blacklisted":
        return "blacklisted"

    # 1. 룰 필터 (hard block + 부정 키워드 + 채널 블랙리스트)
    video_data = {
        "title": video.title,
        "description": video.description,
        "channel_id": video.channel_id,
        "comments_enabled": video.comments_enabled,
        "comment_count": video.comment_count,
        "duration_sec": video.duration_sec,
        # category_id, live_broadcast_content 는 enrich 시 함께 와야 — 일단 None
    }
    ok, reason = evaluate_video(db, video_data, target_id)
    if not ok:
        _set_blacklist(video, reason or "rule_filter_failed")
        return "blacklisted"

    # 2. 임베딩 분류 (Phase 1)
    if not skip_embedding and video.embedding_score is None:
        ok, reason = classify_by_embedding(db, video, target_id)
        if not ok:
            _set_blacklist(video, reason or "embedding_failed")
            return "blacklisted"

    # 3. (Phase 2: LLM 카테고리 — 일단 skip)
    # 4. (Phase 2: 5점수 계산 — 일단 skip, popularity_score 그대로 사용)

    # 5. L 티어 + Lifecycle Phase + revisit
    classify_video(db, video, target_id)

    # 6. state='active' 로 전환
    if video.state == "pending":
        video.state = "active"

    return "active"


def reprocess_existing_videos(
    db: Session,
    target_id: int,
    states: list[str] = None,
    limit: int = 100,
) -> dict:
    """기존 풀의 영상들에 Phase 1 분류 재적용 (한 번에 limit 개씩 배치).

    Phase 1 도입 직후 backfill 용. 운영 안정화 후엔 매일 nightly batch 로 갱신.
    """
    states = states or ["pending", "active", "available"]

    # Brand 의 키워드들에 묶인 영상들
    keyword_ids = [
        k.id for k in db.query(Keyword.id).filter(Keyword.brand_id == target_id).all()
    ]
    if not keyword_ids:
        return {"processed": 0, "active": 0, "blacklisted": 0}

    videos = (
        db.query(Video)
        .filter(
            Video.keyword_id.in_(keyword_ids),
            Video.state.in_(states),
        )
        .limit(limit)
        .all()
    )

    counts = {"processed": 0, "active": 0, "blacklisted": 0}
    for v in videos:
        # Status 가 'available' 같은 legacy 면 'pending' 로 정상화
        if v.state in ("available", None):
            v.state = "pending"
        result = process_video(db, v, target_id)
        counts["processed"] += 1
        counts[result] = counts.get(result, 0) + 1

    db.commit()
    return counts
