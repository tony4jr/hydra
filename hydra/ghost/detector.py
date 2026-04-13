"""Ghost comment detection.

Spec 8.4 + 2.1.6:
- Like boost accounts check if our comment is visible (DOM check)
- 2 accounts must confirm ghost before marking
- Ghost 1 = cooldown (7 days), Ghost 2 = retired
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.core.enums import GhostCheckStatus
from hydra.db.models import Campaign, CampaignStep, Account
from hydra.accounts.manager import handle_ghost
from hydra.infra import telegram

log = get_logger("ghost")


def report_ghost_check(
    db: Session,
    campaign: Campaign,
    result: str,  # "visible" | "suspicious"
    checked_by_account_id: int,
):
    """Record ghost check result from a like boost visit.

    Spec: 2-step verification:
    1st check = suspicious → mark campaign, wait for 2nd check
    2nd check = suspicious → ghost confirmed
    """
    if result == "visible":
        campaign.ghost_check_status = GhostCheckStatus.VISIBLE
        campaign.ghost_checked_by = checked_by_account_id
        campaign.ghost_checked_at = datetime.now(timezone.utc)
        db.commit()
        log.info(f"Campaign #{campaign.id}: comment visible ✓")
        return

    # Suspicious
    if campaign.ghost_check_status == GhostCheckStatus.SUSPICIOUS:
        # 2nd confirmation → ghost confirmed
        campaign.ghost_check_status = GhostCheckStatus.GHOST
        campaign.ghost_checked_at = datetime.now(timezone.utc)
        db.commit()

        log.warning(f"Campaign #{campaign.id}: GHOST confirmed (2 checks)")

        # Find the seed account and handle ghost
        seed_step = (
            db.query(CampaignStep)
            .filter(
                CampaignStep.campaign_id == campaign.id,
                CampaignStep.step_number == 1,
            )
            .first()
        )
        if seed_step:
            account = db.query(Account).get(seed_step.account_id)
            if account:
                handle_ghost(db, account)

    else:
        # 1st suspicious → mark, await 2nd check
        campaign.ghost_check_status = GhostCheckStatus.SUSPICIOUS
        campaign.ghost_checked_by = checked_by_account_id
        campaign.ghost_checked_at = datetime.now(timezone.utc)
        db.commit()
        log.warning(f"Campaign #{campaign.id}: suspicious (awaiting 2nd check)")


def get_pending_ghost_checks(db: Session) -> list[Campaign]:
    """Get campaigns that need ghost verification."""
    return (
        db.query(Campaign)
        .filter(Campaign.ghost_check_status.in_([
            GhostCheckStatus.PENDING,
            GhostCheckStatus.SUSPICIOUS,
        ]))
        .all()
    )
