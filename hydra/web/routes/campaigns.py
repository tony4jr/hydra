"""Campaign management API."""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from hydra.db.session import get_db
from hydra.db.models import Campaign, CampaignStep, Video, Brand, Account, LikeBoostQueue

router = APIRouter()


class CampaignCreate(BaseModel):
    video_id: str
    brand_id: int
    scenario: str | None = None
    like_preset: str = "normal"


@router.post("/api/create")
def create_campaign_api(data: CampaignCreate, db: Session = Depends(get_db)):
    """Create a new campaign for a video."""
    from hydra.core.campaign import create_campaign
    from hydra.core.enums import Scenario, LikeBoostPreset

    video = db.query(Video).get(data.video_id)
    if not video:
        return {"error": "Video not found"}
    brand = db.query(Brand).get(data.brand_id)
    if not brand:
        return {"error": "Brand not found"}

    scenario = Scenario(data.scenario) if data.scenario else None
    preset = LikeBoostPreset(data.like_preset)

    campaign = create_campaign(db, video, brand, scenario=scenario, like_preset=preset)
    return {
        "id": campaign.id,
        "scenario": campaign.scenario,
        "status": campaign.status,
        "steps": db.query(CampaignStep).filter(CampaignStep.campaign_id == campaign.id).count(),
    }


# --- #5: Bulk URL Campaign ---

class BulkUrlInput(BaseModel):
    urls: list[str]
    brand_id: int
    scenario: str | None = None
    like_preset: str = "normal"


