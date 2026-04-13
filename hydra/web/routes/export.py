"""Data export API — CSV download for accounts, actions, campaigns."""

import csv
import io
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import Account, ActionLog, Campaign, CampaignStep, Video

router = APIRouter()


# --- #1: CSV Template Download ---

@router.get("/api/csv-template/accounts")
def download_account_template():
    """Download CSV template for bulk account import."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["gmail", "password", "recovery_email", "phone_number", "totp_secret"])
    writer.writerow(["user@gmail.com", "MyP@ss123", "recovery@gmail.com", "+821012345678", "JBSWY3DPEHPK3PXP"])
    writer.writerow(["user2@gmail.com", "Pass456!", "", "", ""])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hydra_accounts_template.csv"},
    )


# --- #14: Data Export ---

@router.get("/api/accounts")
def export_accounts(db: Session = Depends(get_db)):
    """Export all accounts as CSV."""
    accounts = db.query(Account).order_by(Account.id).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "gmail", "status", "warmup_group", "ghost_count",
        "has_persona", "has_cookies", "adspower_profile_id",
        "last_active_at", "created_at",
    ])
    for a in accounts:
        writer.writerow([
            a.id, a.gmail, a.status, a.warmup_group or "", a.ghost_count or 0,
            "Y" if a.persona else "N", "Y" if a.cookies else "N",
            a.adspower_profile_id or "",
            str(a.last_active_at) if a.last_active_at else "",
            str(a.created_at),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=hydra_accounts_{_today()}.csv"},
    )


@router.get("/api/actions")
def export_actions(
    days: int = 7,
    db: Session = Depends(get_db),
):
    """Export action logs as CSV. Default: last 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    logs = (
        db.query(ActionLog)
        .filter(ActionLog.created_at >= cutoff)
        .order_by(ActionLog.created_at.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "account_id", "video_id", "campaign_id",
        "action_type", "is_promo", "content", "youtube_comment_id",
        "ip_address", "duration_sec", "status", "created_at",
    ])
    for al in logs:
        writer.writerow([
            al.id, al.account_id, al.video_id or "", al.campaign_id or "",
            al.action_type, al.is_promo, (al.content or "")[:200],
            al.youtube_comment_id or "",
            al.ip_address or "", al.duration_sec or "",
            al.status, str(al.created_at),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=hydra_actions_{_today()}.csv"},
    )


@router.get("/api/campaigns")
def export_campaigns(db: Session = Depends(get_db)):
    """Export campaigns with step summary as CSV."""
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "video_id", "video_title", "brand_id", "scenario",
        "status", "ghost_status", "steps_total", "steps_done",
        "created_at", "completed_at",
    ])
    for c in campaigns:
        video = db.query(Video).get(c.video_id)
        steps = db.query(CampaignStep).filter(CampaignStep.campaign_id == c.id).all()
        done = sum(1 for s in steps if s.status == "done")
        writer.writerow([
            c.id, c.video_id, video.title if video else "",
            c.brand_id, c.scenario, c.status,
            c.ghost_check_status or "", len(steps), done,
            str(c.created_at), str(c.completed_at) if c.completed_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=hydra_campaigns_{_today()}.csv"},
    )


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")
