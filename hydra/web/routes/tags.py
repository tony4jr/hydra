"""Tag CRUD + 연결 API (PR-6).

namespace + value 조합 idempotent. niche/campaign N:M 연결.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import Campaign, Niche, NicheTag, CampaignTag, Tag


router = APIRouter()


class TagCreate(BaseModel):
    namespace: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None


def _serialize(t: Tag) -> dict:
    return {
        "id": t.id,
        "namespace": t.namespace,
        "value": t.value,
        "description": t.description,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/list")
def list_tags(namespace: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Tag)
    if namespace:
        q = q.filter(Tag.namespace == namespace)
    return [_serialize(t) for t in q.order_by(Tag.namespace, Tag.value).all()]


@router.post("/create")
def create_tag(data: TagCreate, db: Session = Depends(get_db)):
    """idempotent: (namespace, value) 같으면 기존 반환."""
    existing = (
        db.query(Tag)
        .filter(Tag.namespace == data.namespace, Tag.value == data.value)
        .first()
    )
    if existing:
        return _serialize(existing)
    t = Tag(namespace=data.namespace, value=data.value, description=data.description)
    db.add(t)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Tag)
            .filter(Tag.namespace == data.namespace, Tag.value == data.value)
            .first()
        )
        if existing:
            return _serialize(existing)
        raise HTTPException(409, "tag conflict")
    db.refresh(t)
    return _serialize(t)


@router.delete("/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    t = db.get(Tag, tag_id)
    if t is None:
        raise HTTPException(404, "tag not found")
    db.delete(t)
    db.commit()
    return {"deleted": tag_id}


# ─── 연결 API ────────────────────────────────────────────────────


@router.post("/niches/{niche_id}/{tag_id}")
def attach_tag_to_niche(niche_id: int, tag_id: int, db: Session = Depends(get_db)):
    if not db.get(Niche, niche_id):
        raise HTTPException(404, "niche not found")
    if not db.get(Tag, tag_id):
        raise HTTPException(404, "tag not found")
    if db.get(NicheTag, (niche_id, tag_id)):
        return {"ok": True, "already": True}
    db.add(NicheTag(niche_id=niche_id, tag_id=tag_id))
    db.commit()
    return {"ok": True}


@router.delete("/niches/{niche_id}/{tag_id}")
def detach_tag_from_niche(niche_id: int, tag_id: int, db: Session = Depends(get_db)):
    link = db.get(NicheTag, (niche_id, tag_id))
    if link is None:
        raise HTTPException(404, "link not found")
    db.delete(link)
    db.commit()
    return {"ok": True}


@router.post("/campaigns/{campaign_id}/{tag_id}")
def attach_tag_to_campaign(campaign_id: int, tag_id: int, db: Session = Depends(get_db)):
    if not db.get(Campaign, campaign_id):
        raise HTTPException(404, "campaign not found")
    if not db.get(Tag, tag_id):
        raise HTTPException(404, "tag not found")
    if db.get(CampaignTag, (campaign_id, tag_id)):
        return {"ok": True, "already": True}
    db.add(CampaignTag(campaign_id=campaign_id, tag_id=tag_id))
    db.commit()
    return {"ok": True}


@router.delete("/campaigns/{campaign_id}/{tag_id}")
def detach_tag_from_campaign(campaign_id: int, tag_id: int, db: Session = Depends(get_db)):
    link = db.get(CampaignTag, (campaign_id, tag_id))
    if link is None:
        raise HTTPException(404, "link not found")
    db.delete(link)
    db.commit()
    return {"ok": True}
