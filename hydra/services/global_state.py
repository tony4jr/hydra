"""Phase 1 — youtube_video_global_state 동기화.

같은 YouTube 영상이 여러 타겟에서 동시 작전 중일 때 충돌 방지.
- total_actions_24h: 24h 내 모든 타겟의 액션 합산
- active_target_count: 작전 중인 타겟 수
- can_create_scenario: 시나리오 생성 가능 여부 판정
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session

from hydra.db.models import YoutubeVideoGlobalState


# 글로벌 안전 한도 (운영 권장 디폴트)
GLOBAL_LIMITS = {
    "max_actions_24h": 30,           # 24시간 내 액션 합산 한도
    "max_active_scenarios": 2,        # 동시 시나리오 인스턴스 한도
    "min_main_comment_interval_h": 6,  # 메인 댓글 간격 (시간)
}


def upsert_global_state(
    db: Session,
    youtube_video_id: str,
) -> YoutubeVideoGlobalState:
    """글로벌 상태 row 가져오거나 생성. 호출자가 commit."""
    row = db.get(YoutubeVideoGlobalState, youtube_video_id)
    if row is None:
        row = YoutubeVideoGlobalState(youtube_video_id=youtube_video_id)
        db.add(row)
        db.flush()
    return row


def can_create_scenario(
    db: Session,
    youtube_video_id: str,
    is_main_comment: bool = False,
) -> tuple[bool, str | None]:
    """시나리오 생성 가능한지 판정.

    Returns:
        (allowed, reason). 차단 시 reason 에 사유.
    """
    row = db.get(YoutubeVideoGlobalState, youtube_video_id)
    if row is None:
        return True, None  # 처음이면 OK

    now = datetime.now(UTC)

    # 24h 액션 합산
    if row.total_actions_24h >= GLOBAL_LIMITS["max_actions_24h"]:
        return False, f"24h_actions:{row.total_actions_24h}"

    # 동시 시나리오 수
    if row.active_scenario_count >= GLOBAL_LIMITS["max_active_scenarios"]:
        return False, f"active_scenarios:{row.active_scenario_count}"

    # 메인 댓글 간격
    if is_main_comment and row.last_main_comment_at:
        last = row.last_main_comment_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        elapsed = (now - last).total_seconds() / 3600
        if elapsed < GLOBAL_LIMITS["min_main_comment_interval_h"]:
            return False, f"main_comment_interval:{elapsed:.1f}h"

    return True, None


def record_action(
    db: Session,
    youtube_video_id: str,
    action_type: str,
    target_id: int,
    is_main_comment: bool = False,
) -> None:
    """액션 발생 시 글로벌 상태 갱신.

    호출자가 commit. action_type: comment|reply|like|like_boost.
    """
    now = datetime.now(UTC)
    row = upsert_global_state(db, youtube_video_id)

    # action log 갱신 (최근 100개만 유지)
    log_data = []
    if row.recent_action_log:
        try:
            log_data = json.loads(row.recent_action_log)
        except (ValueError, TypeError):
            log_data = []
    log_data.append({
        "ts": now.isoformat(),
        "type": action_type,
        "target_id": target_id,
    })
    log_data = log_data[-100:]  # 최근 100개
    row.recent_action_log = json.dumps(log_data, ensure_ascii=False)

    # 24h / 7d 카운트 재계산
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    row.total_actions_24h = sum(1 for x in log_data if x["ts"] >= cutoff_24h)
    row.total_actions_7d = sum(1 for x in log_data if x["ts"] >= cutoff_7d)

    row.last_action_at = now
    if is_main_comment:
        row.last_main_comment_at = now


def increment_active_scenario(db: Session, youtube_video_id: str, delta: int = 1) -> None:
    """시나리오 시작/종료 시 active count 갱신."""
    row = upsert_global_state(db, youtube_video_id)
    row.active_scenario_count = max(0, (row.active_scenario_count or 0) + delta)


def increment_active_target(db: Session, youtube_video_id: str, delta: int = 1) -> None:
    """다른 타겟이 이 영상에 작전 시작/종료 시."""
    row = upsert_global_state(db, youtube_video_id)
    row.active_target_count = max(0, (row.active_target_count or 0) + delta)
