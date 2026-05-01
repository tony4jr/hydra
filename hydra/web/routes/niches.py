"""Niche CRUD API — PR-3b.

Niche = Brand 의 시장 정의 + 정책 (1:N).
PR-3a 에서 default Niche 1:1 백필 완료.
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import ActionLog, Brand, Campaign, Keyword, Niche, Video


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


# ─── PR-4b: Overview ────────────────────────────────────────────


@router.get("/{niche_id}/overview")
def niche_overview(niche_id: int, db: Session = Depends(get_db)):
    """시장 개요 — 5탭 중 첫 번째.

    spec PR-4 §1: niche + stats + active_campaigns (max 3) + recent_alerts.
    recent_alerts 는 PR-4 후속 sub-PR 또는 별도 alert 시스템 도입 시 채움
    (현재는 빈 리스트, 운영 시그널 소스 미정).
    """
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")

    keywords_count = (
        db.query(func.count(Keyword.id))
        .filter(Keyword.niche_id == niche_id)
        .scalar()
        or 0
    )
    video_pool_size = (
        db.query(func.count(Video.id))
        .filter(Video.niche_id == niche_id)
        .scalar()
        or 0
    )
    active_campaigns_count = (
        db.query(func.count(Campaign.id))
        .filter(Campaign.niche_id == niche_id, Campaign.status == "active")
        .scalar()
        or 0
    )

    cutoff_7d = datetime.now(UTC) - timedelta(days=7)
    # ActionLog.campaign_id 는 plain int (FK constraint 없음) — explicit join 조건으로 매핑.
    comments_7d = (
        db.query(func.count(ActionLog.id))
        .join(Campaign, Campaign.id == ActionLog.campaign_id)
        .filter(
            Campaign.niche_id == niche_id,
            ActionLog.action_type.in_(["comment", "reply"]),
            ActionLog.created_at >= cutoff_7d,
        )
        .scalar()
        or 0
    )

    active_campaigns_rows = (
        db.query(Campaign)
        .filter(Campaign.niche_id == niche_id, Campaign.status == "active")
        .order_by(Campaign.created_at.desc())
        .limit(3)
        .all()
    )
    active_campaigns = [
        {
            "id": c.id,
            "name": c.name,
            "scenario": c.scenario,
            "status": c.status,
            "target_count": c.target_count,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "end_date": c.end_date.isoformat() if c.end_date else None,
        }
        for c in active_campaigns_rows
    ]

    return {
        "niche": _serialize(n),
        "stats": {
            "video_pool_size": video_pool_size,
            "keywords_count": keywords_count,
            "active_campaigns": active_campaigns_count,
            "comments_7d": comments_7d,
        },
        "active_campaigns": active_campaigns,
        "recent_alerts": [],
    }


# ─── PR-4c: 수집 탭 — flow / keywords / recent-videos ───────────────


_DEFAULT_FLOW_THRESHOLD = 0.65


@router.get("/{niche_id}/collection/flow")
def niche_collection_flow(
    niche_id: int,
    window_hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """5단계 깔때기 — niche 단위.

    spec PR-4 §2: discovered → market_fit → task_created → comment_posted → survived_24h.
    PR-4c 는 niche_id 필터 적용한 lean 버전 (niche.embedding_threshold 기준).
    """
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")

    threshold = n.embedding_threshold or _DEFAULT_FLOW_THRESHOLD
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)

    discovered = (
        db.query(func.count(Video.id))
        .filter(Video.niche_id == niche_id, Video.collected_at >= cutoff)
        .scalar()
        or 0
    )
    market_fit = (
        db.query(func.count(Video.id))
        .filter(
            Video.niche_id == niche_id,
            Video.collected_at >= cutoff,
            Video.embedding_score >= threshold,
        )
        .scalar()
        or 0
    )
    in_pool = (
        db.query(func.count(Video.id))
        .filter(
            Video.niche_id == niche_id,
            Video.collected_at >= cutoff,
            Video.state == "active",
        )
        .scalar()
        or 0
    )
    comment_posted = (
        db.query(func.count(ActionLog.id))
        .join(Campaign, Campaign.id == ActionLog.campaign_id)
        .filter(
            Campaign.niche_id == niche_id,
            ActionLog.action_type.in_(["comment", "reply"]),
            ActionLog.created_at >= cutoff,
        )
        .scalar()
        or 0
    )

    def _rate(prev, cur):
        return (cur / prev) if prev > 0 else None

    stages = [
        {"stage": "discovered", "count": discovered, "pass_rate": None},
        {"stage": "market_fit", "count": market_fit, "pass_rate": _rate(discovered, market_fit)},
        {"stage": "in_pool", "count": in_pool, "pass_rate": _rate(market_fit, in_pool)},
        {"stage": "comment_posted", "count": comment_posted, "pass_rate": _rate(in_pool, comment_posted)},
    ]
    for s in stages:
        s["is_bottleneck"] = s["pass_rate"] is not None and s["pass_rate"] < 0.30

    return {
        "window_hours": window_hours,
        "threshold": threshold,
        "stages": stages,
    }


@router.get("/{niche_id}/keywords")
def niche_keywords(niche_id: int, db: Session = Depends(get_db)):
    """Niche 의 키워드 리스트 + 7일 매트릭."""
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")

    cutoff_7d = datetime.now(UTC) - timedelta(days=7)
    rows = (
        db.query(Keyword)
        .filter(Keyword.niche_id == niche_id, Keyword.status != "excluded")
        .order_by(Keyword.is_variant.asc(), Keyword.id.asc())
        .all()
    )

    out = []
    for kw in rows:
        if kw.is_variant:
            continue
        variants = [v for v in rows if v.parent_keyword_id == kw.id]
        discovered = (
            db.query(func.count(Video.id))
            .filter(Video.keyword_id == kw.id, Video.collected_at >= cutoff_7d)
            .scalar()
            or 0
        )
        passed_market = (
            db.query(func.count(Video.id))
            .filter(
                Video.keyword_id == kw.id,
                Video.collected_at >= cutoff_7d,
                Video.embedding_score >= (n.embedding_threshold or _DEFAULT_FLOW_THRESHOLD),
            )
            .scalar()
            or 0
        )
        polling = (
            "5min" if kw.poll_5min else "30min" if kw.poll_30min else "daily"
        )
        out.append(
            {
                "id": kw.id,
                "text": kw.text,
                "kind": "negative" if kw.is_negative else "positive",
                "polling": polling,
                "status": kw.status,
                "tier": kw.keyword_tier,
                "variations": [
                    {"id": v.id, "text": v.text, "status": v.status}
                    for v in variants
                ],
                "metrics_7d": {
                    "discovered": discovered,
                    "passed_market": passed_market,
                    "pass_rate": (passed_market / discovered) if discovered > 0 else None,
                },
            }
        )
    return out


class KeywordCreate(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    is_negative: bool = False
    polling: str = "daily"

    @field_validator("polling")
    @classmethod
    def _polling(cls, v: str) -> str:
        if v not in {"5min", "30min", "daily"}:
            raise ValueError("polling must be 5min|30min|daily")
        return v


class KeywordUpdate(BaseModel):
    polling: Optional[str] = None
    status: Optional[str] = None

    @field_validator("polling")
    @classmethod
    def _polling(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"5min", "30min", "daily"}:
            raise ValueError("polling must be 5min|30min|daily")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"active", "paused", "excluded"}:
            raise ValueError("status must be active|paused|excluded")
        return v


@router.post("/{niche_id}/keywords")
def create_niche_keyword(niche_id: int, data: KeywordCreate, db: Session = Depends(get_db)):
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")
    kw = Keyword(
        text=data.text,
        brand_id=n.brand_id,
        niche_id=niche_id,
        is_negative=data.is_negative,
        poll_5min=(data.polling == "5min"),
        poll_30min=(data.polling == "30min"),
        poll_daily=(data.polling == "daily"),
        source="manual",
        status="active",
    )
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return {"id": kw.id, "text": kw.text, "polling": data.polling}


@router.patch("/{niche_id}/keywords/{kw_id}")
def update_niche_keyword(
    niche_id: int, kw_id: int, data: KeywordUpdate, db: Session = Depends(get_db)
):
    kw = db.get(Keyword, kw_id)
    if kw is None or kw.niche_id != niche_id:
        raise HTTPException(404, "keyword not found in this niche")
    if data.polling is not None:
        kw.poll_5min = data.polling == "5min"
        kw.poll_30min = data.polling == "30min"
        kw.poll_daily = data.polling == "daily"
    if data.status is not None:
        kw.status = data.status
    db.commit()
    return {"id": kw.id, "ok": True}


@router.delete("/{niche_id}/keywords/{kw_id}")
def delete_niche_keyword(niche_id: int, kw_id: int, db: Session = Depends(get_db)):
    kw = db.get(Keyword, kw_id)
    if kw is None or kw.niche_id != niche_id:
        raise HTTPException(404, "keyword not found in this niche")
    kw.status = "excluded"
    db.commit()
    return {"id": kw_id, "deleted": True, "mode": "soft"}


@router.get("/{niche_id}/recent-videos")
def niche_recent_videos(
    niche_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """최근 발견 영상 + 통과/탈락 사유.

    result 매핑: state='blacklisted' + blacklist_reason → rejected_*,
    state='active'/'pending' → passed.
    """
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")

    rows = (
        db.query(Video)
        .filter(Video.niche_id == niche_id)
        .order_by(Video.collected_at.desc())
        .limit(limit)
        .all()
    )

    def _result(v: Video) -> tuple[str, Optional[str]]:
        if v.state == "blacklisted":
            reason = (v.blacklist_reason or "").lower()
            if reason.startswith("low_relevance"):
                return "rejected_market", v.blacklist_reason
            if reason.startswith("hard_block") or reason in {
                "comments_disabled", "too_short", "kids_category", "live_streaming"
            } or reason.startswith("too_short_"):
                return "rejected_hard_block", v.blacklist_reason
            return "rejected_other", v.blacklist_reason
        return "passed", None

    out = []
    for v in rows:
        result, reason = _result(v)
        out.append(
            {
                "video_id": v.id,
                "title": v.title,
                "channel": v.channel_title,
                "view_count": v.view_count,
                "url": v.url,
                "keyword_matched": v.discovery_keyword,
                "market_fitness": v.embedding_score,
                "result": result,
                "result_reason": reason,
                "collected_at": v.collected_at.isoformat() if v.collected_at else None,
            }
        )
    return out


# ─── PR-4d: 메시지 탭 ────────────────────────────────────────────


def _json_load(s: Optional[str], default):
    if not s:
        return default
    import json
    try:
        return json.loads(s)
    except Exception:
        return default


def _json_dump(v) -> Optional[str]:
    import json
    return json.dumps(v, ensure_ascii=False) if v is not None else None


class NichePersona(BaseModel):
    id: str  # client-generated 또는 uuid
    name: str = Field(min_length=1, max_length=80)
    weight: int = Field(default=1, ge=1, le=100)  # 비율
    description: Optional[str] = None
    age_range: Optional[str] = None
    gender: Optional[str] = None


class NicheMessagingUpdate(BaseModel):
    core_message: Optional[str] = None
    tone_guide: Optional[str] = None
    target_audience: Optional[str] = None
    mention_rules: Optional[str] = None
    promotional_keywords: Optional[list[str]] = None
    preset_selection: Optional[list[str]] = None


@router.get("/{niche_id}/messaging")
def get_niche_messaging(niche_id: int, db: Session = Depends(get_db)):
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")
    return {
        "niche_id": n.id,
        "core_message": n.core_message,
        "tone_guide": n.tone_guide,
        "target_audience": n.target_audience,
        "mention_rules": n.mention_rules,
        "promotional_keywords": _json_load(n.promotional_keywords, []),
        "preset_selection": _json_load(n.preset_selection, []),
        "personas": _json_load(n.personas_json, []),
    }


@router.patch("/{niche_id}/messaging")
def update_niche_messaging(
    niche_id: int, data: NicheMessagingUpdate, db: Session = Depends(get_db)
):
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")
    payload = data.model_dump(exclude_unset=True)
    if "promotional_keywords" in payload:
        n.promotional_keywords = _json_dump(payload.pop("promotional_keywords"))
    if "preset_selection" in payload:
        n.preset_selection = _json_dump(payload.pop("preset_selection"))
    for k, v in payload.items():
        setattr(n, k, v)
    db.commit()
    return {"ok": True}


@router.post("/{niche_id}/personas")
def add_niche_persona(niche_id: int, persona: NichePersona, db: Session = Depends(get_db)):
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")
    personas = _json_load(n.personas_json, [])
    if len(personas) >= 10:
        raise HTTPException(409, "max 10 personas per niche")
    if any(p.get("id") == persona.id for p in personas):
        raise HTTPException(409, f"persona id {persona.id} already exists")
    personas.append(persona.model_dump())
    n.personas_json = _json_dump(personas)
    db.commit()
    return {"ok": True, "personas": personas}


@router.delete("/{niche_id}/personas/{persona_id}")
def delete_niche_persona(niche_id: int, persona_id: str, db: Session = Depends(get_db)):
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")
    personas = _json_load(n.personas_json, [])
    new_list = [p for p in personas if p.get("id") != persona_id]
    if len(new_list) == len(personas):
        raise HTTPException(404, f"persona {persona_id} not found")
    n.personas_json = _json_dump(new_list)
    db.commit()
    return {"ok": True, "personas": new_list}


# ─── PR-4e: 캠페인 탭 ────────────────────────────────────────────


@router.get("/{niche_id}/campaigns")
def niche_campaigns(
    niche_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Niche 단위 캠페인 리스트 (niche 컨텍스트 강제)."""
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")

    q = db.query(Campaign).filter(Campaign.niche_id == niche_id)
    if status:
        q = q.filter(Campaign.status == status)
    rows = q.order_by(Campaign.created_at.desc()).limit(200).all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "scenario": c.scenario,
            "status": c.status,
            "campaign_type": c.campaign_type,
            "comment_mode": c.comment_mode,
            "target_count": c.target_count,
            "duration_days": c.duration_days,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        }
        for c in rows
    ]


