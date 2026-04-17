"""계정 활동 한도 체크 — 일일/주간 상한 초과 방지."""
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session
from hydra.db.models import Account, ActionLog


def check_daily_limit(db: Session, account_id: int) -> dict:
    """일일 한도 체크. 초과 시 해당 타입 차단."""
    account = db.get(Account, account_id)
    if not account:
        return {"allowed": False, "reason": "account_not_found"}

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # 오늘 댓글 수
    today_comments = db.query(ActionLog).filter(
        ActionLog.account_id == account_id,
        ActionLog.action_type.in_(["comment", "reply"]),
        ActionLog.created_at >= today_start,
    ).count()

    # 오늘 좋아요 수
    today_likes = db.query(ActionLog).filter(
        ActionLog.account_id == account_id,
        ActionLog.action_type.in_(["like_video", "like_comment"]),
        ActionLog.created_at >= today_start,
    ).count()

    result = {
        "allowed": True,
        "comment_allowed": today_comments < account.daily_comment_limit,
        "like_allowed": today_likes < account.daily_like_limit,
        "today_comments": today_comments,
        "today_likes": today_likes,
        "daily_comment_limit": account.daily_comment_limit,
        "daily_like_limit": account.daily_like_limit,
    }

    if not result["comment_allowed"] and not result["like_allowed"]:
        result["allowed"] = False
        result["reason"] = "daily_limit_reached"

    return result


def check_weekly_limit(db: Session, account_id: int) -> dict:
    """주간 한도 체크."""
    account = db.get(Account, account_id)
    if not account:
        return {"allowed": False, "reason": "account_not_found"}

    # 이번 주 월요일
    now = datetime.now(UTC)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    week_comments = db.query(ActionLog).filter(
        ActionLog.account_id == account_id,
        ActionLog.action_type.in_(["comment", "reply"]),
        ActionLog.created_at >= week_start,
    ).count()

    week_likes = db.query(ActionLog).filter(
        ActionLog.account_id == account_id,
        ActionLog.action_type.in_(["like_video", "like_comment"]),
        ActionLog.created_at >= week_start,
    ).count()

    result = {
        "allowed": True,
        "comment_allowed": week_comments < account.weekly_comment_limit,
        "like_allowed": week_likes < account.weekly_like_limit,
        "week_comments": week_comments,
        "week_likes": week_likes,
    }

    if not result["comment_allowed"] and not result["like_allowed"]:
        result["allowed"] = False
        result["reason"] = "weekly_limit_reached"

    return result


def can_execute_task(db: Session, account_id: int, task_type: str) -> tuple[bool, str]:
    """태스크 실행 가능 여부. (allowed, reason) 반환."""
    daily = check_daily_limit(db, account_id)
    if not daily["allowed"]:
        return False, daily["reason"]

    weekly = check_weekly_limit(db, account_id)
    if not weekly["allowed"]:
        return False, weekly["reason"]

    # 태스크 타입별 체크
    if task_type in ("comment", "reply") and not daily["comment_allowed"]:
        return False, "daily_comment_limit"
    if task_type in ("like", "like_boost") and not daily["like_allowed"]:
        return False, "daily_like_limit"

    return True, "ok"
