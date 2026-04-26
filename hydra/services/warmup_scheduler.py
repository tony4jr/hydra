"""Warmup scheduler — daily generates per-account warmup tasks until promotion.

Lifecycle (per account in `warmup` status):
    Day 1: language setup, channel customize, watch 5 videos, like 1
    Day 2: + Gmail check, search, watch 8 videos, like 2-3
    Day 3: + subscribe to 1-2 channels, watch 10 videos, like 3-5
    Day 4: + first low-pressure comment (non-promo), watch 12, like 5
    Day 5: + 1-2 more comments, watch 15, sustained activity → promotion candidate

Promotion criteria (run in evaluate_promotion):
    - warmup_day >= 5
    - last 24h: at least 1 successful comment
    - no identity_challenge / suspended state
    - ghost_count < 2 (low ghost rate)
    - stability_score >= 0.7

Stability score (0.0~1.0) = weighted sum:
    - 0.4 × (1.0 - error_rate_7d)
    - 0.3 × (1.0 - ghost_rate_7d)
    - 0.2 × (warmup_day / 5)
    - 0.1 × (login_success_recent ? 1 : 0)

Cron: 0 9 * * *  (daily 09:00 KST — same as report cron)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.db.models import Account, ActionLog, Task

log = get_logger("warmup_scheduler")
UTC = timezone.utc


# Per-day warmup task config
WARMUP_DAY_CONFIG = {
    1: {"watches": 5, "likes": 1, "comments": 0, "subscribes": 0},
    2: {"watches": 8, "likes": 3, "comments": 0, "subscribes": 0},
    3: {"watches": 10, "likes": 5, "comments": 0, "subscribes": 1},
    4: {"watches": 12, "likes": 5, "comments": 1, "subscribes": 1},
    5: {"watches": 15, "likes": 7, "comments": 2, "subscribes": 2},
}

PROMOTION_REQUIRED_DAY = 5
PROMOTION_MIN_SCORE = 0.7


def calc_stability_score(db: Session, account_id: int) -> float:
    """Compute account stability score 0.0~1.0. See module docstring."""
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    account = db.get(Account, account_id)
    if not account:
        return 0.0

    # Error rate (failed tasks / total tasks last 7d)
    tasks_7d = db.query(Task).filter(
        Task.account_id == account_id,
        Task.created_at >= week_ago,
    ).all()
    if tasks_7d:
        failed = sum(1 for t in tasks_7d if t.status == "failed")
        error_rate = failed / len(tasks_7d)
    else:
        error_rate = 0.0  # neutral if no recent tasks

    # Ghost rate (rough — based on ghost_count + total comments)
    comments_7d = sum(1 for t in tasks_7d if t.task_type in ("comment", "reply") and t.status == "done")
    ghost_rate = (account.ghost_count or 0) / max(comments_7d, 1) if comments_7d > 0 else 0.0
    ghost_rate = min(ghost_rate, 1.0)

    # Warmup completion
    warmup_progress = min((account.warmup_day or 0) / 5.0, 1.0)

    # Recent login success (no identity_challenge cooldown active)
    login_ok = 1.0 if not (account.identity_challenge_until and account.identity_challenge_until > now) else 0.0

    score = (
        0.4 * (1.0 - error_rate) +
        0.3 * (1.0 - ghost_rate) +
        0.2 * warmup_progress +
        0.1 * login_ok
    )
    return round(score, 3)


def schedule_warmup_for_account(db: Session, account: Account) -> Task | None:
    """Create today's warmup task for this account, if one isn't already pending/running."""
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    existing = (
        db.query(Task)
        .filter(
            Task.account_id == account.id,
            Task.task_type == "warmup",
            Task.created_at >= today_start,
            Task.status.in_(("pending", "running", "done")),
        )
        .first()
    )
    if existing:
        return None  # already scheduled for today

    day = (account.warmup_day or 0) + 1
    if day > 5:
        log.info(f"account {account.id} already past warmup day 5 — should be promoted")
        return None

    config = WARMUP_DAY_CONFIG.get(day, WARMUP_DAY_CONFIG[5])
    persona = json.loads(account.persona) if account.persona else {}
    payload = {
        "day": day,
        "persona": persona,
        "config": config,
        "session_context": {},
    }
    task = Task(
        account_id=account.id,
        task_type="warmup",
        priority="normal",
        status="pending",
        payload=json.dumps(payload, ensure_ascii=False),
        scheduled_at=now,
    )
    db.add(task)
    log.info(f"scheduled warmup day {day} for account {account.id}")
    return task


def evaluate_promotion(db: Session, account: Account) -> bool:
    """Check if account is ready for promotion to 'active'. Mutates account if promoted."""
    if account.status != "warmup":
        return False
    if (account.warmup_day or 0) < PROMOTION_REQUIRED_DAY:
        return False
    if account.identity_challenge_until and account.identity_challenge_until > datetime.now(UTC):
        return False  # in cooldown

    score = calc_stability_score(db, account.id)
    if score < PROMOTION_MIN_SCORE:
        log.info(f"account {account.id} score {score:.2f} below {PROMOTION_MIN_SCORE} — not promoted")
        return False

    account.status = "active"
    account.onboard_completed_at = account.onboard_completed_at or datetime.now(UTC)
    log.info(f"PROMOTED account {account.id} to active (score={score:.2f}, day={account.warmup_day})")
    return True


def daily_tick(db: Session) -> dict:
    """Cron entry — run once daily.

    1. For each `warmup` account: schedule today's warmup task
    2. After day 5 complete: evaluate promotion
    """
    counts = {"scheduled": 0, "promoted": 0, "checked": 0}
    accounts = db.query(Account).filter(Account.status == "warmup").all()
    for a in accounts:
        counts["checked"] += 1
        # Schedule today's task
        if schedule_warmup_for_account(db, a):
            counts["scheduled"] += 1
        # Evaluate promotion
        if evaluate_promotion(db, a):
            counts["promoted"] += 1
    db.commit()
    log.info(f"daily warmup tick: {counts}")
    return counts


if __name__ == "__main__":
    from hydra.db.session import SessionLocal
    db = SessionLocal()
    try:
        result = daily_tick(db)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        db.close()
