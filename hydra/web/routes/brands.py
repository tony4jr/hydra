"""Brand management API."""

import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import Brand

router = APIRouter()


class BrandCreate(BaseModel):
    name: str
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


@router.get("/api/list")
def list_brands(db: Session = Depends(get_db)):
    brands = db.query(Brand).all()
    return [
        {"id": b.id, "name": b.name, "category": b.product_category, "status": b.status}
        for b in brands
    ]


@router.post("/api/create")
def create_brand(data: BrandCreate, db: Session = Depends(get_db)):
    brand = Brand(
        name=data.name,
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


@router.get("/api/{brand_id}")
def get_brand(brand_id: int, db: Session = Depends(get_db)):
    b = db.query(Brand).get(brand_id)
    if not b:
        return {"error": "not found"}
    return {
        "id": b.id, "name": b.name, "category": b.product_category,
        "core_message": b.core_message, "brand_story": b.brand_story,
        "target_keywords": json.loads(b.target_keywords or "[]"),
        "allowed_keywords": json.loads(b.allowed_keywords or "[]"),
        "banned_keywords": json.loads(b.banned_keywords or "[]"),
        "selling_points": json.loads(b.selling_points or "[]"),
        "mention_rules": json.loads(b.mention_rules or "{}"),
        "tone_guide": b.tone_guide,
        "target_audience": b.target_audience,
    }


@router.post("/api/{brand_id}/update")
def update_brand(brand_id: int, data: BrandCreate, db: Session = Depends(get_db)):
    b = db.query(Brand).get(brand_id)
    if not b:
        return {"error": "not found"}
    b.name = data.name or b.name
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
    db.commit()
    return {"ok": True, "id": b.id}
