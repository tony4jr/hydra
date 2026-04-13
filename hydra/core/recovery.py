"""Error recovery and system restart handler.

Spec Part 11:
- Crash recovery: running → pending rollback
- Level 1~5 error handling
- Auto-restart logic
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.core.enums import StepStatus, CampaignStatus
from hydra.db.models import CampaignStep, Campaign, LikeBoostQueue
from hydra.infra import telegram

log = get_logger("recovery")


def recover_from_crash(db: Session) -> dict:
    """Recover interrupted tasks after system crash/restart.

    Spec 11.3:
    1. Scan incomplete tasks
    2. running → pending rollback
    3. Reconstruct work queue
    4. Report via telegram
    """
    stats = {"steps_recovered": 0, "boosts_recovered": 0, "campaigns_checked": 0,
             "locks_released": 0, "generating_rolled_back": 0}

    # 0. Release all stale locks
    from hydra.core.lock import release_all
    release_all(db)
    stats["locks_released"] = 1

    # 1. Rollback running steps → pending
    running_steps = (
        db.query(CampaignStep)
        .filter(CampaignStep.status == StepStatus.RUNNING)
        .all()
    )
    for step in running_steps:
        step.status = StepStatus.PENDING
        step.error_message = "recovered after crash"
        stats["steps_recovered"] += 1

    # 1b. Rollback generating steps → pending (content may be incomplete)
    generating_steps = (
        db.query(CampaignStep)
        .filter(CampaignStep.status == StepStatus.GENERATING)
        .all()
    )
    for step in generating_steps:
        step.status = StepStatus.PENDING
        step.content = None  # Clear partial content
        step.error_message = "recovered after crash (was generating)"
        stats["generating_rolled_back"] += 1

    # 2. Rollback running like boosts → pending
    running_boosts = (
        db.query(LikeBoostQueue)
        .filter(LikeBoostQueue.status == "running")
        .all()
    )
    for boost in running_boosts:
        boost.status = "pending"
        stats["boosts_recovered"] += 1

    # 2b. Stop any lingering AdsPower browsers
    try:
        from hydra.browser.adspower import adspower
        from hydra.db.models import Account
        active_profiles = (
            db.query(Account.adspower_profile_id)
            .filter(Account.adspower_profile_id.isnot(None))
            .all()
        )
        for (profile_id,) in active_profiles:
            try:
                if adspower.check_browser_active(profile_id):
                    adspower.stop_browser(profile_id)
            except Exception:
                pass
    except Exception as e:
        log.warning(f"AdsPower cleanup failed: {e}")

    # 3. Check campaigns that were in_progress
    active_campaigns = (
        db.query(Campaign)
        .filter(Campaign.status == CampaignStatus.IN_PROGRESS)
        .all()
    )
    for campaign in active_campaigns:
        # Check if all steps are done/failed
        steps = (
            db.query(CampaignStep)
            .filter(CampaignStep.campaign_id == campaign.id)
            .all()
        )
        all_done = all(s.status in (StepStatus.DONE, StepStatus.FAILED, StepStatus.CANCELLED) for s in steps)
        if all_done and steps:
            from hydra.core.campaign import check_campaign_completion
            check_campaign_completion(db, campaign)

        stats["campaigns_checked"] += 1

    db.commit()

    # 4. Report
    total = stats["steps_recovered"] + stats["boosts_recovered"] + stats["generating_rolled_back"]
    if total > 0:
        msg = (
            f"HYDRA 재시작 복구 완료\n"
            f"스텝 복구: {stats['steps_recovered']}건\n"
            f"생성중 롤백: {stats['generating_rolled_back']}건\n"
            f"좋아요 복구: {stats['boosts_recovered']}건\n"
            f"캠페인 확인: {stats['campaigns_checked']}건\n"
            f"락 해제: 완료"
        )
        telegram.info(msg)
        log.info(msg)
    else:
        log.info("No tasks to recover")

    return stats


def handle_error(
    db: Session,
    level: int,
    source: str,
    message: str,
    account_id: int | None = None,
    video_id: str | None = None,
    campaign_id: int | None = None,
    stack_trace: str | None = None,
):
    """Centralized error handler with level-based response.

    Spec 11.1:
    Level 1: auto recover, no alert
    Level 2: auto recover + log
    Level 3: auto recover + telegram warning
    Level 4: manual needed + telegram urgent
    Level 5: system halt + telegram urgent
    """
    from hydra.db.models import ErrorLog
    from hydra.core.enums import ErrorLevel

    # Map level to enum
    level_map = {1: "info", 2: "warning", 3: "warning", 4: "error", 5: "critical"}
    level_str = level_map.get(level, "error")

    # Log to DB
    error = ErrorLog(
        level=level_str,
        source=source,
        account_id=account_id,
        video_id=video_id,
        campaign_id=campaign_id,
        message=message,
        stack_trace=stack_trace,
    )
    db.add(error)
    db.commit()

    # Level-based response
    if level >= 4:
        telegram.urgent(f"[{source}] {message}")
    elif level == 3:
        telegram.warning(f"[{source}] {message}")

    if level >= 3:
        log.error(f"L{level} [{source}] {message}")
    elif level == 2:
        log.warning(f"L{level} [{source}] {message}")
    else:
        log.info(f"L{level} [{source}] {message}")
