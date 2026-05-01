"""Feed / Alerts / Queue endpoints (PR-8b).

운영자 일상 80% 동선 (결과 확인) 지원. 기존 데이터 derived (lean — 신규 EventLog 테이블 X).
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import ActionLog, Brand, Campaign, Niche, Video, Account


router = APIRouter()


def _window_to_cutoff(window: str) -> datetime:
    now = datetime.now(UTC)
    return {
        "1h": now - timedelta(hours=1),
        "24h": now - timedelta(hours=24),
        "week": now - timedelta(days=7),
        "month": now - timedelta(days=30),
    }.get(window, now - timedelta(hours=24))


@router.get("/feed")
def get_feed(
    window: Literal["1h", "24h", "week", "month"] = "24h",
    brand_id: Optional[int] = None,
    niche_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """피드 — 댓글/영상 발견/캠페인 이벤트 시간순.

    같은 video_id 의 댓글들 묶음 (영상 단위 그룹핑은 frontend).
    """
    cutoff = _window_to_cutoff(window)
    events: list[dict] = []

    # 1. 댓글 / 답글
    actions_q = (
        db.query(ActionLog, Campaign)
        .outerjoin(Campaign, Campaign.id == ActionLog.campaign_id)
        .filter(
            ActionLog.created_at >= cutoff,
            ActionLog.action_type.in_(["comment", "reply"]),
        )
    )
    if niche_id is not None:
        actions_q = actions_q.filter(Campaign.niche_id == niche_id)
    elif brand_id is not None:
        actions_q = actions_q.filter(Campaign.brand_id == brand_id)
    for a, c in actions_q.order_by(ActionLog.created_at.desc()).limit(200).all():
        events.append({
            "at": a.created_at.isoformat() if a.created_at else None,
            "kind": "comment_posted",
            "actor": f"account:{a.account_id}",
            "video_id": a.video_id,
            "niche_id": c.niche_id if c else None,
            "campaign_id": a.campaign_id,
            "metadata": {
                "action_type": a.action_type,
                "is_promo": a.is_promo,
                "status": a.status,
                "content": (a.content or "")[:200],
                "youtube_comment_id": a.youtube_comment_id,
            },
        })

    # 2. 영상 발견
    videos_q = db.query(Video).filter(Video.collected_at >= cutoff)
    if niche_id is not None:
        videos_q = videos_q.filter(Video.niche_id == niche_id)
    elif brand_id is not None:
        # video → keyword → brand_id (간접)
        videos_q = videos_q.join(Niche, Niche.id == Video.niche_id).filter(
            Niche.brand_id == brand_id
        )
    for v in videos_q.order_by(Video.collected_at.desc()).limit(100).all():
        events.append({
            "at": v.collected_at.isoformat() if v.collected_at else None,
            "kind": "video_discovered",
            "actor": "system",
            "video_id": v.id,
            "niche_id": v.niche_id,
            "metadata": {
                "title": v.title,
                "channel": v.channel_title,
                "view_count": v.view_count,
                "discovered_via": v.discovered_via,
            },
        })

    # 3. 캠페인 생성
    cp_q = db.query(Campaign).filter(Campaign.created_at >= cutoff)
    if niche_id is not None:
        cp_q = cp_q.filter(Campaign.niche_id == niche_id)
    elif brand_id is not None:
        cp_q = cp_q.filter(Campaign.brand_id == brand_id)
    for c in cp_q.order_by(Campaign.created_at.desc()).limit(50).all():
        events.append({
            "at": c.created_at.isoformat() if c.created_at else None,
            "kind": "campaign_event",
            "actor": "operator",
            "video_id": c.video_id,
            "niche_id": c.niche_id,
            "campaign_id": c.id,
            "metadata": {"name": c.name, "scenario": c.scenario, "status": c.status},
        })

    events.sort(key=lambda e: e["at"] or "", reverse=True)
    return {"window": window, "events": events[:300]}


@router.get("/alerts")
def get_alerts(
    brand_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """문제 (빨간불). lean — 기존 신호로 derived.

    - blacklisted_video: Video.state='blacklisted' (최근 24h)
    - banned_worker: Account.status 변경 (최근 24h, 워커 차단 사유)
    """
    alerts: list[dict] = []
    cutoff = datetime.now(UTC) - timedelta(hours=24)

    # blacklisted videos (recent)
    blq = db.query(Video).filter(
        Video.state == "blacklisted",
        Video.collected_at >= cutoff,
    )
    if brand_id is not None:
        blq = blq.join(Niche, Niche.id == Video.niche_id).filter(
            Niche.brand_id == brand_id
        )
    for v in blq.order_by(Video.collected_at.desc()).limit(50).all():
        alerts.append({
            "id": f"blacklist:{v.id}",
            "kind": "blacklisted_video",
            "severity": "warn",
            "title": "영상 블랙리스트",
            "detail": f"{v.title or v.id} · 사유: {v.blacklist_reason or 'unknown'}",
            "related_link": f"/videos/{v.id}",
            "created_at": v.collected_at.isoformat() if v.collected_at else None,
        })

    # banned workers
    banned_q = db.query(Account).filter(Account.status == "banned")
    for a in banned_q.limit(20).all():
        alerts.append({
            "id": f"worker:{a.id}",
            "kind": "worker_banned",
            "severity": "critical",
            "title": "워커 차단",
            "detail": f"account:{a.id} 차단됨",
            "related_link": "/accounts",
            "created_at": None,
        })

    alerts.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    return {"total": len(alerts), "alerts": alerts}


@router.get("/queue")
def get_queue(
    window_hours: int = Query(default=24, ge=1, le=168),
    brand_id: Optional[int] = None,
    niche_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """예정 — 다음 N시간 안에 일어날 작업.

    Video.next_revisit_at 기반 (재방문 예정).
    """
    cutoff_top = datetime.now(UTC) + timedelta(hours=window_hours)
    items: list[dict] = []

    vq = db.query(Video).filter(
        Video.next_revisit_at.isnot(None),
        Video.next_revisit_at <= cutoff_top,
        Video.next_revisit_at >= datetime.now(UTC) - timedelta(hours=1),
    )
    if niche_id is not None:
        vq = vq.filter(Video.niche_id == niche_id)
    elif brand_id is not None:
        vq = vq.join(Niche, Niche.id == Video.niche_id).filter(
            Niche.brand_id == brand_id
        )
    for v in vq.order_by(Video.next_revisit_at.asc()).limit(100).all():
        items.append({
            "at": v.next_revisit_at.isoformat() if v.next_revisit_at else None,
            "kind": "revisit",
            "video_id": v.id,
            "niche_id": v.niche_id,
            "detail": f"{v.title or v.id} 재방문",
        })

    return {"window_hours": window_hours, "total": len(items), "items": items}
