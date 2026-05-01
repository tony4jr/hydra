"""Niche CRUD API — PR-3b.

Niche = Brand 의 시장 정의 + 정책 (1:N).
PR-3a 에서 default Niche 1:1 백필 완료.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import Brand, Niche


router = APIRouter()


_VALID_STATES = {"active", "paused", "archived"}
_VALID_DEPTHS = {"quick", "standard", "deep", "max"}


class NicheCreate(BaseModel):
    brand_id: int
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None
    market_definition: Optional[str] = None
    embedding_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    trending_vph_threshold: int = Field(default=1000, ge=0)
    new_video_hours: int = Field(default=6, ge=0)
    long_term_score_threshold: int = Field(default=70, ge=0)
    collection_depth: str = "standard"
    keyword_variation_count: int = Field(default=5, ge=0)
    preset_per_video_limit: int = Field(default=1, ge=1)
    state: str = "active"

    @field_validator("collection_depth")
    @classmethod
    def _depth(cls, v: str) -> str:
        if v not in _VALID_DEPTHS:
            raise ValueError(f"collection_depth must be one of {sorted(_VALID_DEPTHS)}")
        return v

    @field_validator("state")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in _VALID_STATES:
            raise ValueError(f"state must be one of {sorted(_VALID_STATES)}")
        return v


class NicheUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = None
    market_definition: Optional[str] = None
    embedding_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    trending_vph_threshold: Optional[int] = Field(default=None, ge=0)
    new_video_hours: Optional[int] = Field(default=None, ge=0)
    long_term_score_threshold: Optional[int] = Field(default=None, ge=0)
    collection_depth: Optional[str] = None
    keyword_variation_count: Optional[int] = Field(default=None, ge=0)
    preset_per_video_limit: Optional[int] = Field(default=None, ge=1)
    state: Optional[str] = None

    @field_validator("collection_depth")
    @classmethod
    def _depth(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_DEPTHS:
            raise ValueError(f"collection_depth must be one of {sorted(_VALID_DEPTHS)}")
        return v

    @field_validator("state")
    @classmethod
    def _state(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_STATES:
            raise ValueError(f"state must be one of {sorted(_VALID_STATES)}")
        return v


def _serialize(n: Niche) -> dict:
    return {
        "id": n.id,
        "brand_id": n.brand_id,
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
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


@router.get("")
def list_niches(
    brand_id: Optional[int] = None,
    state: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(Niche)
    if brand_id is not None:
        q = q.filter(Niche.brand_id == brand_id)
    if state is not None:
        if state not in _VALID_STATES:
            raise HTTPException(400, f"state must be one of {sorted(_VALID_STATES)}")
        q = q.filter(Niche.state == state)
    else:
        q = q.filter(Niche.state != "archived")
    return [_serialize(n) for n in q.order_by(Niche.id.asc()).all()]


@router.get("/{niche_id}")
def get_niche(niche_id: int, db: Session = Depends(get_db)):
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")
    return _serialize(n)


@router.post("")
def create_niche(data: NicheCreate, db: Session = Depends(get_db)):
    brand = db.get(Brand, data.brand_id)
    if brand is None:
        raise HTTPException(409, f"brand {data.brand_id} not found")
    n = Niche(**data.model_dump())
    db.add(n)
    db.commit()
    db.refresh(n)
    return _serialize(n)


@router.patch("/{niche_id}")
def update_niche(niche_id: int, data: NicheUpdate, db: Session = Depends(get_db)):
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(n, k, v)
    db.commit()
    db.refresh(n)
    return _serialize(n)


@router.delete("/{niche_id}")
def delete_niche(
    niche_id: int,
    hard: bool = False,
    db: Session = Depends(get_db),
):
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")
    if hard:
        try:
            db.delete(n)
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(409, f"cannot hard delete: {e}")
        return {"deleted": niche_id, "mode": "hard"}
    n.state = "archived"
    db.commit()
    return {"deleted": niche_id, "mode": "soft"}
