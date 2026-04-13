"""Dashboard home — realtime stats overview."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone, timedelta

from hydra.db.session import get_db
from hydra.db.models import Account, Campaign, CampaignStep, ActionLog, ErrorLog

router = APIRouter()


@router.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Dashboard summary stats."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Account stats
    account_stats = {}
    for row in db.query(Account.status, func.count()).group_by(Account.status).all():
        account_stats[row[0]] = row[1]

    # Today's activity
    today_comments = (
        db.query(func.count())
        .filter(ActionLog.action_type == "comment", ActionLog.created_at >= today_start, ActionLog.is_promo == True)
        .scalar()
    )
    today_actions = (
        db.query(func.count())
        .filter(ActionLog.created_at >= today_start, ActionLog.is_promo == False)
        .scalar()
    )
    today_likes = (
        db.query(func.count())
        .filter(ActionLog.action_type == "like_comment", ActionLog.created_at >= today_start)
        .scalar()
    )

    # Campaign stats
    active_campaigns = db.query(func.count()).filter(Campaign.status == "in_progress").scalar()
    completed_today = (
        db.query(func.count())
        .filter(Campaign.status == "completed", Campaign.completed_at >= today_start)
        .scalar()
    )

    # Recent errors
    recent_errors = (
        db.query(func.count())
        .filter(ErrorLog.created_at >= today_start, ErrorLog.level.in_(["error", "critical"]))
        .scalar()
    )

    return {
        "accounts": account_stats,
        "today": {
            "promo_comments": today_comments,
            "non_promo_actions": today_actions,
            "like_boosts": today_likes,
        },
        "campaigns": {
            "active": active_campaigns,
            "completed_today": completed_today,
        },
        "errors_today": recent_errors,
    }
