"""Phase 1 — L 티어 + Lifecycle Phase 분류.

L 티어:
  L2: 신규 (업로드 6시간 이내) — 시간 민감, 최우선
  L3: 트렌딩 (시간당 조회수 급증)
  L1: 점수 임계값 이상 — 영구 자산
  L4: 그 외 — 롱테일

Lifecycle Phase (영상 나이 기준):
  1: 신규 (업로드 7일 이내) — revisit 1일
  2: 안정화 (~1개월) — revisit 3일
  3: 에버그린 (~6개월) — revisit 14일
  4: 장기 자산 (6개월+) — revisit 90일
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session

from hydra.db.models import Video, TargetCollectionConfig
from hydra.services._niche_helper import get_niche_for_target


# Phase 별 한도 (작업 빈도 + 재방문 간격)
PHASE_LIMITS = {
    1: {  # T+0~7일
        "max_scenarios_24h": 2,
        "max_scenarios_7d": 3,
        "max_likes_24h": 30,
        "max_likes_7d": 80,
        "revisit_interval_days": 1,
    },
    2: {  # T+7일~1개월
        "max_scenarios_24h": 1,
        "max_scenarios_7d": 2,
        "max_likes_24h": 20,
        "max_likes_7d": 50,
        "revisit_interval_days": 3,
    },
    3: {  # T+1~6개월
        "max_scenarios_24h": 1,
        "max_scenarios_7d": 1,
        "max_likes_24h": 15,
        "max_likes_7d": 30,
        "revisit_interval_days": 14,
    },
    4: {  # T+6개월+
        "max_scenarios_24h": 1,
        "max_scenarios_7d": 1,
        "max_likes_24h": 10,
        "max_likes_7d": 20,
        "revisit_interval_days": 90,
    },
}


def compute_lifecycle_phase(video: Video, now: datetime | None = None) -> int:
    """업로드 후 경과일로 phase 결정."""
    now = now or datetime.now(UTC)
    if video.published_at is None:
        return 4  # 알 수 없으면 보수적 (장기 자산처럼 취급)

    pub = video.published_at
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=UTC)

    age_days = (now - pub).total_seconds() / 86400
    if age_days < 7:
        return 1
    if age_days < 30:
        return 2
    if age_days < 180:
        return 3
    return 4


def compute_l_tier(
    db: Session,
    video: Video,
    target_id: int,
    now: datetime | None = None,
) -> str:
    """L1~L4 결정.

    우선순위: L2 (신규) > L3 (트렌딩) > L1 (점수 ≥ threshold) > L4 (나머지)
    """
    now = now or datetime.now(UTC)
    niche = get_niche_for_target(db, target_id)
    cfg = db.get(TargetCollectionConfig, target_id)

    # L2: 업로드 N시간 이내 (신규 진입 윈도우 — Niche.new_video_hours, default 6)
    new_video_hours = (niche.new_video_hours if niche else None) or 6
    if video.published_at:
        pub = video.published_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=UTC)
        age_hours = (now - pub).total_seconds() / 3600
        if age_hours < new_video_hours:
            return "L2"

    # L3: 시간당 조회수 급증 (Niche.trending_vph_threshold fallback to TCC.l3_views_per_hour_threshold)
    if niche is not None:
        threshold_l3 = niche.trending_vph_threshold or 1000
    else:
        threshold_l3 = (cfg.l3_views_per_hour_threshold if cfg else 1000) or 1000
    if (video.views_per_hour_recent or 0) > threshold_l3:
        return "L3"

    # L1: 점수 임계값 이상 (Niche.long_term_score_threshold fallback to TCC.l1_threshold_score)
    if niche is not None:
        threshold_l1 = niche.long_term_score_threshold or 70.0
    else:
        threshold_l1 = (cfg.l1_threshold_score if cfg else 70.0) or 70.0
    score = video.relevance_score_v2 or (video.popularity_score or 0) * 100
    if score >= threshold_l1:
        return "L1"

    # L4: 나머지
    return "L4"


def compute_next_revisit_at(
    video: Video,
    now: datetime | None = None,
) -> datetime:
    """Phase 별 revisit interval 적용. last_action_at 기준.

    아직 한 번도 작업 안 했으면 즉시 (now).
    """
    now = now or datetime.now(UTC)
    if video.last_action_at is None:
        return now

    phase = video.lifecycle_phase or compute_lifecycle_phase(video, now)
    interval_days = PHASE_LIMITS.get(phase, PHASE_LIMITS[4])["revisit_interval_days"]

    last = video.last_action_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return last + timedelta(days=interval_days)


def classify_video(
    db: Session,
    video: Video,
    target_id: int,
    now: datetime | None = None,
) -> None:
    """영상에 L tier + lifecycle_phase + next_revisit_at 채움.

    호출자가 db.commit() 책임.
    """
    now = now or datetime.now(UTC)
    video.lifecycle_phase = compute_lifecycle_phase(video, now)
    video.l_tier = compute_l_tier(db, video, target_id, now)
    video.next_revisit_at = compute_next_revisit_at(video, now)


def get_phase_limits(phase: int | None) -> dict:
    """Phase 한도 조회 (한도 체크 시 사용)."""
    if phase is None:
        return PHASE_LIMITS[4]
    return PHASE_LIMITS.get(phase, PHASE_LIMITS[4])
