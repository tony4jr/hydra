"""Like boost engine — wave-based like deployment.

Spec Part 8:
- 3 presets: conservative, normal, aggressive
- Surrounding likes for disguise (like 0~2 count comments)
- Ghost check during visit
- Each account: visit → short watch → surrounding likes → our like → more surrounding
"""

import random
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.core.enums import LikeBoostPreset, StepStatus
from hydra.db.models import Campaign, CampaignStep, LikeBoostQueue, Account
from hydra.accounts.manager import get_available_accounts

log = get_logger("like_boost")

# Wave presets: list of (delay_minutes, count)
PRESETS = {
    LikeBoostPreset.CONSERVATIVE: [
        (30, 3), (180, 5), (720, 10), (1440, 12),
    ],
    LikeBoostPreset.NORMAL: [
        (30, 5), (120, 10), (360, 20), (720, 30), (1440, 35),
    ],
    LikeBoostPreset.AGGRESSIVE: [
        (15, 10), (60, 20), (180, 30), (360, 40),
    ],
}


def schedule_like_boost(
    db: Session,
    campaign: Campaign,
    target_step: CampaignStep,
    preset: LikeBoostPreset | None = None,
) -> int:
    """Schedule like boost waves for a campaign step.

    Returns total likes scheduled.
    """
    if not preset:
        preset = LikeBoostPreset(campaign.like_boost_preset or "normal")

    waves = PRESETS.get(preset, PRESETS[LikeBoostPreset.NORMAL])

    # Get available accounts (exclude campaign participants)
    campaign_account_ids = [
        s.account_id for s in
        db.query(CampaignStep.account_id)
        .filter(CampaignStep.campaign_id == campaign.id)
        .all()
    ]

    available = get_available_accounts(db, exclude_ids=campaign_account_ids)
    if not available:
        log.warning(f"No accounts available for like boost on campaign #{campaign.id}")
        return 0

    base_time = target_step.completed_at or datetime.now(timezone.utc)
    total = 0

    for wave_num, (delay_min, count) in enumerate(waves, 1):
        scheduled_at = base_time + timedelta(minutes=delay_min)

        # Pick random accounts for this wave
        wave_accounts = random.sample(available, min(count, len(available)))

        for account in wave_accounts:
            item = LikeBoostQueue(
                campaign_id=campaign.id,
                target_step_id=target_step.id,
                wave_number=wave_num,
                account_id=account.id,
                scheduled_at=scheduled_at,
                surrounding_likes_count=random.randint(2, 5),
            )
            db.add(item)
            total += 1

    db.commit()
    log.info(
        f"Scheduled {total} likes for campaign #{campaign.id} "
        f"step #{target_step.step_number} ({preset})"
    )
    return total


def get_pending_boosts(db: Session, limit: int = 10) -> list[LikeBoostQueue]:
    """Get like boost items ready to execute."""
    now = datetime.now(timezone.utc)
    return (
        db.query(LikeBoostQueue)
        .filter(
            LikeBoostQueue.status == "pending",
            LikeBoostQueue.scheduled_at <= now,
        )
        .order_by(LikeBoostQueue.scheduled_at)
        .limit(limit)
        .all()
    )


def complete_boost(db: Session, boost: LikeBoostQueue, surrounding_count: int = 0):
    """Mark a like boost as completed."""
    boost.status = "done"
    boost.completed_at = datetime.now(timezone.utc)
    boost.surrounding_likes_count = surrounding_count
    db.commit()


def schedule_custom_boost(
    db: Session,
    video_id: str,
    comment_id: str,
    accounts: list[Account],
) -> int:
    """Schedule like boosts for a custom comment (all-hands mobilization).

    Creates a virtual campaign with a single step, then schedules boosts.
    """
    from hydra.db.models import Campaign, CampaignStep, Video

    # Create tracking campaign
    campaign = Campaign(
        video_id=video_id,
        brand_id=0,  # virtual — no brand
        scenario="custom_like",
        status="in_progress",
        like_boost_preset="aggressive",
    )
    db.add(campaign)
    db.flush()

    # Virtual step (represents the target comment)
    step = CampaignStep(
        campaign_id=campaign.id,
        step_number=1,
        role="external",
        account_id=accounts[0].id if accounts else 0,
        type="comment",
        content="[custom like boost target]",
        youtube_comment_id=comment_id,
        status="done",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(step)
    db.flush()

    # Spread accounts across 3 waves (30min, 2h, 6h)
    base_time = datetime.now(timezone.utc)
    wave_configs = [(30, 0.4), (120, 0.35), (360, 0.25)]  # (delay_min, fraction)
    total = 0

    remaining = list(accounts)
    random.shuffle(remaining)

    for wave_num, (delay_min, fraction) in enumerate(wave_configs, 1):
        count = max(1, int(len(accounts) * fraction))
        wave_accounts = remaining[:count]
        remaining = remaining[count:]

        for account in wave_accounts:
            item = LikeBoostQueue(
                campaign_id=campaign.id,
                target_step_id=step.id,
                wave_number=wave_num,
                account_id=account.id,
                scheduled_at=base_time + timedelta(minutes=delay_min),
                surrounding_likes_count=random.randint(2, 5),
            )
            db.add(item)
            total += 1

    db.commit()
    log.info(f"Custom like boost: {total} accounts for comment {comment_id}")
    return total
