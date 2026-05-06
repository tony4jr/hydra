"""YouTube API 키 풀 셀렉터 — 라운드로빈 + 할당량 추적.

자정 PT 에 YouTube Data API quota 가 리셋됨. 호출 시점에 last_reset_at 을 비교해
lazy reset.

호출 비용 (대략):
- search.list = 100
- videos.list = 1
- 그 외 = 1 (보수적)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from threading import Lock

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.db.models import YouTubeApiKey
from hydra.db.session import SessionLocal

log = get_logger("youtube_keys")

_PT_OFFSET_HOURS = 8  # PST 기준 보수적 오프셋
_rr_lock = Lock()
_rr_cursor = 0


def _pt_midnight_for(now: datetime) -> datetime:
    pt_now = now - timedelta(hours=_PT_OFFSET_HOURS)
    pt_midnight = pt_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return pt_midnight + timedelta(hours=_PT_OFFSET_HOURS)


def _maybe_reset(key: YouTubeApiKey, now: datetime) -> bool:
    pt_midnight = _pt_midnight_for(now)
    last = key.last_reset_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is None or last < pt_midnight:
        key.quota_used_today = 0
        key.last_reset_at = now
        if key.status == "exhausted":
            key.status = "active"
            key.exhausted_at = None
        return True
    return False


def pick_active_key(db: Session) -> YouTubeApiKey | None:
    """라운드로빈으로 active 키 1개 선택. 없으면 None."""
    global _rr_cursor
    now = datetime.now(timezone.utc)

    keys = db.query(YouTubeApiKey).order_by(YouTubeApiKey.id).all()
    if not keys:
        return None

    # Lazy daily reset
    changed = False
    for k in keys:
        if _maybe_reset(k, now):
            changed = True
    if changed:
        db.commit()

    candidates = [k for k in keys if k.status == "active" and k.quota_used_today < k.quota_limit]
    if not candidates:
        return None

    with _rr_lock:
        _rr_cursor = (_rr_cursor + 1) % len(candidates)
        return candidates[_rr_cursor % len(candidates)]


def mark_used(db: Session, key_id: int, cost: int) -> None:
    k = db.query(YouTubeApiKey).filter(YouTubeApiKey.id == key_id).first()
    if not k:
        return
    k.quota_used_today = (k.quota_used_today or 0) + cost
    k.last_used_at = datetime.now(timezone.utc)
    if k.quota_used_today >= k.quota_limit and k.status == "active":
        k.status = "exhausted"
        k.exhausted_at = k.last_used_at
    db.commit()


def mark_exhausted(db: Session, key_id: int) -> None:
    k = db.query(YouTubeApiKey).filter(YouTubeApiKey.id == key_id).first()
    if not k:
        return
    k.status = "exhausted"
    k.exhausted_at = datetime.now(timezone.utc)
    k.quota_used_today = max(k.quota_used_today, k.quota_limit)
    db.commit()
    log.warning(f"YouTube key #{key_id} marked exhausted")


def list_for_admin(db: Session) -> list[dict]:
    """어드민 UI 용 직렬화. key 는 마스킹."""
    now = datetime.now(timezone.utc)
    keys = db.query(YouTubeApiKey).order_by(YouTubeApiKey.id).all()
    changed = False
    for k in keys:
        if _maybe_reset(k, now):
            changed = True
    if changed:
        db.commit()

    out = []
    for k in keys:
        raw = k.key or ""
        masked = (raw[:7] + "..." + raw[-4:]) if len(raw) > 12 else "***"
        used = k.quota_used_today or 0
        limit = k.quota_limit or 10000
        out.append({
            "id": k.id,
            "key_masked": masked,
            "label": k.label,
            "status": k.status,
            "quota_used": used,
            "quota_limit": limit,
            "quota_pct": round(100.0 * used / limit, 1) if limit else 0.0,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "exhausted_at": k.exhausted_at.isoformat() if k.exhausted_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        })
    return out
