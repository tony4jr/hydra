"""홈 대시보드 파이프라인 흐름 집계.

PR-2b-1.

5단계 깔때기 카운트 + 병목 감지. 30s in-memory 캐시.

Stage 정의:
1. discovered      — Video.collected_at 윈도우 내
2. market_fit      — discovered + embedding_score >= 0.65
3. task_created    — Task.created_at 윈도우 + task_type in (comment, reply)
4. comment_posted  — ActionLog 윈도우 + action_type in (comment, reply) + is_promo
5. survived_24h    — CommentSnapshot 윈도우 + 24h+ 생존 (window_hours>=24만)

설계 결정 (CLAUDE.md/PR-2 사전점검):
- module-level sync 함수 (codebase 전체 패턴)
- market_fit threshold 0.65 글로벌 (PR-3 에서 per-niche)
- lock 없는 _cache (GIL + race 무해 / compute 중복 허용)
- niche_id 파라미터 X (PR-3 에서 추가)
- survived_24h 는 distinct youtube_comment_id (정밀화는 후속)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from hydra.db.models import ActionLog, CommentSnapshot, Task, Video
from hydra.services import _cache

DEFAULT_MARKET_FIT_THRESHOLD = 0.65  # PR-3 까지 글로벌 기준점
CACHE_TTL_SECONDS = 30
PASS_RATE_MIN_SAMPLE = 5  # 직전 stage 카운트가 이 미만이면 pass_rate=None

StageName = Literal[
    "discovered", "market_fit", "task_created",
    "comment_posted", "survived_24h",
]


class PipelineStageMetric(BaseModel):
    stage: StageName
    count: int
    pass_rate: float | None  # 직전 단계 대비 통과율 (0~1)
    is_bottleneck: bool


class PipelineFlowResponse(BaseModel):
    window_hours: int
    stages: list[PipelineStageMetric]
    bottleneck_message: str | None
    generated_at: datetime


def _calc_pass_rate(prev: int, current: int) -> float | None:
    if prev < PASS_RATE_MIN_SAMPLE:
        return None
    return current / prev


def _is_bottleneck(pass_rate: float | None) -> bool:
    """통과율 30% 미만이면 병목."""
    if pass_rate is None:
        return False
    return pass_rate < 0.30


def _bottleneck_message(stages: list[PipelineStageMetric]) -> str | None:
    """첫 번째 병목 단계의 사람용 메시지."""
    for s in stages:
        if s.is_bottleneck:
            name_kr = {
                "discovered": "발견",
                "market_fit": "시장 적합도",
                "task_created": "작업 생성",
                "comment_posted": "댓글 작성",
                "survived_24h": "24시간 생존",
            }[s.stage]
            pct = (s.pass_rate or 0) * 100
            return f"{name_kr} 단계 통과율 {pct:.0f}% — 검토 권장."
    return None


def _count_discovered(db: Session, cutoff: datetime) -> int:
    return (
        db.query(func.count(Video.id))
        .filter(Video.collected_at >= cutoff)
        .scalar()
        or 0
    )


def _count_market_fit(db: Session, cutoff: datetime, threshold: float) -> int:
    return (
        db.query(func.count(Video.id))
        .filter(
            Video.collected_at >= cutoff,
            Video.embedding_score >= threshold,
        )
        .scalar()
        or 0
    )


def _count_task_created(db: Session, cutoff: datetime) -> int:
    return (
        db.query(func.count(Task.id))
        .filter(
            Task.created_at >= cutoff,
            Task.task_type.in_(["comment", "reply"]),
        )
        .scalar()
        or 0
    )


def _count_comment_posted(db: Session, cutoff: datetime) -> int:
    return (
        db.query(func.count(ActionLog.id))
        .filter(
            ActionLog.created_at >= cutoff,
            ActionLog.action_type.in_(["comment", "reply"]),
            ActionLog.is_promo == True,  # noqa: E712
        )
        .scalar()
        or 0
    )


def _count_survived_24h(
    db: Session, cutoff: datetime, now: datetime
) -> int:
    """24h 이상 살아있는 promo 댓글 distinct count.

    기준:
    - posted_at <= now - 24h (24시간 이상 경과)
    - is_held == False, is_deleted == False
    - captured_at >= cutoff (윈도우 내 검증)
    """
    cutoff_24h = now - timedelta(hours=24)
    return (
        db.query(func.count(func.distinct(CommentSnapshot.youtube_comment_id)))
        .filter(
            CommentSnapshot.captured_at >= cutoff,
            CommentSnapshot.posted_at <= cutoff_24h,
            CommentSnapshot.posted_at.isnot(None),
            CommentSnapshot.is_held == False,  # noqa: E712
            CommentSnapshot.is_deleted == False,  # noqa: E712
        )
        .scalar()
        or 0
    )


def _compute_flow(
    db: Session,
    window_hours: int,
    threshold: float,
) -> PipelineFlowResponse:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)

    discovered = _count_discovered(db, cutoff)
    market_fit = _count_market_fit(db, cutoff, threshold)
    task_created = _count_task_created(db, cutoff)
    comment_posted = _count_comment_posted(db, cutoff)
    survived_24h = (
        _count_survived_24h(db, cutoff, now) if window_hours >= 24 else 0
    )

    counts = {
        "discovered": discovered,
        "market_fit": market_fit,
        "task_created": task_created,
        "comment_posted": comment_posted,
        "survived_24h": survived_24h,
    }

    order: list[StageName] = [
        "discovered", "market_fit", "task_created",
        "comment_posted", "survived_24h",
    ]
    stages: list[PipelineStageMetric] = []
    prev_count = None
    for name in order:
        cur = counts[name]
        rate = _calc_pass_rate(prev_count, cur) if prev_count is not None else None
        stages.append(PipelineStageMetric(
            stage=name,
            count=cur,
            pass_rate=rate,
            is_bottleneck=_is_bottleneck(rate),
        ))
        prev_count = cur

    return PipelineFlowResponse(
        window_hours=window_hours,
        stages=stages,
        bottleneck_message=_bottleneck_message(stages),
        generated_at=now,
    )


def get_pipeline_flow(
    db: Session,
    window_hours: int = 24,
    threshold: float = DEFAULT_MARKET_FIT_THRESHOLD,
) -> PipelineFlowResponse:
    """파이프라인 흐름 집계 — 30s 캐시.

    Args:
        db: SQLAlchemy session.
        window_hours: 집계 윈도우 (1, 6, 12, 24 권장).
        threshold: market_fit embedding score 임계값.

    Returns:
        PipelineFlowResponse — 5 stages + 병목 메시지.
    """
    key = f"pipeline_flow:wh={window_hours}:th={threshold}"
    return _cache.cached(
        key=key,
        ttl=CACHE_TTL_SECONDS,
        compute=lambda: _compute_flow(db, window_hours, threshold),
    )
