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


# --- 캠페인 프로젝트 생성 (키워드 기반, video_id 없이) ---

class CampaignProjectCreate(BaseModel):
    brand_id: int
    target_keywords: list[str] = []
    preset_codes: list[str] = []
    sets_per_video: int = 1
    mention_style: str = ""
    duration_days: int = 7
    target_count: int = 10
    name: str | None = None


@router.post("/api/create-project")
def create_campaign_project(data: CampaignProjectCreate, db: Session = Depends(get_db)):
    """키워드 기반 캠페인 프로젝트 생성. 영상은 자동 수집 후 태스크 생성."""
    import json
    from datetime import UTC

    brand = db.get(Brand, data.brand_id)
    if not brand:
        return {"error": "Brand not found"}

    # 캠페인 이름 자동 생성
    campaign_name = data.name or f"{brand.name} — {', '.join(data.target_keywords[:3])} 캠페인"

    now = datetime.now(UTC)
    campaign = Campaign(
        video_id=None,  # 프로젝트형 캠페인 (영상은 자동 수집 후 배정)
        brand_id=data.brand_id,
        scenario=data.preset_codes[0] if data.preset_codes else "A",
        campaign_type="scenario",
        comment_mode="ai_auto",
        status="planning",
        name=campaign_name,
        target_keywords=json.dumps(data.target_keywords, ensure_ascii=False),
        mention_style=data.mention_style,
        selected_presets=json.dumps(data.preset_codes, ensure_ascii=False),
        sets_per_video=data.sets_per_video,
        duration_days=data.duration_days,
        target_count=data.target_count,
        start_date=now,
        end_date=now + timedelta(days=data.duration_days),
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    return {
        "id": campaign.id,
        "name": campaign_name,
        "status": campaign.status,
        "target_count": data.target_count,
        "duration_days": data.duration_days,
    }


# --- 다이렉트 캠페인 API ---

class DirectCampaignCreate(BaseModel):
    video_urls: list[str]
    work_mode: str = "preset"  # preset | manual
    preset_code: str | None = None
    brand_id: int | None = None
    like_count: int = 0
    subscribe: bool = False
    manual_steps: list[dict] | None = None


@router.post("/api/direct/create")
def create_direct_campaign(data: DirectCampaignCreate, db: Session = Depends(get_db)):
    """다이렉트 캠페인 생성 — URL별로 캠페인 + 태스크 생성."""
    import json
    from datetime import UTC
    from hydra.services.campaign_service import extract_video_id

    created = []
    for url in data.video_urls:
        video_id = extract_video_id(url)
        if not video_id:
            continue

        # 영상이 DB에 없으면 추가
        video = db.get(Video, video_id)
        if not video:
            video = Video(id=video_id, url=url, status="available")
            db.add(video)
            db.flush()

        campaign = Campaign(
            video_id=video_id,
            brand_id=data.brand_id,
            scenario=data.preset_code or "direct",
            campaign_type="direct",
            comment_mode="ai_auto" if data.work_mode == "preset" else "manual",
            status="in_progress",
            name=f"다이렉트 — {video.title or video_id}",
        )
        db.add(campaign)
        db.flush()

        now = datetime.now(UTC)
        from hydra.db.models import Task

        # 댓글 태스크 (프리셋 or 수동)
        if data.work_mode == "preset" and data.preset_code:
            task = Task(
                campaign_id=campaign.id,
                task_type="comment",
                priority="normal",
                status="pending",
                payload=json.dumps({
                    "video_id": video_id,
                    "preset_code": data.preset_code,
                    "brand_id": data.brand_id,
                }, ensure_ascii=False),
                scheduled_at=now,
            )
            db.add(task)
        elif data.work_mode == "manual" and data.manual_steps:
            for i, step in enumerate(data.manual_steps):
                task = Task(
                    campaign_id=campaign.id,
                    task_type=step.get("type", "comment"),
                    priority="normal",
                    status="pending",
                    payload=json.dumps({
                        "video_id": video_id,
                        "text": step.get("text", ""),
                        "role": step.get("role", "seed"),
                        "target": step.get("target", "main"),
                        "step_number": i + 1,
                    }, ensure_ascii=False),
                    scheduled_at=now + timedelta(minutes=i * 5),  # 스텝 간 5분 간격
                )
                db.add(task)

        # 좋아요 태스크
        import random
        for j in range(data.like_count):
            task = Task(
                campaign_id=campaign.id,
                task_type="like",
                priority="low",
                status="pending",
                payload=json.dumps({"video_id": video_id}, ensure_ascii=False),
                scheduled_at=now + timedelta(seconds=random.uniform(15, 90) * j),
            )
            db.add(task)

        # 구독 태스크
        if data.subscribe:
            task = Task(
                campaign_id=campaign.id,
                task_type="subscribe",
                priority="low",
                status="pending",
                payload=json.dumps({"video_id": video_id}, ensure_ascii=False),
                scheduled_at=now,
            )
            db.add(task)

        db.commit()
        created.append({"id": campaign.id, "video_id": video_id})

    return {"ok": True, "created": len(created), "campaigns": created}


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


# --- Path parameter routes MUST be last to avoid conflicts ---

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
