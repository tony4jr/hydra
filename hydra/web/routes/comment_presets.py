"""Comment Preset CRUD (PR-8d).

운영자 댓글 트리 프리셋 라이브러리. 기존 'presets' (campaign step) 과 별도.
슬롯 CRUD 는 PR-8e.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import CommentPreset, Niche


router = APIRouter()


class CommentPresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = None


class CommentPresetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = None


def _serialize(p: CommentPreset, niche_count: int = 0) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "is_global": p.is_global,
        "is_default": p.is_default,
        "slot_count": len(p.slots) if p.slots else 0,
        "used_by_niches": niche_count,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("/list")
def list_comment_presets(db: Session = Depends(get_db)):
    rows = db.query(CommentPreset).order_by(
        CommentPreset.is_default.desc(), CommentPreset.id.asc()
    ).all()
    counts = dict(
        db.query(Niche.comment_preset_id, func.count(Niche.id))
        .filter(Niche.comment_preset_id.isnot(None))
        .group_by(Niche.comment_preset_id)
        .all()
    )
    return [_serialize(p, counts.get(p.id, 0)) for p in rows]


@router.get("/{preset_id}")
def get_comment_preset(preset_id: int, db: Session = Depends(get_db)):
    p = db.get(CommentPreset, preset_id)
    if p is None:
        raise HTTPException(404, "comment preset not found")
    niche_count = db.query(func.count(Niche.id)).filter(
        Niche.comment_preset_id == preset_id
    ).scalar() or 0
    out = _serialize(p, int(niche_count))
    out["slots"] = [
        {
            "id": s.id,
            "slot_label": s.slot_label,
            "reply_to_slot_label": s.reply_to_slot_label,
            "position": s.position,
            "text_template": s.text_template,
            "length": s.length,
            "emoji": s.emoji,
            "ai_variation": s.ai_variation,
            "like_min": s.like_min,
            "like_max": s.like_max,
            "like_distribution": s.like_distribution,
        }
        for s in p.slots
    ]
    return out


@router.post("")
def create_comment_preset(data: CommentPresetCreate, db: Session = Depends(get_db)):
    p = CommentPreset(
        name=data.name,
        description=data.description,
        is_global=True,
        is_default=False,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.post("/{preset_id}/clone")
def clone_comment_preset(preset_id: int, db: Session = Depends(get_db)):
    src = db.get(CommentPreset, preset_id)
    if src is None:
        raise HTTPException(404, "comment preset not found")
    from hydra.db.models import CommentTreeSlot
    clone = CommentPreset(
        name=f"{src.name} (복제)",
        description=src.description,
        is_global=True,
        is_default=False,
    )
    db.add(clone)
    db.flush()
    for s in src.slots:
        db.add(CommentTreeSlot(
            comment_preset_id=clone.id,
            slot_label=s.slot_label,
            reply_to_slot_label=s.reply_to_slot_label,
            position=s.position,
            text_template=s.text_template,
            length=s.length, emoji=s.emoji, ai_variation=s.ai_variation,
            like_min=s.like_min, like_max=s.like_max,
            like_distribution=s.like_distribution,
        ))
    db.commit()
    db.refresh(clone)
    return _serialize(clone)


@router.patch("/{preset_id}")
def update_comment_preset(
    preset_id: int, data: CommentPresetUpdate, db: Session = Depends(get_db)
):
    p = db.get(CommentPreset, preset_id)
    if p is None:
        raise HTTPException(404, "comment preset not found")
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(p, k, v)
    db.commit()
    return _serialize(p)


@router.delete("/{preset_id}")
def delete_comment_preset(
    preset_id: int,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    p = db.get(CommentPreset, preset_id)
    if p is None:
        raise HTTPException(404, "comment preset not found")
    if p.is_default and not force:
        raise HTTPException(409, "default preset, use ?force=true to delete")
    # 사용 중인 niche 의 FK 는 SET NULL 이므로 그대로 delete
    db.delete(p)
    db.commit()
    return {"deleted": preset_id}
