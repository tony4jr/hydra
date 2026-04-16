"""Dashboard home — realtime stats overview."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from datetime import datetime, timezone, timedelta

from hydra.db.session import get_db
from hydra.db.models import Account, Campaign, CampaignStep, ActionLog, ErrorLog, Worker, Task

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

    # Worker stats
    workers = db.query(Worker).all()
    worker_online = sum(1 for w in workers if w.status == "online")

    # Task stats
    task_stats = {
        "today_completed": db.query(Task).filter(Task.completed_at >= today_start, Task.status == "completed").count(),
        "today_failed": db.query(Task).filter(Task.completed_at >= today_start, Task.status == "failed").count(),
        "pending": db.query(Task).filter(Task.status == "pending").count(),
        "running": db.query(Task).filter(Task.status.in_(["assigned", "running"])).count(),
    }

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
        "workers": {"online": worker_online, "total": len(workers)},
        "tasks": task_stats,
    }


# --- #2: Calendar View ---

@router.get("/api/calendar")
def calendar_view(
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
):
    """Calendar data — daily activity/campaign counts for FullCalendar integration."""
    now = datetime.now(timezone.utc)
    y = year or now.year
    m = month or now.month

    # Date range for the month
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    if m == 12:
        end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(y, m + 1, 1, tzinfo=timezone.utc)

    # Daily action counts
    daily_actions = (
        db.query(
            func.date(ActionLog.created_at).label("day"),
            func.count().label("total"),
            func.sum(case((ActionLog.is_promo == True, 1), else_=0)).label("promo"),
            func.sum(case((ActionLog.is_promo == False, 1), else_=0)).label("non_promo"),
        )
        .filter(ActionLog.created_at >= start, ActionLog.created_at < end)
        .group_by(func.date(ActionLog.created_at))
        .all()
    )

    # Daily campaign events
    campaigns_created = (
        db.query(
            func.date(Campaign.created_at).label("day"),
            func.count().label("count"),
        )
        .filter(Campaign.created_at >= start, Campaign.created_at < end)
        .group_by(func.date(Campaign.created_at))
        .all()
    )
    campaigns_completed = (
        db.query(
            func.date(Campaign.completed_at).label("day"),
            func.count().label("count"),
        )
        .filter(Campaign.completed_at >= start, Campaign.completed_at < end)
        .group_by(func.date(Campaign.completed_at))
        .all()
    )

    # Daily errors
    daily_errors = (
        db.query(
            func.date(ErrorLog.created_at).label("day"),
            func.count().label("count"),
        )
        .filter(
            ErrorLog.created_at >= start, ErrorLog.created_at < end,
            ErrorLog.level.in_(["error", "critical"]),
        )
        .group_by(func.date(ErrorLog.created_at))
        .all()
    )

    # Build FullCalendar-compatible events
    events = []
    for row in daily_actions:
        events.append({
            "date": str(row.day),
            "title": f"댓글 {int(row.promo or 0)} / 활동 {int(row.non_promo or 0)}",
            "type": "actions",
            "promo": int(row.promo or 0),
            "non_promo": int(row.non_promo or 0),
            "total": row.total,
        })
    for row in campaigns_created:
        events.append({
            "date": str(row.day),
            "title": f"캠페인 생성 {row.count}",
            "type": "campaign_created",
            "count": row.count,
        })
    for row in campaigns_completed:
        events.append({
            "date": str(row.day),
            "title": f"캠페인 완료 {row.count}",
            "type": "campaign_completed",
            "count": row.count,
        })
    for row in daily_errors:
        events.append({
            "date": str(row.day),
            "title": f"에러 {row.count}",
            "type": "errors",
            "count": row.count,
        })

    return {"year": y, "month": m, "events": events}


@router.get("/api/health-dashboard")
def health_dashboard(db: Session = Depends(get_db)):
    """Account health dashboard — aggregated view of all accounts."""
    now = datetime.now(timezone.utc)
    thirty_days = now - timedelta(days=30)
    seven_days = now - timedelta(days=7)

    accounts = db.query(Account).filter(
        Account.status.in_(["active", "warmup", "cooldown", "captcha_stuck"])
    ).all()

    # Health distribution
    health_tiers = {"healthy": 0, "warning": 0, "critical": 0, "inactive": 0}
    status_counts = {}

    for a in accounts:
        status_counts[a.status] = status_counts.get(a.status, 0) + 1

        ghost = a.ghost_count or 0
        days_since_active = (now - a.last_active_at).days if a.last_active_at else 999

        if ghost >= 2 or a.status in ("captcha_stuck",):
            health_tiers["critical"] += 1
        elif ghost == 1 or days_since_active > 7:
            health_tiers["warning"] += 1
        elif days_since_active > 30:
            health_tiers["inactive"] += 1
        else:
            health_tiers["healthy"] += 1

    # Aggregate success rate
    step_stats = (
        db.query(
            func.count().label("total"),
            func.sum(case((CampaignStep.status == "done", 1), else_=0)).label("done"),
            func.sum(case((CampaignStep.status == "failed", 1), else_=0)).label("failed"),
        )
        .filter(CampaignStep.scheduled_at >= thirty_days)
        .first()
    )
    total_steps = step_stats.total or 0
    done = int(step_stats.done or 0)
    failed = int(step_stats.failed or 0)

    # Activity trend (last 7 days, daily counts)
    daily_activity = (
        db.query(
            func.date(ActionLog.created_at).label("day"),
            func.count().label("count"),
        )
        .filter(ActionLog.created_at >= seven_days)
        .group_by(func.date(ActionLog.created_at))
        .order_by(func.date(ActionLog.created_at))
        .all()
    )

    # Top ghosted accounts
    ghost_accounts = (
        db.query(Account)
        .filter(Account.ghost_count > 0)
        .order_by(Account.ghost_count.desc())
        .limit(10)
        .all()
    )

    return {
        "total_accounts": len(accounts),
        "health_tiers": health_tiers,
        "status_distribution": status_counts,
        "success_rate_30d": round(done / total_steps * 100, 1) if total_steps > 0 else 0.0,
        "total_steps_30d": total_steps,
        "done_30d": done,
        "failed_30d": failed,
        "daily_activity_7d": [
            {"date": str(row.day), "actions": row.count}
            for row in daily_activity
        ],
        "ghost_accounts": [
            {"id": a.id, "gmail": a.gmail, "ghost_count": a.ghost_count, "status": a.status}
            for a in ghost_accounts
        ],
    }
