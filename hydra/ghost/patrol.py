"""Comment survival patrol — periodic check for ghost/deleted comments.

Spec 8.4 extension:
- Stage 1: DOM check (ghost vs visible) — done during like boost
- Stage 2: YouTube Data API check (actually deleted vs ghost-banned)

This module provides the scheduled patrol that re-checks all recent comments
without requiring a browser session.
"""

from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from hydra.core.config import settings
from hydra.core.logger import get_logger
from hydra.core.enums import GhostCheckStatus
from hydra.db.models import ActionLog, CampaignStep, Campaign, Account
from hydra.ghost.detector import report_ghost_check
from hydra.collection.youtube_api import _get_youtube_service, _rotate_key

log = get_logger("patrol")


def _batch_check_comments_api(comment_ids: list[str]) -> dict[str, str]:
    """Check comment existence via YouTube Data API (commentThreads.list).

    Returns dict of {comment_id: "visible"|"deleted"}.
    Comments not returned by the API are considered deleted.
    """
    yt = _get_youtube_service()
    results = {}

    for i in range(0, len(comment_ids), 50):
        batch = comment_ids[i:i + 50]
        try:
            resp = yt.comments().list(
                id=",".join(batch),
                part="id,snippet",
                textFormat="plainText",
            ).execute()
        except Exception as e:
            if "quotaExceeded" in str(e):
                _rotate_key()
                continue
            log.error(f"Comment API check failed: {e}")
            # Mark as unchecked rather than assuming deleted
            for cid in batch:
                results[cid] = "unchecked"
            continue

        returned_ids = {item["id"] for item in resp.get("items", [])}
        for cid in batch:
            results[cid] = "visible" if cid in returned_ids else "deleted"

    return results


def run_patrol(db: Session, hours_back: int = 72, max_comments: int = 500) -> dict:
    """Run survival patrol on recent comments.

    Checks comments posted in the last `hours_back` hours.
    Returns summary: {checked, visible, ghost, deleted, errors}.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    # Get recent promo comments with youtube_comment_id
    logs = (
        db.query(ActionLog)
        .filter(
            ActionLog.action_type.in_(["comment", "reply"]),
            ActionLog.is_promo == True,
            ActionLog.youtube_comment_id.isnot(None),
            ActionLog.youtube_comment_id != "",
            ActionLog.created_at >= cutoff,
        )
        .order_by(ActionLog.created_at.desc())
        .limit(max_comments)
        .all()
    )

    if not logs:
        log.info("Patrol: no recent comments to check")
        return {"checked": 0, "visible": 0, "ghost": 0, "deleted": 0}

    comment_ids = [al.youtube_comment_id for al in logs]
    log_map = {al.youtube_comment_id: al for al in logs}

    # Stage 2: API check
    api_results = _batch_check_comments_api(comment_ids)

    visible = 0
    ghost = 0
    deleted = 0

    for cid, status in api_results.items():
        al = log_map.get(cid)
        if not al:
            continue

        if status == "visible":
            visible += 1
        elif status == "deleted":
            deleted += 1
            # Find the campaign step to update ghost status
            _handle_deleted_comment(db, al)
        # "unchecked" → skip, will retry next patrol

    db.commit()

    summary = {
        "checked": len(comment_ids),
        "visible": visible,
        "ghost": ghost,
        "deleted": deleted,
    }
    log.info(f"Patrol complete: {summary}")

    if deleted > 0:
        from hydra.infra import telegram
        telegram.warning(f"🚨 순찰 결과: {deleted}개 댓글 삭제 감지 (총 {len(comment_ids)}개 확인)")

    return summary


def _handle_deleted_comment(db: Session, action_log: ActionLog):
    """Handle a confirmed deleted comment — update campaign and account."""
    if not action_log.campaign_id:
        return

    campaign = db.query(Campaign).get(action_log.campaign_id)
    if not campaign:
        return

    # If campaign ghost status isn't already ghost, report it
    if campaign.ghost_check_status != GhostCheckStatus.GHOST:
        # API-confirmed deletion goes straight to GHOST (no 2-step needed)
        campaign.ghost_check_status = GhostCheckStatus.GHOST
        campaign.ghost_checked_at = datetime.now(timezone.utc)

        # Find seed account and handle ghost
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
                from hydra.accounts.manager import handle_ghost
                handle_ghost(db, account)

        log.warning(f"Campaign #{campaign.id}: comment DELETED (API confirmed)")
