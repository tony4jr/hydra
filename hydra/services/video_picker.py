"""Smart video picker — 점수 가중 랜덤 픽업.

캠페인 자동 생성 시 풀에서 영상을 어떻게 고를지 결정.
기존 auto_create_campaigns 와 공존 — feature flag (Brand.collection_depth or settings) 로 선택.

점수 = α × 신선도 + β × 인기도 + γ × 미작업도 + δ × 무작위
- 신선도: 수집 후 경과일 (7일 내 1.0, 1년 후 0.0)
- 인기도: log10(view_count) / 7  (1000만뷰 ≈ 1.0)
- 미작업도: last_worked_at 경과일 / 30  (한 번도 안 했으면 1.0)
- 무작위: random(0,1)

카테고리 비율 강제:
- 45% 신규 (수집 7일 내 + 미작업)
- 30% 인기 백로그 (조회수 100만+ + 미작업)
- 15% 재방문 (이미 작업, 7일 경과)
- 10% 일반 백로그 (나머지 미작업)
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, UTC
from typing import Iterable

from sqlalchemy.orm import Session

from hydra.db.models import Brand, Video, Campaign


DEFAULT_WEIGHTS = {
    "freshness": 0.3,
    "popularity": 0.3,
    "untouched": 0.3,
    "random": 0.1,
}

CATEGORY_RATIOS = {
    "fresh": 0.45,        # 수집 7일 내 + 미작업
    "popular_backlog": 0.30,  # 조회수 100만+ + 미작업
    "revisit": 0.15,      # 이미 작업, 7일+ 경과
    "general_backlog": 0.10,  # 나머지 미작업
}


def _get_brand_weights(brand: Brand) -> dict:
    if brand and brand.scoring_weights:
        try:
            w = json.loads(brand.scoring_weights)
            return {**DEFAULT_WEIGHTS, **w}
        except (ValueError, TypeError):
            pass
    return DEFAULT_WEIGHTS


def _score(video: Video, weights: dict, now: datetime) -> float:
    # 신선도 — 수집 후 경과일 기반
    if video.collected_at:
        # collected_at 이 timezone-naive 면 UTC 로 가정
        coll = video.collected_at if video.collected_at.tzinfo else video.collected_at.replace(tzinfo=UTC)
        age_days = (now - coll).total_seconds() / 86400
        freshness = max(0.0, 1.0 - age_days / 365)  # 1년 후 0
    else:
        freshness = 0.5

    # 인기도 — popularity_score 사용 (수집 시 계산), 없으면 view_count 로 즉석
    if video.popularity_score is not None:
        popularity = max(0.0, min(1.0, video.popularity_score))
    elif video.view_count:
        popularity = math.log10(video.view_count + 1) / 7.0
        popularity = max(0.0, min(1.0, popularity))
    else:
        popularity = 0.0

    # 미작업도 — last_worked_at 경과
    if video.last_worked_at is None:
        untouched = 1.0
    else:
        lw = video.last_worked_at if video.last_worked_at.tzinfo else video.last_worked_at.replace(tzinfo=UTC)
        days_since = (now - lw).total_seconds() / 86400
        untouched = min(1.0, days_since / 30)  # 30일 후 1.0

    rnd = random.random()

    return (
        weights["freshness"] * freshness
        + weights["popularity"] * popularity
        + weights["untouched"] * untouched
        + weights["random"] * rnd
    )


def _categorize(videos: list[Video], now: datetime) -> dict[str, list[Video]]:
    fresh, popular_backlog, revisit, general_backlog = [], [], [], []
    seven_days = timedelta(days=7)
    for v in videos:
        coll_aware = v.collected_at.replace(tzinfo=UTC) if (v.collected_at and not v.collected_at.tzinfo) else v.collected_at
        is_recent_collection = coll_aware and (now - coll_aware) < seven_days
        is_high_view = (v.view_count or 0) >= 1_000_000
        is_worked_recently = False
        if v.last_worked_at:
            lw_aware = v.last_worked_at.replace(tzinfo=UTC) if not v.last_worked_at.tzinfo else v.last_worked_at
            is_worked_recently = (now - lw_aware) < seven_days

        if v.last_worked_at and not is_worked_recently:
            revisit.append(v)
        elif v.last_worked_at:
            # 너무 최근에 작업 → 제외 (video_protection 영역)
            continue
        elif is_recent_collection:
            fresh.append(v)
        elif is_high_view:
            popular_backlog.append(v)
        else:
            general_backlog.append(v)
    return {
        "fresh": fresh,
        "popular_backlog": popular_backlog,
        "revisit": revisit,
        "general_backlog": general_backlog,
    }


def _weighted_random_sample(scored: list[tuple[Video, float]], k: int) -> list[Video]:
    """점수를 확률로 변환 (softmax 비슷) → 비복원 가중 랜덤 샘플링."""
    if not scored or k <= 0:
        return []
    pool = scored.copy()
    picked = []
    while pool and len(picked) < k:
        weights = [s for _, s in pool]
        # 모든 점수 0 이면 균등 랜덤
        total = sum(weights)
        if total <= 0:
            choice_idx = random.randrange(len(pool))
        else:
            r = random.uniform(0, total)
            cum = 0.0
            choice_idx = 0
            for i, (_, s) in enumerate(pool):
                cum += s
                if r <= cum:
                    choice_idx = i
                    break
        picked.append(pool.pop(choice_idx)[0])
    return picked


def smart_pick_videos(
    db: Session,
    brand_id: int,
    n: int = 50,
    exclude_video_ids: set[str] | None = None,
) -> list[Video]:
    """브랜드 풀에서 점수 가중 랜덤으로 N개 픽.

    exclude: 이미 캠페인 도는 영상 등 제외할 ID 셋.
    """
    brand = db.get(Brand, brand_id)
    if not brand:
        return []

    weights = _get_brand_weights(brand)
    now = datetime.now(UTC)
    exclude_video_ids = exclude_video_ids or set()

    # 풀 — 브랜드 키워드들의 영상, available 상태, 댓글 활성, 제외 ID 빼고
    from hydra.db.models import Keyword
    keyword_ids = [
        k.id for k in db.query(Keyword.id).filter(Keyword.brand_id == brand_id).all()
    ]
    if not keyword_ids:
        return []

    pool = (
        db.query(Video)
        .filter(
            Video.keyword_id.in_(keyword_ids),
            Video.status == "available",
            Video.comments_enabled.is_(True),
            ~Video.id.in_(exclude_video_ids) if exclude_video_ids else True,
        )
        .all()
    )
    if not pool:
        return []

    # 카테고리 분류
    cats = _categorize(pool, now)

    # 카테고리별 점수 + 비율대로 픽
    picks: list[Video] = []
    for cat_name, ratio in CATEGORY_RATIOS.items():
        cat_videos = cats.get(cat_name, [])
        if not cat_videos:
            continue
        target_count = max(1, int(n * ratio))
        scored = [(v, _score(v, weights, now)) for v in cat_videos]
        picks.extend(_weighted_random_sample(scored, target_count))

    # 부족하면 전체 풀에서 보충
    if len(picks) < n:
        remaining = [v for v in pool if v not in picks]
        scored = [(v, _score(v, weights, now)) for v in remaining]
        picks.extend(_weighted_random_sample(scored, n - len(picks)))

    return picks[:n]
