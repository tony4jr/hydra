"""계정 활동 한도 체크 — 일일/주간 상한 초과 방지."""
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session
from hydra.db.models import Account, ActionLog


def check_daily_limit(db: Session, account_id: int) -> dict:
    """일일 한도 체크. 계정 상태별 비율 적용."""
    account = db.get(Account, account_id)
    if not account:
        return {"allowed": False, "reason": "account_not_found"}

    # 상태별 비율 적용된 실제 한도
    comment_limit = get_effective_limit(account, "daily_comment_limit")
    like_limit = get_effective_limit(account, "daily_like_limit")

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    today_comments = db.query(ActionLog).filter(
        ActionLog.account_id == account_id,
        ActionLog.action_type.in_(["comment", "reply"]),
        ActionLog.created_at >= today_start,
    ).count()

    today_likes = db.query(ActionLog).filter(
        ActionLog.account_id == account_id,
        ActionLog.action_type.in_(["like_video", "like_comment"]),
        ActionLog.created_at >= today_start,
    ).count()

    result = {
        "allowed": True,
        "comment_allowed": today_comments < comment_limit,
        "like_allowed": today_likes < like_limit,
        "today_comments": today_comments,
        "today_likes": today_likes,
        "daily_comment_limit": comment_limit,
        "daily_like_limit": like_limit,
    }

    if not result["comment_allowed"] and not result["like_allowed"]:
        result["allowed"] = False
        result["reason"] = "daily_limit_reached"

    return result


def check_weekly_limit(db: Session, account_id: int) -> dict:
    """주간 한도 체크. 계정 상태별 비율 적용."""
    account = db.get(Account, account_id)
    if not account:
        return {"allowed": False, "reason": "account_not_found"}

    comment_limit = get_effective_limit(account, "weekly_comment_limit")
    like_limit = get_effective_limit(account, "weekly_like_limit")

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
        "comment_allowed": week_comments < comment_limit,
        "like_allowed": week_likes < like_limit,
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


# === 계정 상태별 한도 비율 ===

STATUS_RATIOS = {
    "warmup": 0.3,      # 워밍업: 기본값의 30%
    "active": 1.0,      # 활성: 100%
    "cooldown": 0.5,    # 쿨다운 복귀: 50%
    "registered": 0.0,  # 등록만: 작업 안 함
}


def get_effective_limit(account: Account, limit_field: str) -> int:
    """계정 상태에 따른 실제 한도 계산."""
    base = getattr(account, limit_field, 15)
    ratio = STATUS_RATIOS.get(account.status, 1.0)
    return max(1, int(base * ratio))


def get_remaining_comments(db: Session, account_id: int) -> int:
    """이 계정이 오늘 더 달 수 있는 댓글 수."""
    account = db.get(Account, account_id)
    if not account:
        return 0

    effective_limit = get_effective_limit(account, "daily_comment_limit")
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    today_comments = db.query(ActionLog).filter(
        ActionLog.account_id == account_id,
        ActionLog.action_type.in_(["comment", "reply"]),
        ActionLog.created_at >= today_start,
    ).count()

    return max(0, effective_limit - today_comments)


# === 프리셋 원자적 실행 — 사전 한도 체크 ===

def check_preset_feasibility(
    db: Session,
    preset_steps: list[dict],
    available_accounts: list[Account],
) -> dict | None:
    """프리셋 1세트를 완전히 실행할 수 있는 계정 배정을 찾는다.

    Returns: {"role": account_id} 매핑 or None (불가능)
    """
    # 역할별 필요 댓글 수 계산
    role_counts: dict[str, int] = {}
    for step in preset_steps:
        role = step.get("role", "seed")
        step_type = step.get("type", "comment")
        if step_type in ("comment", "reply"):
            role_counts[role] = role_counts.get(role, 0) + 1

    # 역할별 계정 배정 시도
    role_assignments: dict[str, int] = {}
    used_account_ids: set[int] = set()

    for role, needed in role_counts.items():
        assigned = False
        for account in available_accounts:
            if account.id in used_account_ids:
                # 같은 역할은 같은 계정, 다른 역할은 다른 계정
                continue
            remaining = get_remaining_comments(db, account.id)
            if remaining >= needed:
                role_assignments[role] = account.id
                used_account_ids.add(account.id)
                assigned = True
                break

        if not assigned:
            return None  # 이 역할에 배정할 계정이 없음

    return role_assignments
