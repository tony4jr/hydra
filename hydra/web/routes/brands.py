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
    }
