"""Analytics — comment ranking, ghost rate, account performance.

Endpoints (admin-only via dependencies in app.py):
  GET  /api/analytics/comment-snapshots   list recent snapshots
  GET  /api/analytics/account-stability   per-account stability score
  GET  /api/analytics/ghost-rate          ghost-rate over time window
  GET  /api/analytics/ranking-summary     avg rank by brand/preset/persona
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from hydra.db.session import get_db
from hydra.db.models import Account, CommentSnapshot, Task

router = APIRouter()
UTC = timezone.utc


class SnapshotOut(BaseModel):
    id: int
    account_id: int
    gmail: Optional[str] = None
    video_id: str
    youtube_comment_id: str
    captured_at: datetime
    rank: Optional[int]
    like_count: int
    reply_count: int
    visible_to_third_party: bool
    is_held: bool
    is_deleted: bool


@router.get("/api/analytics/comment-snapshots")
def list_snapshots(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=500),
    account_id: Optional[int] = None,
    video_id: Optional[str] = None,
    days: int = Query(7, le=90),
):
    """Recent comment snapshots — ranking + visibility over time."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    q = db.query(CommentSnapshot).filter(CommentSnapshot.captured_at >= cutoff)
    if account_id:
        q = q.filter(CommentSnapshot.account_id == account_id)
    if video_id:
        q = q.filter(CommentSnapshot.video_id == video_id)
    rows = q.order_by(CommentSnapshot.captured_at.desc()).limit(limit).all()

    # Attach gmail (for display)
    acc_map = {a.id: a.gmail for a in db.query(Account).all()}
    items = []
    for r in rows:
        items.append(SnapshotOut(
            id=r.id, account_id=r.account_id, gmail=acc_map.get(r.account_id),
            video_id=r.video_id, youtube_comment_id=r.youtube_comment_id,
            captured_at=r.captured_at, rank=r.rank, like_count=r.like_count or 0,
            reply_count=r.reply_count or 0,
            visible_to_third_party=bool(r.visible_to_third_party),
            is_held=bool(r.is_held), is_deleted=bool(r.is_deleted),
        ))
    return {"items": items, "total": len(items)}


@router.get("/api/analytics/account-stability")
def account_stability(db: Session = Depends(get_db)):
    """Per-account stability score (warmup_scheduler.calc_stability_score)."""
    from hydra.services.warmup_scheduler import calc_stability_score
    accs = db.query(Account).all()
    out = []
    for a in accs:
        out.append({
            "id": a.id,
            "gmail": a.gmail,
            "status": a.status,
            "warmup_day": a.warmup_day or 0,
            "ghost_count": a.ghost_count or 0,
            "ipp_flagged": bool(a.ipp_flagged),
            "score": calc_stability_score(db, a.id),
        })
    return {"accounts": out, "total": len(out)}


@router.get("/api/analytics/ghost-rate")
def ghost_rate_summary(
    db: Session = Depends(get_db),
    days: int = Query(7, le=90),
):
    """Ghost rate over a window — held / total snapshots."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(CommentSnapshot)
        .filter(CommentSnapshot.captured_at >= cutoff)
        .all()
    )
    if not rows:
        return {"window_days": days, "total": 0, "held": 0, "deleted": 0, "ghost_rate": 0.0}
    held = sum(1 for r in rows if r.is_held)
    deleted = sum(1 for r in rows if r.is_deleted)
    ghost_rate = (held + deleted) / len(rows)
    return {
        "window_days": days,
        "total": len(rows),
        "held": held,
        "deleted": deleted,
        "ghost_rate": round(ghost_rate, 3),
    }


@router.get("/api/analytics/ranking-summary")
def ranking_summary(
    db: Session = Depends(get_db),
    days: int = Query(7, le=90),
):
    """Average comment rank — coarse measure of 'top comment' effectiveness."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(CommentSnapshot)
        .filter(
            CommentSnapshot.captured_at >= cutoff,
            CommentSnapshot.rank.isnot(None),
        )
        .all()
    )
    if not rows:
        return {"window_days": days, "samples": 0, "avg_rank": None, "top10_rate": 0.0}
    avg_rank = sum(r.rank for r in rows) / len(rows)
    top10_rate = sum(1 for r in rows if r.rank and r.rank <= 10) / len(rows)
    return {
        "window_days": days,
        "samples": len(rows),
        "avg_rank": round(avg_rank, 2),
        "top10_rate": round(top10_rate, 3),
    }
