"""어드민 감사 로그 조회 (Task 39.5).

쓰기는 AuditLogMiddleware 가 자동으로 수행 — 여기는 조회 전용.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc

from hydra.db import session as _db_session
from hydra.db.models import AuditLog
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()


class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    target_type: Optional[str]
    target_id: Optional[int]
    metadata: Optional[dict]
    ip_address: Optional[str]
    user_agent: Optional[str]
    timestamp: datetime


class AuditListResponse(BaseModel):
    items: list[AuditLogOut]
    total: int
    limit: int
    offset: int


def _to_out(row: AuditLog) -> AuditLogOut:
    meta = None
    if row.metadata_json:
        try:
            meta = json.loads(row.metadata_json)
        except json.JSONDecodeError:
            meta = {"raw": row.metadata_json}
    return AuditLogOut(
        id=row.id,
        user_id=row.user_id,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        metadata=meta,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        timestamp=row.timestamp,
    )


@router.get("/list", response_model=AuditListResponse)
def list_audit(
    _session: dict = Depends(admin_session),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None, description="완전 일치 (예: deploy, login)"),
    user_id: Optional[int] = Query(None),
    since: Optional[datetime] = Query(None, description="ISO8601, 이 시각 이후"),
    until: Optional[datetime] = Query(None, description="ISO8601, 이 시각 이전"),
) -> AuditListResponse:
    db = _db_session.SessionLocal()
    try:
        q = db.query(AuditLog)
        if action:
            q = q.filter(AuditLog.action == action)
        if user_id is not None:
            q = q.filter(AuditLog.user_id == user_id)
        if since is not None:
            q = q.filter(AuditLog.timestamp >= since)
        if until is not None:
            q = q.filter(AuditLog.timestamp <= until)

        total = q.count()
        rows = (
            q.order_by(desc(AuditLog.timestamp))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return AuditListResponse(
            items=[_to_out(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )
    finally:
        db.close()
