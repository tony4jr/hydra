"""Work queue scheduler — pulls and executes pending tasks.

Spec Part 9:
- Every minute: check pending tasks
- Priority ordering: urgent > high > normal > low
- Account availability check (not running, not cooldown)
- IP availability check (1 IP = 1 account)
- Retry logic (max 3)

Also runs periodic jobs:
- Warmup graduation check (hourly)
- Cooldown recovery check (hourly)
- Video collection (4h core, 24h normal)
- Daily report (23:00)
- Backup (every 4h)
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.core.enums import (
    StepStatus, CampaignStatus, AccountStatus, VideoPriority,
)
from hydra.db.models import (
    CampaignStep, Campaign, Account, Video, LikeBoostQueue,
)
from hydra.db.session import SessionLocal
from hydra.infra import telegram

log = get_logger("scheduler")

# Device ID for IP rotation (set via CLI or config)
_device_id: str | None = None

# Global pause flag
_paused: bool = False


def set_device(device_id: str):
    global _device_id
    _device_id = device_id


def pause():
    global _paused
    _paused = True
    log.info("Scheduler PAUSED")


def resume():
    global _paused
    _paused = False
    log.info("Scheduler RESUMED")


def is_paused() -> bool:
    return _paused


def get_pending_steps(db: Session, limit: int = 10) -> list[CampaignStep]:
    """Get steps ready to execute, ordered by priority.

    Tikitaka safety: only pick a step if all prior steps in the same
    campaign are already DONE. Prevents step 2 running before step 1.
    """
    from hydra.core.lock import is_locked

    now = datetime.now(timezone.utc)

    steps = (
        db.query(CampaignStep)
        .join(Campaign)
        .join(Video, Campaign.video_id == Video.id)
        .filter(
            CampaignStep.status == StepStatus.PENDING,
            CampaignStep.scheduled_at <= now,
            Campaign.status == CampaignStatus.IN_PROGRESS,
        )
        .order_by(Video.priority, CampaignStep.scheduled_at)
        .limit(limit * 3)  # Fetch more to filter
        .all()
    )

    available = []
    for step in steps:
        # DB-level lock check (cross-process safe)
        if is_locked(db, step.account_id):
            continue

        account = db.query(Account).get(step.account_id)
        if not account or account.status != AccountStatus.ACTIVE:
            continue

        # Tikitaka order guard: all prior steps must be done
        if step.step_number > 1:
            prior_incomplete = (
                db.query(CampaignStep)
                .filter(
                    CampaignStep.campaign_id == step.campaign_id,
                    CampaignStep.step_number < step.step_number,
                    CampaignStep.status.notin_([StepStatus.DONE, StepStatus.CANCELLED]),
                )
                .first()
            )
            if prior_incomplete:
                continue  # Wait for prior steps

        available.append(step)
        if len(available) >= limit:
            break

    return available


def mark_running(db: Session, step: CampaignStep):
    from hydra.core.lock import acquire_lock
    acquire_lock(db, step.account_id)
    step.status = StepStatus.RUNNING
    db.commit()


def mark_done(db: Session, step: CampaignStep):
    from hydra.core.lock import release_lock
    step.status = StepStatus.DONE
    step.completed_at = datetime.now(timezone.utc)
    release_lock(db, step.account_id)
    db.commit()

    from hydra.core.campaign import check_campaign_completion
    campaign = db.query(Campaign).get(step.campaign_id)
    if campaign:
        check_campaign_completion(db, campaign)


def mark_failed(db: Session, step: CampaignStep, error: str):
    from hydra.core.lock import release_lock
    step.retry_count += 1
    step.error_message = error
    release_lock(db, step.account_id)

    if step.retry_count < 3:
        step.status = StepStatus.PENDING
        log.warning(f"Step #{step.id} failed (attempt {step.retry_count}): {error}")
    else:
        step.status = StepStatus.FAILED
        log.error(f"Step #{step.id} permanently failed: {error}")
        telegram.warning(f"작업 실패 (3회): 캠페인 #{step.campaign_id} 스텝 #{step.step_number}")

    db.commit()


async def run_scheduler_tick():
    """One tick — execute pending campaign steps and like boosts."""
    if _paused:
        return

    from hydra.core.executor import execute_step, execute_like_boost
    from hydra.core.lock import acquire_lock, release_lock, is_locked

    db = SessionLocal()
    try:
        # 1. Campaign steps
        steps = get_pending_steps(db, limit=3)
        for step in steps:
            mark_running(db, step)
            try:
                await execute_step(db, step, device_id=_device_id)
            except Exception as e:
                log.error(f"Step #{step.id} execution error: {e}")
                mark_failed(db, step, str(e))

        # 2. Like boosts
        from hydra.like_boost.engine import get_pending_boosts
        boosts = get_pending_boosts(db, limit=3)
        for boost in boosts:
            if not is_locked(db, boost.account_id) and acquire_lock(db, boost.account_id):
                boost.status = "running"
                db.commit()
                try:
                    await execute_like_boost(db, boost, device_id=_device_id)
                except Exception as e:
                    log.error(f"Like boost #{boost.id} error: {e}")
                    boost.status = "failed"
                    db.commit()
                finally:
                    release_lock(db, boost.account_id)

    except Exception as e:
        log.error(f"Scheduler tick error: {e}")
    finally:
        db.close()


async def run_periodic_jobs():
    """Periodic maintenance tasks."""
    from hydra.accounts.manager import check_warmup_graduation, check_cooldown_recovery
    from hydra.core.settings_loader import load_and_apply

    last_collection_core = datetime.min
    last_collection_all = datetime.min
    last_maintenance = datetime.min
    last_warmup_run = datetime.min
    last_daily_report = datetime.min

    while True:
        now = datetime.now(timezone.utc)
        db = SessionLocal()

        try:
            # Reload settings from DB every cycle
            load_and_apply(db)

            # Hourly: warmup/cooldown checks + warmup sessions
            if (now - last_maintenance).total_seconds() >= 3600:
                check_warmup_graduation(db)
                check_cooldown_recovery(db)
                last_maintenance = now

            # 4h: core keyword collection
            if (now - last_collection_core).total_seconds() >= 14400:
                from hydra.collection.youtube_api import collect_all
                try:
                    collect_all(db, core_only=True)
                except Exception as e:
                    log.error(f"Core collection failed: {e}")
                last_collection_core = now

            # 24h: all keyword collection
            if (now - last_collection_all).total_seconds() >= 86400:
                from hydra.collection.youtube_api import collect_all
                try:
                    collect_all(db, core_only=False)
                except Exception as e:
                    log.error(f"Full collection failed: {e}")
                last_collection_all = now

            # 6h: run warmup sessions for warmup accounts
            if (now - last_warmup_run).total_seconds() >= 21600:
                from hydra.accounts.warmup_runner import run_all_warmups
                try:
                    await run_all_warmups(device_id=_device_id)
                except Exception as e:
                    log.error(f"Warmup run failed: {e}")
                last_warmup_run = now

            # Daily report at 23:00 UTC
            if now.hour == 23 and (now - last_daily_report).total_seconds() >= 43200:
                from hydra.infra.daily_report import send_daily_report
                send_daily_report()
                last_daily_report = now

        except Exception as e:
            log.error(f"Periodic job error: {e}")
        finally:
            db.close()

        await asyncio.sleep(300)  # Check every 5 min


async def run_scheduler(interval_sec: int = 60):
    """Main scheduler loop — runs tick + periodic jobs concurrently."""
    log.info(f"Scheduler started (interval={interval_sec}s)")

    # Crash recovery on startup
    db = SessionLocal()
    try:
        from hydra.core.recovery import recover_from_crash
        recover_from_crash(db)
    finally:
        db.close()

    telegram.info("HYDRA 스케줄러 시작됨")

    # Start periodic jobs in background
    asyncio.create_task(run_periodic_jobs())

    while True:
        await run_scheduler_tick()
        await asyncio.sleep(interval_sec)
