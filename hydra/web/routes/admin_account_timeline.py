"""Phase 3.2 — Account timeline 조회.

운영자가 한 계정 클릭하면 최근 events 한눈에. 운영자 메모(note) append 도 지원.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc

from hydra.db import session as _db_session
from hydra.db.models import Account, AccountEvent
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()


class TimelineItem(BaseModel):
    id: int
    event_type: str
    message: str
    screen_state: str | None
    failure_taxonomy: str | None
    task_id: int | None
    worker_id: int | None
    context: dict | None
    created_at: datetime


class NoteRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    context: dict | None = None


@router.get("/{account_id}/timeline", response_model=list[TimelineItem])
def get_account_timeline(
    account_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    days: int = Query(default=30, ge=1, le=180),
    event_type: str | None = Query(default=None),
    _user=Depends(admin_session),
) -> list[TimelineItem]:
    db = _db_session.SessionLocal()
    try:
        if db.get(Account, account_id) is None:
            raise HTTPException(404, f"account {account_id} not found")
        cutoff = datetime.now(UTC) - timedelta(days=days)
        q = (
            db.query(AccountEvent)
            .filter(AccountEvent.account_id == account_id)
            .filter(AccountEvent.created_at >= cutoff)
        )
        if event_type:
            q = q.filter(AccountEvent.event_type == event_type)
        rows = q.order_by(desc(AccountEvent.created_at)).limit(limit).all()
        out = []
        for r in rows:
            ctx = None
            if r.context:
                try:
                    ctx = json.loads(r.context)
                except Exception:
                    pass
            out.append(TimelineItem(
                id=r.id,
                event_type=r.event_type,
                message=r.message,
                screen_state=r.screen_state,
                failure_taxonomy=r.failure_taxonomy,
                task_id=r.task_id,
                worker_id=r.worker_id,
                context=ctx,
                created_at=r.created_at,
            ))
        return out
    finally:
        db.close()


@router.post("/{account_id}/note", response_model=TimelineItem)
def append_note(
    account_id: int,
    req: NoteRequest,
    _user=Depends(admin_session),
) -> TimelineItem:
    """운영자가 계정에 메모 1줄 append (event_type='note')."""
    db = _db_session.SessionLocal()
    try:
        if db.get(Account, account_id) is None:
            raise HTTPException(404, f"account {account_id} not found")
        ev = AccountEvent(
            account_id=account_id,
            event_type="note",
            message=req.message,
            context=json.dumps(req.context, ensure_ascii=False) if req.context else None,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        return TimelineItem(
            id=ev.id,
            event_type=ev.event_type,
            message=ev.message,
            screen_state=ev.screen_state,
            failure_taxonomy=ev.failure_taxonomy,
            task_id=ev.task_id,
            worker_id=ev.worker_id,
            context=req.context,
            created_at=ev.created_at,
        )
    finally:
        db.close()
