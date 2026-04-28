"""Keyword management API."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import Keyword

router = APIRouter()


class KeywordCreate(BaseModel):
    text: str
    brand_id: int
    priority: int = 5


@router.get("/api/list")
def list_keywords(
    status: str | None = None,
    brand_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Keyword)
    if status:
        query = query.filter(Keyword.status == status)
    if brand_id:
        query = query.filter(Keyword.brand_id == brand_id)

    return [
        {
            "id": k.id, "text": k.text, "brand_id": k.brand_id,
            "source": k.source, "status": k.status, "priority": k.priority,
            "total_videos_found": k.total_videos_found,
            "comments_posted": k.total_comments_posted,
            "is_variant": bool(k.is_variant),
            "parent_keyword_id": k.parent_keyword_id,
            "is_negative": bool(k.is_negative),
            "poll_5min": bool(k.poll_5min),
            "poll_30min": bool(k.poll_30min),
            "poll_daily": bool(k.poll_daily),
            "keyword_tier": k.keyword_tier or "core",
        }
        for k in query.all()
    ]


@router.post("/api/create")
def create_keyword(data: KeywordCreate, db: Session = Depends(get_db)):
    kw = Keyword(text=data.text, brand_id=data.brand_id, priority=data.priority)
    db.add(kw)
    db.commit()
    return {"id": kw.id, "text": kw.text}


@router.post("/api/{keyword_id}/exclude")
def exclude_keyword(keyword_id: int, db: Session = Depends(get_db)):
    kw = db.query(Keyword).get(keyword_id)
    if not kw:
        return {"error": "not found"}
    kw.status = "excluded"
    db.commit()
    return {"ok": True}


@router.post("/api/{keyword_id}/expand")
def expand_keyword(keyword_id: int, db: Session = Depends(get_db)):
    """Auto-expand keyword using Claude."""
    from hydra.ai.agents.keyword_agent import expand_keywords
    kw = db.query(Keyword).get(keyword_id)
    if not kw:
        return {"error": "not found"}
    try:
        new_kws = expand_keywords(db, kw)
        return {"ok": True, "count": len(new_kws), "keywords": [k.text for k in new_kws]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/{keyword_id}/activate")
def activate_keyword(keyword_id: int, db: Session = Depends(get_db)):
    kw = db.query(Keyword).get(keyword_id)
    if not kw:
        return {"error": "not found"}
    kw.status = "active"
    db.commit()
    return {"ok": True}


@router.post("/api/{keyword_id}/pause")
def pause_keyword(keyword_id: int, db: Session = Depends(get_db)):
    kw = db.query(Keyword).get(keyword_id)
    if not kw:
        return {"error": "not found"}
    kw.status = "paused"
    db.commit()
    return {"ok": True}


class KeywordFieldUpdate(BaseModel):
    field: str
    value: bool | str | int


@router.post("/api/{keyword_id}/update-field")
def update_field(keyword_id: int, data: KeywordFieldUpdate, db: Session = Depends(get_db)):
    """Phase 1: poll_5min/poll_30min/poll_daily/is_negative 등 토글."""
    kw = db.query(Keyword).get(keyword_id)
    if not kw:
        return {"error": "not found"}
    allowed = {"poll_5min", "poll_30min", "poll_daily", "is_negative", "status", "keyword_tier"}
    if data.field not in allowed:
        return {"error": f"field {data.field} not allowed"}
    setattr(kw, data.field, data.value)
    db.commit()
    return {"ok": True, "field": data.field, "value": data.value}


@router.post("/api/{keyword_id}/delete")
def delete_keyword(keyword_id: int, db: Session = Depends(get_db)):
    """키워드 soft-delete (status='excluded'). 영상/매칭 기록은 유지."""
    kw = db.query(Keyword).get(keyword_id)
    if not kw:
        return {"error": "not found"}
    kw.status = "excluded"
    db.commit()
    return {"ok": True}
