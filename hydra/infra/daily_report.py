"""Daily report generator — sent via Telegram at 23:00.

Spec Part 12.1: daily report format.
"""

from datetime import datetime, timezone, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.db.models import Account, Campaign, ActionLog, ErrorLog, LikeBoostQueue
from hydra.db.session import SessionLocal
from hydra.infra import telegram

log = get_logger("report")


def generate_daily_report(db: Session, date: datetime | None = None) -> str:
    """Generate daily report text."""
    if not date:
        date = datetime.now(timezone.utc)

    day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    # Account stats
    account_status = {}
    for row in db.query(Account.status, func.count()).group_by(Account.status).all():
        account_status[row[0]] = row[1]

    total_accounts = sum(account_status.values())
    active = account_status.get("active", 0)
    warmup = account_status.get("warmup", 0)
    cooldown = account_status.get("cooldown", 0)
    retired = account_status.get("retired", 0)

    # Today's actions
    promo_comments = (
        db.query(func.count())
        .filter(
            ActionLog.action_type == "comment",
            ActionLog.is_promo == True,
            ActionLog.created_at.between(day_start, day_end),
        )
        .scalar() or 0
    )

    non_promo = (
        db.query(func.count())
        .filter(
            ActionLog.is_promo == False,
            ActionLog.created_at.between(day_start, day_end),
        )
        .scalar() or 0
    )

    like_boosts = (
        db.query(func.count())
        .filter(
            ActionLog.action_type == "like_comment",
            ActionLog.is_promo == True,
            ActionLog.created_at.between(day_start, day_end),
        )
        .scalar() or 0
    )

    # Ghost count today
    ghost_today = (
        db.query(func.count())
        .filter(
            Campaign.ghost_check_status == "ghost",
            Campaign.ghost_checked_at.between(day_start, day_end),
        )
        .scalar() or 0
    )

    # Campaign stats
    campaigns_completed = (
        db.query(func.count())
        .filter(
            Campaign.status == "completed",
            Campaign.completed_at.between(day_start, day_end),
        )
        .scalar() or 0
    )
    campaigns_active = (
        db.query(func.count())
        .filter(Campaign.status == "in_progress")
        .scalar() or 0
    )

    # Errors
    errors = {}
    for row in (
        db.query(ErrorLog.level, func.count())
        .filter(ErrorLog.created_at.between(day_start, day_end))
        .group_by(ErrorLog.level)
        .all()
    ):
        errors[row[0]] = row[1]

    date_str = date.strftime("%Y-%m-%d")

    report = f"""HYDRA 일일 리포트 ({date_str})

활동 계정: {active}/{total_accounts}
웜업 계정: {warmup}
쿨다운: {cooldown}
폐기: {retired}

홍보 댓글: {promo_comments}개
비홍보 행동: {non_promo}개
좋아요 부스팅: {like_boosts}개

Ghost 발생: {ghost_today}건
캠페인 완료: {campaigns_completed}건
캠페인 진행중: {campaigns_active}건

에러:
  Critical: {errors.get('critical', 0)}건
  Error: {errors.get('error', 0)}건
  Warning: {errors.get('warning', 0)}건"""

    return report


def send_daily_report():
    """Generate and send daily report via Telegram."""
    db = SessionLocal()
    try:
        report = generate_daily_report(db)
        telegram.daily_report(report)
        log.info("Daily report sent")
    except Exception as e:
        log.error(f"Daily report failed: {e}")
    finally:
        db.close()
