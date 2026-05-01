"""Favorites + protected videos (PR-8h)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import (
    Brand, FavoriteChannel, FavoriteVideo, ProtectedVideo, Video,
)


router = APIRouter()


class FavChannelCreate(BaseModel):
    brand_id: int
    channel_id: str
    channel_title: Optional[str] = None
    note: Optional[str] = None


class FavVideoCreate(BaseModel):
    brand_id: int
    video_id: str
    note: Optional[str] = None


class ProtectedCreate(BaseModel):
    brand_id: int
    video_id: str
    reason: Optional[str] = None


# ─── Favorite Channels ────────────────────────────────────────────


@router.get("/channels")
def list_fav_channels(brand_id: int = Query(...), db: Session = Depends(get_db)):
    rows = db.query(FavoriteChannel).filter(
        FavoriteChannel.brand_id == brand_id
    ).order_by(FavoriteChannel.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "channel_id": r.channel_id,
            "channel_title": r.channel_title,
            "note": r.note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/channels")
def add_fav_channel(data: FavChannelCreate, db: Session = Depends(get_db)):
    if not db.get(Brand, data.brand_id):
        raise HTTPException(404, "brand not found")
    existing = db.query(FavoriteChannel).filter(
        FavoriteChannel.brand_id == data.brand_id,
        FavoriteChannel.channel_id == data.channel_id,
    ).first()
    if existing:
        return {"id": existing.id, "already": True}
    fav = FavoriteChannel(
        brand_id=data.brand_id, channel_id=data.channel_id,
        channel_title=data.channel_title, note=data.note,
    )
    db.add(fav)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "conflict")
    db.refresh(fav)
    return {"id": fav.id}


@router.delete("/channels/{fav_id}")
def remove_fav_channel(fav_id: int, db: Session = Depends(get_db)):
    fav = db.get(FavoriteChannel, fav_id)
    if fav is None:
        raise HTTPException(404, "not found")
    db.delete(fav)
    db.commit()
    return {"deleted": fav_id}


# ─── Favorite Videos ──────────────────────────────────────────────


@router.get("/videos")
def list_fav_videos(brand_id: int = Query(...), db: Session = Depends(get_db)):
    rows = db.query(FavoriteVideo).filter(
        FavoriteVideo.brand_id == brand_id
    ).order_by(FavoriteVideo.created_at.desc()).all()
    return [
        {
            "id": r.id, "video_id": r.video_id, "note": r.note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/videos")
def add_fav_video(data: FavVideoCreate, db: Session = Depends(get_db)):
    if not db.get(Brand, data.brand_id):
        raise HTTPException(404, "brand not found")
    if not db.get(Video, data.video_id):
        raise HTTPException(404, "video not found")
    existing = db.query(FavoriteVideo).filter(
        FavoriteVideo.brand_id == data.brand_id,
        FavoriteVideo.video_id == data.video_id,
    ).first()
    if existing:
        return {"id": existing.id, "already": True}
    fav = FavoriteVideo(brand_id=data.brand_id, video_id=data.video_id, note=data.note)
    db.add(fav)
    db.commit()
    db.refresh(fav)
    return {"id": fav.id}


@router.delete("/videos/{fav_id}")
def remove_fav_video(fav_id: int, db: Session = Depends(get_db)):
    fav = db.get(FavoriteVideo, fav_id)
    if fav is None:
        raise HTTPException(404, "not found")
    db.delete(fav)
    db.commit()
    return {"deleted": fav_id}


# ─── Protected Videos ─────────────────────────────────────────────


@router.get("/protected")
def list_protected(brand_id: int = Query(...), db: Session = Depends(get_db)):
    rows = db.query(ProtectedVideo).filter(
        ProtectedVideo.brand_id == brand_id
    ).order_by(ProtectedVideo.created_at.desc()).all()
    return [
        {
            "id": r.id, "video_id": r.video_id, "reason": r.reason,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/protected")
def add_protected(data: ProtectedCreate, db: Session = Depends(get_db)):
    if not db.get(Brand, data.brand_id):
        raise HTTPException(404, "brand not found")
    if not db.get(Video, data.video_id):
        raise HTTPException(404, "video not found")
    existing = db.query(ProtectedVideo).filter(
        ProtectedVideo.brand_id == data.brand_id,
        ProtectedVideo.video_id == data.video_id,
    ).first()
    if existing:
        return {"id": existing.id, "already": True}
    p = ProtectedVideo(brand_id=data.brand_id, video_id=data.video_id, reason=data.reason)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id}


@router.delete("/protected/{prot_id}")
def remove_protected(prot_id: int, db: Session = Depends(get_db)):
    p = db.get(ProtectedVideo, prot_id)
    if p is None:
        raise HTTPException(404, "not found")
    db.delete(p)
    db.commit()
    return {"deleted": prot_id}
