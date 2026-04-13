"""Campaign management API."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import Campaign, CampaignStep, Video, Brand

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