@router.post("/api/bulk-create")
def bulk_create_campaigns(data: BulkUrlInput, db: Session = Depends(get_db)):
    """Create campaigns for multiple video URLs at once.

    Auto-detects long/short format and creates/reuses Video records.
    """
    import re
    from hydra.core.campaign import create_campaign
    from hydra.core.enums import Scenario, LikeBoostPreset

    brand = db.query(Brand).get(data.brand_id)
    if not brand:
        return {"error": "Brand not found"}

    scenario = Scenario(data.scenario) if data.scenario else None
    preset = LikeBoostPreset(data.like_preset)

    results = {"created": 0, "skipped": 0, "errors": []}

    for url in data.urls:
        url = url.strip()
        if not url:
            continue

        # Extract video ID
        video_id = _extract_video_id(url)
        if not video_id:
            results["errors"].append(f"Invalid URL: {url[:60]}")
            continue

        # Get or create video
        video = db.query(Video).get(video_id)
        if not video:
            is_short = "/shorts/" in url
            video = Video(
                id=video_id,
                url=f"https://www.youtube.com/watch?v={video_id}",
                is_short=is_short,
                status="available",
            )
            db.add(video)
            db.commit()

        try:
            create_campaign(db, video, brand, scenario=scenario, like_preset=preset)
            results["created"] += 1
        except Exception as e:
            results["errors"].append(f"{video_id}: {str(e)[:60]}")

    return results


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    import re
    patterns = [
        r"(?:v=|/v/)([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    # Bare ID?
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url
    return None


# --- #6: Custom Like Boost (All Accounts) ---

class CustomLikeInput(BaseModel):
    youtube_comment_url: str
    max_accounts: int = 50


@router.post("/api/custom-like-boost")
def custom_like_boost(data: CustomLikeInput, db: Session = Depends(get_db)):
    """Mobilize all available accounts to like a specific comment.

    Input: YouTube comment URL (contains video_id + comment_id).
    """
    import re

    # Parse URL: youtube.com/watch?v=XXX&lc=YYY
    video_match = re.search(r"v=([a-zA-Z0-9_-]{11})", data.youtube_comment_url)
    comment_match = re.search(r"lc=([a-zA-Z0-9_.-]+)", data.youtube_comment_url)

    if not video_match or not comment_match:
        return {"error": "Invalid comment URL. Expected format: youtube.com/watch?v=XXX&lc=YYY"}

    video_id = video_match.group(1)
    comment_id = comment_match.group(1)

    # Get available active accounts
    accounts = (
        db.query(Account)
        .filter(Account.status == "active")
        .limit(data.max_accounts)
        .all()
    )

    if not accounts:
        return {"error": "No active accounts available"}

    # Create a virtual campaign for tracking
    video = db.query(Video).get(video_id)
    if not video:
        video = Video(id=video_id, url=f"https://www.youtube.com/watch?v={video_id}", status="available")
        db.add(video)
        db.commit()

    # Schedule like boosts
    from hydra.like_boost.engine import schedule_custom_boost
    count = schedule_custom_boost(db, video_id, comment_id, accounts)

    return {"ok": True, "video_id": video_id, "comment_id": comment_id, "accounts_scheduled": count}


@router.post("/api/{campaign_id}/cancel")
def cancel_campaign(campaign_id: int, db: Session = Depends(get_db)):
    c = db.query(Campaign).get(campaign_id)
    if not c:
        return {"error": "not found"}
    c.status = "cancelled"
    # Cancel pending steps
    db.query(CampaignStep).filter(
        CampaignStep.campaign_id == c.id,
        CampaignStep.status.in_(["pending", "generating", "ready"]),
    ).update({"status": "cancelled"}, synchronize_session="fetch")
    db.commit()
    return {"ok": True}


@router.get("/api/list")
def list_campaigns(
    status: str | None = None,
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Campaign)
    if status:
        query = query.filter(Campaign.status == status)
    total = query.count()
    campaigns = query.order_by(Campaign.created_at.desc()).offset((page - 1) * size).limit(size).all()

    items = []
    for c in campaigns:
        video = db.query(Video).get(c.video_id)
        brand = db.query(Brand).get(c.brand_id)
        steps = db.query(CampaignStep).filter(CampaignStep.campaign_id == c.id).all()
        items.append({
            "id": c.id,
            "video_title": video.title if video else None,
            "brand_name": brand.name if brand else None,
            "scenario": c.scenario,
            "status": c.status,
            "steps_done": sum(1 for s in steps if s.status == "done"),
            "steps_total": len(steps),
            "ghost_status": c.ghost_check_status,
            "created_at": str(c.created_at),
        })

    return {"total": total, "page": page, "items": items}


@router.get("/api/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    c = db.query(Campaign).get(campaign_id)
    if not c:
        return {"error": "not found"}

    steps = (
        db.query(CampaignStep)
        .filter(CampaignStep.campaign_id == c.id)
        .order_by(CampaignStep.step_number)
        .all()
    )

    return {
        "id": c.id,
        "video_id": c.video_id,
        "brand_id": c.brand_id,
        "scenario": c.scenario,
        "status": c.status,
        "like_boost_preset": c.like_boost_preset,
        "ghost_check_status": c.ghost_check_status,
        "created_at": str(c.created_at),
        "completed_at": str(c.completed_at) if c.completed_at else None,
        "steps": [
            {
                "step_number": s.step_number,
                "role": s.role,
                "type": s.type,
                "account_id": s.account_id,
                "content": s.content,
                "status": s.status,
                "scheduled_at": str(s.scheduled_at) if s.scheduled_at else None,
                "completed_at": str(s.completed_at) if s.completed_at else None,
                "error": s.error_message,
            }
            for s in steps
        ],
    }


# --- #27: Step Search/Filter ---

@router.get("/api/steps/search")
def search_steps(
    status: str | None = None,
    role: str | None = None,
    account_id: int | None = None,
    campaign_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
):
    """Search and filter campaign steps (work history)."""
    query = db.query(CampaignStep)

    if status:
        query = query.filter(CampaignStep.status == status)
    if role:
        query = query.filter(CampaignStep.role == role)
    if account_id:
        query = query.filter(CampaignStep.account_id == account_id)
    if campaign_id:
        query = query.filter(CampaignStep.campaign_id == campaign_id)
    if date_from:
        query = query.filter(CampaignStep.scheduled_at >= date_from)
    if date_to:
        query = query.filter(CampaignStep.scheduled_at <= date_to)

    total = query.count()
    steps = query.order_by(CampaignStep.scheduled_at.desc()).offset((page - 1) * size).limit(size).all()

    items = []
    for s in steps:
        account = db.query(Account).get(s.account_id)
        campaign = db.query(Campaign).get(s.campaign_id)
        video = db.query(Video).get(campaign.video_id) if campaign else None
        brand = db.query(Brand).get(campaign.brand_id) if campaign else None
        items.append({
            "step_id": s.id,
            "campaign_id": s.campaign_id,
            "step_number": s.step_number,
            "role": s.role,
            "type": s.type,
            "status": s.status,
            "content": s.content[:80] if s.content else None,
            "youtube_comment_id": s.youtube_comment_id,
            "account_gmail": account.gmail if account else None,
            "video_title": video.title[:40] if video and video.title else None,
            "brand_name": brand.name if brand else None,
            "scheduled_at": str(s.scheduled_at) if s.scheduled_at else None,
            "completed_at": str(s.completed_at) if s.completed_at else None,
            "error": s.error_message,
            "retry_count": s.retry_count,
        })

    return {"total": total, "page": page, "items": items}


# --- #11: Work Queue Visualization ---

@router.get("/api/queue")
def work_queue(db: Session = Depends(get_db)):
    """Visualize the current work queue — pending, running, recently completed tasks."""
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)

    # Pending steps (upcoming)
    pending = (
        db.query(CampaignStep)
        .join(Campaign)
        .filter(
            CampaignStep.status.in_(["pending", "generating", "ready"]),
            Campaign.status == "in_progress",
        )
        .order_by(CampaignStep.scheduled_at)
        .limit(50)
        .all()
    )

    # Running steps
    running = (
        db.query(CampaignStep)
        .filter(CampaignStep.status == "running")
        .all()
    )

    # Recently completed (last 1h)
    completed = (
        db.query(CampaignStep)
        .filter(
            CampaignStep.status.in_(["done", "failed"]),
            CampaignStep.completed_at >= one_hour_ago,
        )
        .order_by(CampaignStep.completed_at.desc())
        .limit(30)
        .all()
    )

    # Like boost queue
    pending_boosts = (
        db.query(LikeBoostQueue)
        .filter(LikeBoostQueue.status.in_(["pending", "running"]))
        .order_by(LikeBoostQueue.scheduled_at)
        .limit(30)
        .all()
    )

    def _step_item(s: CampaignStep) -> dict:
        account = db.query(Account).get(s.account_id)
        campaign = db.query(Campaign).get(s.campaign_id)
        video = db.query(Video).get(campaign.video_id) if campaign else None
        return {
            "step_id": s.id,
            "campaign_id": s.campaign_id,
            "step_number": s.step_number,
            "role": s.role,
            "type": s.type,
            "status": s.status,
            "account_gmail": account.gmail if account else None,
            "video_title": (video.title[:40] + "...") if video and video.title and len(video.title) > 40 else (video.title if video else None),
            "scheduled_at": str(s.scheduled_at) if s.scheduled_at else None,
            "completed_at": str(s.completed_at) if s.completed_at else None,
            "error": s.error_message,
            "retry_count": s.retry_count,
        }

    # Summary counts
    total_pending = db.query(func.count()).select_from(CampaignStep).filter(
        CampaignStep.status.in_(["pending", "generating", "ready"]),
    ).scalar()
    total_running = db.query(func.count()).select_from(CampaignStep).filter(
        CampaignStep.status == "running",
    ).scalar()

    return {
        "summary": {
            "pending_steps": total_pending,
            "running_steps": total_running,
            "pending_boosts": len(pending_boosts),
        },
        "pending": [_step_item(s) for s in pending],
        "running": [_step_item(s) for s in running],
        "completed": [_step_item(s) for s in completed],
        "like_boosts": [
            {
                "id": b.id,
                "campaign_id": b.campaign_id,
                "wave": b.wave_number,
                "status": b.status,
                "scheduled_at": str(b.scheduled_at) if b.scheduled_at else None,
            }
            for b in pending_boosts
        ],
    }
