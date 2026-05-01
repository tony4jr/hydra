"""영상 보호 규칙 — 영상당 캠페인 수 제한, 중복 방지."""
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session
from hydra.db.models import Campaign, ActionLog
from hydra.core.config import settings


def check_video_campaign_limit(
    db: Session,
    video_id: str,
    max_campaigns: int = 2,
    period_days: int = 7,
) -> tuple[bool, int]:
    """영상당 캠페인 수 제한. (allowed, current_count) 반환."""
    cutoff = datetime.now(UTC) - timedelta(days=period_days)
    count = db.query(Campaign).filter(
        Campaign.video_id == video_id,
        Campaign.created_at >= cutoff,
        Campaign.status != "cancelled",
    ).count()
    return count < max_campaigns, count


def check_video_preset_limit(
    db: Session,
    video_id: str,
    preset_code: str,
    period_days: int = 7,
    max_count: int = 1,
) -> bool:
    """같은 영상 + 같은 프리셋 캠페인 수 제한. True=허용.

    max_count 안에 캠페인이 몇 개까지 가능한지. 기본 1 (한 번이라도 있으면 차단).
    """
    cutoff = datetime.now(UTC) - timedelta(days=period_days)
    count = db.query(Campaign).filter(
        Campaign.video_id == video_id,
        Campaign.scenario == preset_code,
        Campaign.created_at >= cutoff,
        Campaign.status != "cancelled",
    ).count()
    return count < max_count


def check_video_preset_limit_for_brand(
    db: Session,
    video_id: str,
    preset_code: str,
    brand_id: int,
    period_days: int = 7,
) -> bool:
    """Niche.preset_per_video_limit (PR-3b) → Brand.preset_video_limit fallback. brand 마다 다른 한도 가능."""
    from hydra.db.models import Brand
    from hydra.services._niche_helper import get_niche_for_target
    niche = get_niche_for_target(db, brand_id) if brand_id else None
    if niche is not None and niche.preset_per_video_limit is not None:
        max_count = niche.preset_per_video_limit
    else:
        brand = db.get(Brand, brand_id) if brand_id else None
        max_count = (brand.preset_video_limit if brand else None) or 1
    return check_video_preset_limit(db, video_id, preset_code, period_days, max_count)


def check_account_video_duplicate(
    db: Session,
    account_id: int,
    video_id: str,
) -> bool:
    """같은 계정이 같은 영상에 이미 댓글 달았는지 확인. True=중복 없음."""
    existing = db.query(ActionLog).filter(
        ActionLog.account_id == account_id,
        ActionLog.video_id == video_id,
        ActionLog.action_type.in_(["comment", "reply"]),
    ).first()
    return existing is None


def check_account_video_like_duplicate(
    db: Session,
    account_id: int,
    video_id: str,
) -> bool:
    """같은 계정이 같은 영상에 이미 좋아요 눌렀는지 확인. True=중복 없음."""
    existing = db.query(ActionLog).filter(
        ActionLog.account_id == account_id,
        ActionLog.video_id == video_id,
        ActionLog.action_type.in_(["like_video", "like_comment"]),
    ).first()
    return existing is None
