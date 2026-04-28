"""Phase 1 — Hard Block + 부정 키워드 + 채널 블랙리스트 필터.

영상이 풀에 들어갈 만한지 판단. 통과 못 하면 video.state='blacklisted' + reason 저장.
"""
from __future__ import annotations

from datetime import datetime, UTC
from sqlalchemy.orm import Session

from hydra.db.models import (
    Brand, Video, Keyword, ChannelBlacklist, TargetCollectionConfig,
)


# ─────────────────────────────────────────────────────────────────
# Defaults — 운영 권장값 (어드민에서 override 가능)
# ─────────────────────────────────────────────────────────────────

DEFAULTS = {
    "hard_block_min_video_seconds": 30,
    "exclude_kids_category": True,
    "exclude_live_streaming": True,
    "embedding_threshold": 0.65,
    "l1_threshold_score": 70.0,
    "l3_views_per_hour_threshold": 1000,
    "l2_max_age_hours": 24,
}

YOUTUBE_KIDS_CATEGORY_ID = 15  # YouTube 카테고리 "Pets & Animals" — 키즈 영상 다수 분류됨


def get_or_create_config(db: Session, target_id: int) -> TargetCollectionConfig:
    """Brand 의 collection config 가져오기 (없으면 default 로 생성)."""
    cfg = db.get(TargetCollectionConfig, target_id)
    if cfg is None:
        cfg = TargetCollectionConfig(target_id=target_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


# ─────────────────────────────────────────────────────────────────
# Hard Block — 즉시 제외
# ─────────────────────────────────────────────────────────────────

def passes_hard_block(video_data: dict, target_id: int, db: Session) -> tuple[bool, str | None]:
    """영상이 hard block 룰 통과하는지. 통과하면 (True, None), 실패하면 (False, reason)."""
    cfg = get_or_create_config(db, target_id)

    # 1. 댓글 비활성화
    if video_data.get("comments_enabled") is False:
        return False, "comments_disabled"
    if video_data.get("comment_count") is None:
        return False, "comment_count_missing"

    # 2. 키즈 카테고리
    if cfg.exclude_kids_category:
        cat = video_data.get("category_id")
        if cat is not None and int(cat) == YOUTUBE_KIDS_CATEGORY_ID:
            return False, "kids_category"

    # 3. 라이브 스트리밍 진행 중
    if cfg.exclude_live_streaming:
        live = video_data.get("live_broadcast_content")
        if live == "live":
            return False, "live_streaming"

    # 4. 영상 길이 임계값 미달
    duration = video_data.get("duration_sec") or 0
    if duration < cfg.hard_block_min_video_seconds:
        return False, f"too_short_{duration}s"

    return True, None


# ─────────────────────────────────────────────────────────────────
# 부정 키워드 (target 별)
# ─────────────────────────────────────────────────────────────────

def passes_negative_keywords(
    db: Session,
    title: str,
    description: str,
    target_id: int,
) -> tuple[bool, str | None]:
    """타겟의 부정 키워드 (is_negative=True) 가 영상 텍스트에 포함되는지.

    한 개라도 매칭되면 False.
    """
    negative = (
        db.query(Keyword)
        .filter(
            Keyword.brand_id == target_id,
            Keyword.is_negative.is_(True),
            Keyword.status == "active",
        )
        .all()
    )
    if not negative:
        return True, None

    text = f"{title or ''} {description or ''}".lower()
    for nk in negative:
        if nk.text and nk.text.lower() in text:
            return False, f"negative_keyword:{nk.text}"
    return True, None


# ─────────────────────────────────────────────────────────────────
# 채널 블랙리스트 (target 별 + 글로벌)
# ─────────────────────────────────────────────────────────────────

def passes_channel_blacklist(
    db: Session,
    channel_id: str,
    target_id: int,
) -> tuple[bool, str | None]:
    """채널이 블랙리스트에 있는지. 글로벌 (target_id NULL) 또는 타겟별."""
    if not channel_id:
        return True, None

    # 글로벌 블랙리스트
    glob = db.query(ChannelBlacklist).filter(
        ChannelBlacklist.channel_id == channel_id,
        ChannelBlacklist.target_id.is_(None),
    ).first()
    if glob:
        return False, f"channel_blacklist_global:{glob.reason or 'unknown'}"

    # 타겟별 블랙리스트
    tgt = db.query(ChannelBlacklist).filter(
        ChannelBlacklist.channel_id == channel_id,
        ChannelBlacklist.target_id == target_id,
    ).first()
    if tgt:
        return False, f"channel_blacklist_target:{tgt.reason or 'unknown'}"

    return True, None


# ─────────────────────────────────────────────────────────────────
# 모든 필터 통합 — process_video 에서 호출
# ─────────────────────────────────────────────────────────────────

def evaluate_video(
    db: Session,
    video_data: dict,
    target_id: int,
) -> tuple[bool, str | None]:
    """모든 룰 필터 한 번에 검사. (passed, reason).

    video_data 필요한 키:
      - title, description, channel_id
      - comments_enabled, comment_count, category_id, live_broadcast_content, duration_sec
    """
    # 1. Hard block
    ok, reason = passes_hard_block(video_data, target_id, db)
    if not ok:
        return False, reason

    # 2. 부정 키워드
    ok, reason = passes_negative_keywords(
        db,
        video_data.get("title", ""),
        video_data.get("description", ""),
        target_id,
    )
    if not ok:
        return False, reason

    # 3. 채널 블랙리스트
    ok, reason = passes_channel_blacklist(
        db,
        video_data.get("channel_id", ""),
        target_id,
    )
    if not ok:
        return False, reason

    return True, None
