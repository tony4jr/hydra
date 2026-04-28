"""Phase 1 — YouTube API quota 모니터링 + 자동 다운그레이드.

5분 폴링 도입으로 quota 소비 급증. 90% 도달 시 5min→10min 자동 전환.
무료 키 한 개 = 10,000 unit/일.
search.list = 100 unit/call. videos.list = 1 unit/call.

운영 첫날 quota 소진 사고 방지.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, UTC
from sqlalchemy.orm import Session

from hydra.db.models import YoutubeQuotaLog

log = logging.getLogger(__name__)


# 무료 키 한 개당 일일 한도 (default; 어드민에서 override 가능 추후)
DEFAULT_DAILY_LIMIT = 10_000

# 임계값 — 어느 시점에 알람 + 자동 다운그레이드
WARN_PCT = 70   # 70% 도달 시 알람
THROTTLE_PCT = 90  # 90% 도달 시 5min→10min 다운그레이드


def _today_utc() -> date:
    return datetime.now(UTC).date()


def record_usage(
    db: Session,
    api_key_index: int,
    cost: int,
) -> None:
    """API 호출 후 quota 사용량 기록. 호출자가 commit."""
    today = _today_utc()
    row = (
        db.query(YoutubeQuotaLog)
        .filter(
            YoutubeQuotaLog.api_key_index == api_key_index,
            YoutubeQuotaLog.day == today,
        )
        .first()
    )
    if row is None:
        row = YoutubeQuotaLog(
            api_key_index=api_key_index,
            day=today,
            quota_used=0,
        )
        db.add(row)
        db.flush()
    row.quota_used = (row.quota_used or 0) + cost
    row.last_request_at = datetime.now(UTC)


def get_today_usage(db: Session, api_key_index: int) -> int:
    """오늘 해당 키의 사용량."""
    today = _today_utc()
    row = (
        db.query(YoutubeQuotaLog)
        .filter(
            YoutubeQuotaLog.api_key_index == api_key_index,
            YoutubeQuotaLog.day == today,
        )
        .first()
    )
    return (row.quota_used if row else 0) or 0


def get_total_usage_today(db: Session) -> int:
    """오늘 모든 키 합산 사용량."""
    today = _today_utc()
    rows = db.query(YoutubeQuotaLog).filter(YoutubeQuotaLog.day == today).all()
    return sum((r.quota_used or 0) for r in rows)


def check_throttle_state(db: Session, num_keys: int) -> dict:
    """전체 quota 상태 + 5min 폴링 다운그레이드 필요 여부 판정.

    Returns:
        {
            "total_used": N,
            "total_limit": L,
            "pct_used": p,
            "should_warn": bool,
            "should_throttle": bool,  # True 면 5min 폴링 정지하고 10min 으로
        }
    """
    total_used = get_total_usage_today(db)
    total_limit = DEFAULT_DAILY_LIMIT * max(num_keys, 1)
    pct = (total_used / total_limit * 100) if total_limit > 0 else 0
    return {
        "total_used": total_used,
        "total_limit": total_limit,
        "pct_used": round(pct, 1),
        "should_warn": pct >= WARN_PCT,
        "should_throttle": pct >= THROTTLE_PCT,
    }


def should_skip_5min_poll(db: Session, num_keys: int) -> bool:
    """5분 폴링 직전 호출 — quota 90%+ 면 스킵."""
    state = check_throttle_state(db, num_keys)
    if state["should_throttle"]:
        log.warning(f"YouTube quota at {state['pct_used']}% — 5min poll skipped")
        return True
    return False
