"""Brand management API."""

import json
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from hydra.db.session import get_db
from hydra.db.models import Brand, Campaign, CampaignStep, ActionLog, Keyword, Niche

router = APIRouter()


class BrandCreate(BaseModel):
    name: str
    product_name: str | None = None
    product_category: str | None = None
    core_message: str | None = None
    brand_story: str | None = None
    target_keywords: list[str] | None = None
    allowed_keywords: list[str] | None = None
    banned_keywords: list[str] | None = None
    ingredients: list[str] | None = None
    selling_points: list[str] | None = None
    mention_rules: dict | None = None
    tone_guide: str | None = None
    target_audience: str | None = None
    weekly_campaign_target: int | None = None
    auto_campaign_enabled: bool | None = None


@router.get("/api/list")
def list_brands(db: Session = Depends(get_db)):
    brands = db.query(Brand).filter(Brand.status != "deleted").all()
    return [
        {"id": b.id, "name": b.name, "product_name": b.product_name, "category": b.product_category, "status": b.status}
        for b in brands
    ]


@router.post("/api/create")
def create_brand(data: BrandCreate, db: Session = Depends(get_db)):
    brand = Brand(
        name=data.name,
        product_name=data.product_name,
        product_category=data.product_category,
        core_message=data.core_message,
        brand_story=data.brand_story,
        target_keywords=json.dumps(data.target_keywords or [], ensure_ascii=False),
        allowed_keywords=json.dumps(data.allowed_keywords or [], ensure_ascii=False),
        banned_keywords=json.dumps(data.banned_keywords or [], ensure_ascii=False),
        ingredients=json.dumps(data.ingredients or [], ensure_ascii=False),
        selling_points=json.dumps(data.selling_points or [], ensure_ascii=False),
        mention_rules=json.dumps(data.mention_rules or {}, ensure_ascii=False),
        tone_guide=data.tone_guide,
        target_audience=data.target_audience,
    )
    db.add(brand)
    db.commit()
    return {"id": brand.id, "name": brand.name}


