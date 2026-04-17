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
) -> bool:
    """같은 영상 + 같은 프리셋 = 7일 차단. True=허용."""
    cutoff = datetime.now(UTC) - timedelta(days=period_days)
    existing = db.query(Campaign).filter(
        Campaign.video_id == video_id,
        Campaign.scenario == preset_code,
        Campaign.created_at >= cutoff,
        Campaign.status != "cancelled",
    ).first()
    return existing is None


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
