"""Campaign creation and execution orchestration.

Spec Part 6.4:
Campaign = 1 video × 1 brand × 1 scenario → N steps (timed).
"""

import json
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.core.enums import (
    CampaignStatus, StepStatus, Scenario, LikeBoostPreset,
    AccountRole, VideoPriority,
)
from hydra.core.scenarios import get_template, select_scenario
from hydra.db.models import Campaign, CampaignStep, Video, Brand, Account
from hydra.accounts.manager import get_available_accounts
from hydra.accounts.persona import get_persona
from hydra.content.generator import generate_comment
from hydra.infra import telegram

log = get_logger("campaign")


def create_campaign(
    db: Session,
    video: Video,
    brand: Brand,
    scenario: Scenario | None = None,
    like_preset: LikeBoostPreset = LikeBoostPreset.NORMAL,
) -> Campaign:
    """Create a new campaign with scheduled steps."""

    # Auto-select scenario if not specified
    if not scenario:
        has_active = (
            db.query(Campaign)
            .filter(Campaign.video_id == video.id, Campaign.status == CampaignStatus.IN_PROGRESS)
            .first() is not None
        )
        is_fresh = False
        if video.published_at:
            is_fresh = (datetime.now(timezone.utc) - video.published_at) < timedelta(hours=24)

        scenario = select_scenario(
            is_fresh=is_fresh,
            is_short=video.is_short or False,
            comment_count=video.comment_count,
            has_active_campaign=has_active,
        )

    template = get_template(scenario)

    # Create campaign record
    campaign = Campaign(
        video_id=video.id,
        brand_id=brand.id,
        scenario=scenario,
        status=CampaignStatus.PLANNING,
        like_boost_preset=like_preset,
    )
    db.add(campaign)
    db.flush()  # Get campaign.id

    # Assign accounts to roles
    needed_roles = set()
    role_accounts: dict[AccountRole, list[Account]] = {}

    for step_def in template.steps:
        needed_roles.add(step_def.role)

    used_ids: list[int] = []
    for role in needed_roles:
        accounts = get_available_accounts(db, role=role, exclude_ids=used_ids)
        if not accounts:
            accounts = get_available_accounts(db, exclude_ids=used_ids)
        if not accounts:
            log.warning(f"No available accounts for role {role}")
            campaign.status = CampaignStatus.FAILED
            db.commit()
            return campaign

        selected = random.choice(accounts)
        role_accounts[role] = [selected]
        used_ids.append(selected.id)

    # Create steps with scheduled times
    base_time = datetime.now(timezone.utc) + timedelta(minutes=random.randint(5, 15))
    cumulative_delay = 0

    for i, step_def in enumerate(template.steps):
        cumulative_delay += step_def.delay_min
        scheduled = base_time + timedelta(minutes=cumulative_delay)

        # Get account for this role
        account = role_accounts[step_def.role][0]

        step = CampaignStep(
            campaign_id=campaign.id,
            step_number=i + 1,
            role=step_def.role,
            account_id=account.id,
            type=step_def.type,
            parent_step_id=step_def.parent_step,
            scheduled_at=scheduled,
            status=StepStatus.PENDING,
        )
        db.add(step)

    campaign.status = CampaignStatus.IN_PROGRESS
    db.commit()

    log.info(
        f"Campaign #{campaign.id} created: video={video.id}, "
        f"scenario={scenario}, steps={len(template.steps)}"
    )
    return campaign


def generate_step_content(db: Session, step: CampaignStep) -> str:
    """Generate comment content for a campaign step."""
    campaign = db.query(Campaign).get(step.campaign_id)
    brand = db.query(Brand).get(campaign.brand_id)
    video = db.query(Video).get(campaign.video_id)
    account = db.query(Account).get(step.account_id)
    persona = get_persona(account)

    if not persona:
        raise RuntimeError(f"No persona for account {account.id}")

    # Build conversation context from prior steps
    context = ""
    if step.parent_step_id is not None:
        prior_steps = (
            db.query(CampaignStep)
            .filter(
                CampaignStep.campaign_id == campaign.id,
                CampaignStep.step_number < step.step_number,
                CampaignStep.content.isnot(None),
            )
            .order_by(CampaignStep.step_number)
            .all()
        )
        context = "\n".join(
            f"[{s.role}]: {s.content}" for s in prior_steps if s.content
        )

    # Find parent comment text for replies
    parent_comment = ""
    if step.parent_step_id is not None and step.type == "reply":
        parent = (
            db.query(CampaignStep)
            .filter(
                CampaignStep.campaign_id == campaign.id,
                CampaignStep.step_number == step.parent_step_id + 1,
            )
            .first()
        )
        if parent and parent.content:
            parent_comment = parent.content

    step.status = StepStatus.GENERATING
    db.commit()

    comment = generate_comment(
        persona=persona,
        role=AccountRole(step.role),
        brand=brand,
        video=video,
        context=context,
        is_reply=(step.type == "reply"),
        parent_comment=parent_comment,
    )

    step.content = comment
    step.status = StepStatus.READY
    db.commit()

    return comment


def check_campaign_completion(db: Session, campaign: Campaign):
    """Check if all steps are done and update campaign status."""
    steps = (
        db.query(CampaignStep)
        .filter(CampaignStep.campaign_id == campaign.id)
        .all()
    )

    all_done = all(s.status == StepStatus.DONE for s in steps)
    any_failed = any(s.status == StepStatus.FAILED for s in steps)

    if all_done:
        campaign.status = CampaignStatus.COMPLETED
        campaign.completed_at = datetime.now(timezone.utc)
        telegram.info(f"캠페인 #{campaign.id} 완료: 시나리오 {campaign.scenario}")
    elif any_failed:
        # Check if critical steps failed
        failed_steps = [s for s in steps if s.status == StepStatus.FAILED]
        if any(s.step_number == 1 for s in failed_steps):
            # Seed step failed — campaign is dead
            campaign.status = CampaignStatus.FAILED
            telegram.warning(f"캠페인 #{campaign.id} 실패: 시드 댓글 작성 실패")

    db.commit()