@router.get("/api/performance-summary")
def all_brands_performance(days: int = 30, db: Session = Depends(get_db)):
    """Performance summary across all brands."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    brands = db.query(Brand).filter(Brand.status == "active").all()

    results = []
    for b in brands:
        campaign_count = (
            db.query(func.count())
            .filter(Campaign.brand_id == b.id, Campaign.created_at >= cutoff)
            .scalar()
        )
        comment_count = (
            db.query(func.count())
            .filter(
                ActionLog.campaign_id.in_(
                    db.query(Campaign.id).filter(Campaign.brand_id == b.id)
                ),
                ActionLog.action_type.in_(["comment", "reply"]),
                ActionLog.created_at >= cutoff,
            )
            .scalar()
        )
        ghost_count = (
            db.query(func.count())
            .filter(
                Campaign.brand_id == b.id,
                Campaign.ghost_check_status == "ghost",
                Campaign.created_at >= cutoff,
            )
            .scalar()
        )

        results.append({
            "id": b.id,
            "name": b.name,
            "category": b.product_category,
            "campaigns": campaign_count,
            "comments": comment_count,
            "ghosts": ghost_count,
        })

    return {"period_days": days, "brands": results}


@router.get("/api/{brand_id}")
def get_brand(brand_id: int, db: Session = Depends(get_db)):
    b = db.query(Brand).get(brand_id)
    if not b:
        return {"error": "not found"}
    niches = (
        db.query(Niche)
        .filter(Niche.brand_id == brand_id, Niche.state != "archived")
        .order_by(Niche.id.asc())
        .all()
    )
    return {
        "id": b.id, "name": b.name, "product_name": b.product_name, "category": b.product_category,
        "core_message": b.core_message, "brand_story": b.brand_story,
        "target_keywords": json.loads(b.target_keywords or "[]"),
        "allowed_keywords": json.loads(b.allowed_keywords or "[]"),
        "banned_keywords": json.loads(b.banned_keywords or "[]"),
        "selling_points": json.loads(b.selling_points or "[]"),
        "mention_rules": json.loads(b.mention_rules or "{}"),
        "tone_guide": b.tone_guide,
        "target_audience": b.target_audience,
        # PR-8c — Brand v2 운영 자산
        "industry": b.industry,
        "tone": b.tone,
        "common_phrases": json.loads(b.common_phrases or "[]"),
        "forbidden_words": json.loads(b.forbidden_words or "[]"),
        "avoid_competitors": json.loads(b.avoid_competitors or "[]"),
        "target_demographics": json.loads(b.target_demographics or "{}"),
        # PR-3b: Niche 배열 추가 (frontend 가 PR-3c 에서 사용 시작)
        "niches": [
            {
                "id": n.id,
                "name": n.name,
                "description": n.description,
                "market_definition": n.market_definition,
                "embedding_threshold": n.embedding_threshold,
                "trending_vph_threshold": n.trending_vph_threshold,
                "new_video_hours": n.new_video_hours,
                "long_term_score_threshold": n.long_term_score_threshold,
                "collection_depth": n.collection_depth,
                "keyword_variation_count": n.keyword_variation_count,
                "preset_per_video_limit": n.preset_per_video_limit,
                "state": n.state,
            }
            for n in niches
        ],
    }


@router.post("/api/{brand_id}/update")
def update_brand(brand_id: int, data: BrandCreate, db: Session = Depends(get_db)):
    b = db.query(Brand).get(brand_id)
    if not b:
        return {"error": "not found"}
    b.name = data.name or b.name
    if data.product_name is not None:
        b.product_name = data.product_name
    b.product_category = data.product_category or b.product_category
    b.core_message = data.core_message or b.core_message
    b.brand_story = data.brand_story or b.brand_story
    b.target_audience = data.target_audience or b.target_audience
    b.tone_guide = data.tone_guide or b.tone_guide
    if data.target_keywords is not None:
        b.target_keywords = json.dumps(data.target_keywords, ensure_ascii=False)
    if data.allowed_keywords is not None:
        b.allowed_keywords = json.dumps(data.allowed_keywords, ensure_ascii=False)
    if data.banned_keywords is not None:
        b.banned_keywords = json.dumps(data.banned_keywords, ensure_ascii=False)
    if data.selling_points is not None:
        b.selling_points = json.dumps(data.selling_points, ensure_ascii=False)
    if data.mention_rules is not None:
        b.mention_rules = json.dumps(data.mention_rules, ensure_ascii=False)
    if data.ingredients is not None:
        b.ingredients = json.dumps(data.ingredients, ensure_ascii=False)
    if data.weekly_campaign_target is not None:
        b.weekly_campaign_target = data.weekly_campaign_target
    if data.auto_campaign_enabled is not None:
        b.auto_campaign_enabled = data.auto_campaign_enabled
    db.commit()
    return {"ok": True, "id": b.id}


# --- #23: Brand field-level updates for UI ---

class BrandFieldUpdate(BaseModel):
    field: str
    value: Any


@router.post("/api/{brand_id}/update-field")
def update_brand_field(brand_id: int, data: BrandFieldUpdate, db: Session = Depends(get_db)):
    """Update a single brand field. Handles JSON serialization for list/dict fields."""
    b = db.query(Brand).get(brand_id)
    if not b:
        return {"error": "not found"}

    json_fields = {
        "target_keywords", "allowed_keywords", "banned_keywords",
        "ingredients", "selling_points", "mention_rules",
    }
    text_fields = {
        "name", "product_name", "product_category", "core_message", "brand_story",
        "tone_guide", "target_audience", "status",
    }

    if data.field in json_fields:
        setattr(b, data.field, json.dumps(data.value, ensure_ascii=False))
    elif data.field in text_fields:
        setattr(b, data.field, data.value)
    else:
        return {"error": f"Unknown field: {data.field}"}

    db.commit()
    return {"ok": True, "field": data.field}


@router.post("/api/{brand_id}/add-keyword")
def add_brand_keyword(brand_id: int, keyword: str, field: str = "allowed_keywords", db: Session = Depends(get_db)):
    """Add a keyword to a brand's keyword list (allowed/banned/target)."""
    b = db.query(Brand).get(brand_id)
    if not b:
        return {"error": "not found"}

    if field not in ("allowed_keywords", "banned_keywords", "target_keywords"):
        return {"error": "invalid field"}

    current = json.loads(getattr(b, field) or "[]")
    if keyword not in current:
        current.append(keyword)
        setattr(b, field, json.dumps(current, ensure_ascii=False))
        db.commit()

    return {"ok": True, "keywords": current}


@router.post("/api/{brand_id}/remove-keyword")
def remove_brand_keyword(brand_id: int, keyword: str, field: str = "allowed_keywords", db: Session = Depends(get_db)):
    """Remove a keyword from a brand's keyword list."""
    b = db.query(Brand).get(brand_id)
    if not b:
        return {"error": "not found"}

    if field not in ("allowed_keywords", "banned_keywords", "target_keywords"):
        return {"error": "invalid field"}

    current = json.loads(getattr(b, field) or "[]")
    if keyword in current:
        current.remove(keyword)
        setattr(b, field, json.dumps(current, ensure_ascii=False))
        db.commit()

    return {"ok": True, "keywords": current}