# ─── PR-4f: 분석 탭 ──────────────────────────────────────────────


@router.get("/{niche_id}/analytics")
def niche_analytics(
    niche_id: int,
    window_days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """Niche 분석 (lean — 기존 데이터 niche 필터링).

    spec PR-4 §5: daily_workload / campaign_performance / persona / preset / hourly /
    ranking_summary. 본 sub-PR 은 daily_workload + campaign_performance + hourly_pattern +
    ranking_summary 우선 구현. persona/preset performance 는 PR-4f-followup
    (Niche.personas_json/preset_selection 운용 후).
    """
    n = db.get(Niche, niche_id)
    if n is None:
        raise HTTPException(404, "niche not found")

    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    # daily_workload (date 별 댓글 수)
    rows = (
        db.query(
            func.date(ActionLog.created_at).label("d"),
            func.count(ActionLog.id).label("n"),
        )
        .join(Campaign, Campaign.id == ActionLog.campaign_id)
        .filter(
            Campaign.niche_id == niche_id,
            ActionLog.created_at >= cutoff,
            ActionLog.action_type.in_(["comment", "reply"]),
        )
        .group_by("d")
        .order_by("d")
        .all()
    )
    daily_workload = [{"date": str(r.d), "comments": int(r.n)} for r in rows]

    # campaign_performance (캠페인 별 댓글 수)
    cp_rows = (
        db.query(
            Campaign.id, Campaign.name, Campaign.status,
            func.count(ActionLog.id).label("n"),
        )
        .outerjoin(ActionLog, (ActionLog.campaign_id == Campaign.id) & (
            ActionLog.created_at >= cutoff
        ) & (ActionLog.action_type.in_(["comment", "reply"])))
        .filter(Campaign.niche_id == niche_id)
        .group_by(Campaign.id, Campaign.name, Campaign.status)
        .all()
    )
    campaign_performance = [
        {
            "campaign_id": r.id,
            "name": r.name,
            "status": r.status,
            "comments": int(r.n or 0),
        }
        for r in cp_rows
    ]

    # hourly_pattern (시간대 분포)
    hour_rows = (
        db.query(
            func.extract("hour", ActionLog.created_at).label("h"),
            func.count(ActionLog.id).label("n"),
        )
        .join(Campaign, Campaign.id == ActionLog.campaign_id)
        .filter(
            Campaign.niche_id == niche_id,
            ActionLog.created_at >= cutoff,
            ActionLog.action_type.in_(["comment", "reply"]),
        )
        .group_by("h")
        .order_by("h")
        .all()
    )
    hourly_pattern = [{"hour": int(r.h), "comments": int(r.n)} for r in hour_rows]

    # ranking_summary (간단 베스트 캠페인)
    best = max(campaign_performance, key=lambda x: x["comments"], default=None)
    ranking_summary = (
        {"best_campaign_id": best["campaign_id"], "best_comments": best["comments"]}
        if best and best["comments"] > 0
        else {"best_campaign_id": None, "best_comments": 0}
    )

    return {
        "window_days": window_days,
        "daily_workload": daily_workload,
        "campaign_performance": campaign_performance,
        "persona_performance": [],
        "preset_performance": [],
        "hourly_pattern": hourly_pattern,
        "ranking_summary": ranking_summary,
    }
