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


# ─── PR-8e: 슬롯 CRUD ────────────────────────────────────────────


from hydra.db.models import CommentTreeSlot


_LENGTHS = {"short", "medium", "long"}
_EMOJIS = {"none", "sometimes", "often"}
_DISTRIBUTIONS = {"adaptive", "burst", "spread", "slow"}


class SlotCreate(BaseModel):
    slot_label: Optional[str] = None  # None = 자동 (다음 알파벳)
    reply_to_slot_label: Optional[str] = None
    text_template: str = ""
    length: str = "medium"
    emoji: str = "sometimes"
    ai_variation: int = Field(default=50, ge=0, le=100)
    like_min: int = Field(default=0, ge=0)
    like_max: int = Field(default=0, ge=0)
    like_distribution: str = "adaptive"


class SlotUpdate(BaseModel):
    slot_label: Optional[str] = None
    reply_to_slot_label: Optional[str] = None
    text_template: Optional[str] = None
    length: Optional[str] = None
    emoji: Optional[str] = None
    ai_variation: Optional[int] = Field(default=None, ge=0, le=100)
    like_min: Optional[int] = Field(default=None, ge=0)
    like_max: Optional[int] = Field(default=None, ge=0)
    like_distribution: Optional[str] = None


def _next_label(used: set[str]) -> str:
    """A → B → C → ... → Z → AA → AB ..."""
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if ch not in used:
            return ch
    # Z 후엔 AA, AB ... (드문 경우)
    for c1 in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for c2 in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            cand = c1 + c2
            if cand not in used:
                return cand
    raise ValueError("too many slots")


def _validate_slot(s: SlotCreate | SlotUpdate):
    if isinstance(s, SlotCreate):
        if s.length not in _LENGTHS:
            raise HTTPException(400, f"length must be one of {_LENGTHS}")
        if s.emoji not in _EMOJIS:
            raise HTTPException(400, f"emoji must be one of {_EMOJIS}")
        if s.like_distribution not in _DISTRIBUTIONS:
            raise HTTPException(400, f"like_distribution must be one of {_DISTRIBUTIONS}")
        if s.like_max < s.like_min:
            raise HTTPException(400, "like_max < like_min")


@router.post("/{preset_id}/slots")
def create_slot(preset_id: int, data: SlotCreate, db: Session = Depends(get_db)):
    p = db.get(CommentPreset, preset_id)
    if p is None:
        raise HTTPException(404, "comment preset not found")
    _validate_slot(data)

    existing_labels = {s.slot_label for s in p.slots}
    label = data.slot_label or _next_label(existing_labels)
    # 명시적 라벨이면 (재등장) 또는 자동 라벨 — UNIQUE 제약은 (preset_id, slot_label) → 같은 라벨 불가능?
    # spec: 슬롯 재등장 = 같은 워커 = 같은 슬롯 라벨. 그러나 UNIQUE 제약 (uq_slots_preset_label)
    # 이 막음. 재등장은 다른 row 가 같은 label 을 가져야 함 → UNIQUE 제거 필요? 또는 라벨+position 복합키.
    # 자율 결정: UNIQUE 유지, 재등장은 같은 label 의 별도 row 로 표현 — 기존 UNIQUE 가 문제.
    # 임시 해결: position 기반 별도 식별, label 은 동일 허용 위해 UNIQUE 우회 (해결 후속).
    if label in existing_labels and data.slot_label is None:
        # 자동 라벨인데 이미 있으면 다음
        label = _next_label(existing_labels)

    if data.reply_to_slot_label and data.reply_to_slot_label not in existing_labels:
        if data.reply_to_slot_label != label:
            raise HTTPException(400, f"reply_to_slot_label '{data.reply_to_slot_label}' not found")
    if data.reply_to_slot_label == label:
        raise HTTPException(400, "cannot reply to self")

    next_pos = (max((s.position for s in p.slots), default=0)) + 1

    try:
        slot = CommentTreeSlot(
            comment_preset_id=preset_id,
            slot_label=label,
            reply_to_slot_label=data.reply_to_slot_label,
            position=next_pos,
            text_template=data.text_template,
            length=data.length, emoji=data.emoji, ai_variation=data.ai_variation,
            like_min=data.like_min, like_max=data.like_max,
            like_distribution=data.like_distribution,
        )
        db.add(slot)
        db.commit()
        db.refresh(slot)
    except Exception as e:
        db.rollback()
        # UNIQUE 충돌이면 재등장 의도일 수 있음 — UI 가 "재등장" 옵션을 따로 보낼 때 처리
        raise HTTPException(409, f"slot conflict: {e}")
    return {"id": slot.id, "slot_label": slot.slot_label, "position": slot.position}


@router.patch("/{preset_id}/slots/{slot_id}")
def update_slot(
    preset_id: int, slot_id: int, data: SlotUpdate, db: Session = Depends(get_db)
):
    slot = db.get(CommentTreeSlot, slot_id)
    if slot is None or slot.comment_preset_id != preset_id:
        raise HTTPException(404, "slot not found in this preset")
    _validate_slot(data)
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        if k in ("length", "emoji", "like_distribution") and v is not None:
            valid = {"length": _LENGTHS, "emoji": _EMOJIS, "like_distribution": _DISTRIBUTIONS}[k]
            if v not in valid:
                raise HTTPException(400, f"{k} must be one of {valid}")
        setattr(slot, k, v)
    db.commit()
    return {"id": slot.id, "ok": True}


@router.delete("/{preset_id}/slots/{slot_id}")
def delete_slot(preset_id: int, slot_id: int, db: Session = Depends(get_db)):
    slot = db.get(CommentTreeSlot, slot_id)
    if slot is None or slot.comment_preset_id != preset_id:
        raise HTTPException(404, "slot not found in this preset")
    db.delete(slot)
    db.commit()
    return {"deleted": slot_id}
