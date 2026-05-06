"""어드민 — YouTube Data API v3 키 풀 관리."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from hydra.collection.youtube_keys import list_for_admin
from hydra.db.models import YouTubeApiKey
from hydra.db.session import get_db

router = APIRouter()


class CreateKeyInput(BaseModel):
    key: str = Field(..., min_length=10)
    label: str | None = None
    quota_limit: int = 10000


class PatchKeyInput(BaseModel):
    label: str | None = None
    status: str | None = None  # active | disabled
    quota_limit: int | None = None


@router.get("")
def list_keys(db: Session = Depends(get_db)):
    return {"keys": list_for_admin(db)}


@router.post("")
def create_key(data: CreateKeyInput, db: Session = Depends(get_db)):
    raw = data.key.strip()
    exists = db.query(YouTubeApiKey).filter(YouTubeApiKey.key == raw).first()
    if exists:
        raise HTTPException(status_code=409, detail="이미 등록된 키입니다")

    row = YouTubeApiKey(
        key=raw,
        label=data.label,
        status="active",
        quota_used_today=0,
        quota_limit=data.quota_limit,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id}


@router.patch("/{key_id}")
def patch_key(key_id: int, data: PatchKeyInput, db: Session = Depends(get_db)):
    row = db.query(YouTubeApiKey).filter(YouTubeApiKey.id == key_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="키를 찾을 수 없습니다")
    if data.label is not None:
        row.label = data.label
    if data.status is not None:
        if data.status not in {"active", "disabled"}:
            raise HTTPException(status_code=400, detail="status 는 active|disabled")
        row.status = data.status
    if data.quota_limit is not None:
        row.quota_limit = data.quota_limit
    db.commit()
    return {"ok": True}


@router.delete("/{key_id}")
def delete_key(key_id: int, db: Session = Depends(get_db)):
    row = db.query(YouTubeApiKey).filter(YouTubeApiKey.id == key_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="키를 찾을 수 없습니다")
    db.delete(row)
    db.commit()
    return {"ok": True}