# --- #10: Brand Performance ---

@router.get("/api/{brand_id}/performance")
def brand_performance(brand_id: int, days: int = 30, db: Session = Depends(get_db)):
    """Per-brand performance metrics."""
    brand = db.query(Brand).get(brand_id)
    if not brand:
        return {"error": "not found"}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Campaign stats
    campaigns = (
        db.query(Campaign)
        .filter(Campaign.brand_id == brand_id, Campaign.created_at >= cutoff)
        .all()
    )
    campaign_ids = [c.id for c in campaigns]

    total_campaigns = len(campaigns)
    completed = sum(1 for c in campaigns if c.status == "completed")
    ghost_count = sum(1 for c in campaigns if c.ghost_check_status == "ghost")

    # Step stats
    step_stats = {"total": 0, "done": 0, "failed": 0}
    if campaign_ids:
        row = (
            db.query(
                func.count().label("total"),
                func.sum(case((CampaignStep.status == "done", 1), else_=0)).label("done"),
                func.sum(case((CampaignStep.status == "failed", 1), else_=0)).label("failed"),
            )
            .filter(CampaignStep.campaign_id.in_(campaign_ids))
            .first()
        )
        step_stats = {
            "total": row.total or 0,
            "done": int(row.done or 0),
            "failed": int(row.failed or 0),
        }

    # Comments posted for this brand
    comments_posted = 0
    if campaign_ids:
        comments_posted = (
            db.query(func.count())
            .filter(
                ActionLog.campaign_id.in_(campaign_ids),
                ActionLog.action_type.in_(["comment", "reply"]),
            )
            .scalar()
        )

    # Keyword stats
    keywords = db.query(Keyword).filter(Keyword.brand_id == brand_id).all()
    keyword_stats = {
        "total": len(keywords),
        "active": sum(1 for k in keywords if k.status == "active"),
        "total_videos_found": sum(k.total_videos_found or 0 for k in keywords),
    }

    # Scenario distribution
    scenario_dist = {}
    for c in campaigns:
        scenario_dist[c.scenario] = scenario_dist.get(c.scenario, 0) + 1

    success_rate = round(step_stats["done"] / step_stats["total"] * 100, 1) if step_stats["total"] > 0 else 0.0

    return {
        "brand_id": brand_id,
        "brand_name": brand.name,
        "period_days": days,
        "campaigns": {
            "total": total_campaigns,
            "completed": completed,
            "ghost": ghost_count,
        },
        "steps": step_stats,
        "success_rate": success_rate,
        "comments_posted": comments_posted,
        "keywords": keyword_stats,
        "scenario_distribution": scenario_dist,
    }


# ───────────── T18 미리보기 ─────────────
class PreviewRequest(BaseModel):
    funnel_stage: str
    count: int = 3


@router.post("/{brand_id}/preview-comments")
def preview_comments(
    brand_id: int,
    req: PreviewRequest,
):
    """T18 — 퍼널 단계별 댓글 샘플 N개 (실 Claude 호출 — key 있으면).

    key 미설정 시 stub 응답으로 graceful degrade.
    """
    from hydra.core.config import settings
    if not settings.claude_api_key:
        return [
            f"(stub — Claude key 미설정 — {req.funnel_stage} 톤 샘플 {i+1})"
            for i in range(req.count)
        ]
    # 실 호출 — comment_agent 재사용. brand 로드 + dummy persona/role/video.
    from hydra.db.session import SessionLocal
    from hydra.db.models import Brand as BrandModel, Video
    from hydra.ai.agents.comment_agent import generate_comment
    from hydra.core.enums import AccountRole
    db = SessionLocal()
    try:
        brand = db.get(BrandModel, brand_id)
        if brand is None:
            return []
        # 테스트용 더미 video — 미리보기라 실제 게시 X
        dummy_video = Video(id="preview", title="(미리보기 — 영상 제목)",
                            url="https://www.youtube.com/watch?v=preview")
        dummy_persona = {
            "age": 28, "gender": "female", "region": "서울",
            "occupation": "직장인", "interests": ["뷰티"],
            "speech_style": "편한 존댓말", "comment_length": "medium",
        }
        out = []
        for i in range(min(req.count, 5)):
            try:
                c = generate_comment(
                    persona=dummy_persona,
                    role=AccountRole.WITNESS,
                    brand=brand,
                    video=dummy_video,
                    funnel_stage=req.funnel_stage,
                    max_retries=1,
                )
                out.append(c)
            except Exception as e:
                out.append(f"(생성 실패: {e})")
        return out
    finally:
        db.close()
