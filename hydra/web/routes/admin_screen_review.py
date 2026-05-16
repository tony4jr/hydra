"""Phase 3.2 — Admin Screen Review API.

UNKNOWN_SCREEN 캡처본 list + 운영자 라벨링 → ScreenResolution 생성.
워커가 다음 같은 화면 만나면 lookup 으로 자동 처리 (Phase 3 worker-side, 후속 PR).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_

from hydra.db import session as _db_session
from hydra.db.models import WorkerError, ScreenResolution
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()


class UnknownScreenItem(BaseModel):
    id: int
    worker_id: int
    screen_state: str | None
    failure_taxonomy: str | None
    message: str
    captured_url: str | None
    captured_title: str | None
    screenshot_url: str | None
    context: dict | None
    received_at: datetime


class LabelRequest(BaseModel):
    screen_state: str = Field(..., min_length=1, max_length=64)
    resolution_type: str = Field(..., min_length=1, max_length=32)
    # 'auto_click_skip' / 'auto_enter_code' / 'escalate_manual' / 'fail_task' / 'retry_after_cooldown'
    url_pattern: str | None = None
    title_pattern: str | None = None
    dom_signature: str | None = None
    action_config: dict | None = None
    approved: bool = False
    notes: str | None = None


class LabelResponse(BaseModel):
    ok: bool
    resolution_id: int


@router.get("/list", response_model=list[UnknownScreenItem])
def list_unknown_screens(
    limit: int = Query(default=50, ge=1, le=500),
    hours: int = Query(default=72, ge=1, le=720),
    only_unresolved: bool = Query(default=True),
    _user=Depends(admin_session),
) -> list[UnknownScreenItem]:
    """worker_errors where kind='unknown_screen' (and 옵션: 아직 resolution 없는 것).

    only_unresolved=True 일 때 filter 후 limit (Codex P2 fix). limit 후 filter 면
    최신 N 개가 모두 라벨링된 경우 큐가 비어 보이지만 실은 오래된 미라벨 존재.
    """
    db = _db_session.SessionLocal()
    try:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        q = (
            db.query(WorkerError)
            .filter(WorkerError.kind == "unknown_screen")
            .filter(WorkerError.received_at >= cutoff)
        )
        if only_unresolved:
            # NOT EXISTS — 이미 라벨된 worker_error 제외 (limit 전에 적용)
            labeled_ids = db.query(ScreenResolution.source_error_id).filter(
                ScreenResolution.source_error_id.isnot(None)
            )
            q = q.filter(~WorkerError.id.in_(labeled_ids))
        rows = q.order_by(desc(WorkerError.received_at)).limit(limit).all()
        result = []
        for r in rows:
            ctx = None
            if r.context:
                try:
                    ctx = json.loads(r.context)
                except Exception:
                    pass
            result.append(UnknownScreenItem(
                id=r.id,
                worker_id=r.worker_id,
                screen_state=r.screen_state,
                failure_taxonomy=r.failure_taxonomy,
                message=r.message,
                captured_url=r.captured_url,
                captured_title=r.captured_title,
                screenshot_url=r.screenshot_url,
                context=ctx,
                received_at=r.received_at,
            ))
        return result
    finally:
        db.close()


@router.post("/{error_id}/label", response_model=LabelResponse)
def label_unknown_screen(
    error_id: int,
    req: LabelRequest,
    _user=Depends(admin_session),
) -> LabelResponse:
    """UNKNOWN_SCREEN 1건을 운영자가 라벨링 → ScreenResolution 1행 생성.

    같은 dom_signature/url_pattern 의 화면이 다음에 나타나면 워커가 lookup 으로
    자동 처리 (별도 PR — worker-side resolution lookup).
    """
    db = _db_session.SessionLocal()
    try:
        err = db.get(WorkerError, error_id)
        if err is None:
            raise HTTPException(404, f"worker_error {error_id} not found")
        if err.kind != "unknown_screen":
            raise HTTPException(400, f"worker_error {error_id} is not unknown_screen (kind={err.kind})")

        # 유효한 resolution_type 검증
        valid_types = {
            "auto_click_skip", "auto_enter_code", "escalate_manual",
            "fail_task", "retry_after_cooldown",
        }
        if req.resolution_type not in valid_types:
            raise HTTPException(400, f"invalid resolution_type: {req.resolution_type}")

        res = ScreenResolution(
            screen_state=req.screen_state,
            url_pattern=req.url_pattern,
            title_pattern=req.title_pattern,
            dom_signature=req.dom_signature,
            resolution_type=req.resolution_type,
            action_config=json.dumps(req.action_config, ensure_ascii=False) if req.action_config else None,
            source_error_id=error_id,
            approved=req.approved,
            notes=req.notes,
        )
        db.add(res)
        db.commit()
        return LabelResponse(ok=True, resolution_id=res.id)
    finally:
        db.close()


@router.get("/summary", response_model=dict)
def summarize_recent_errors(
    hours: int = Query(default=24, ge=1, le=168),
    kind: str | None = Query(default=None),
    _user=Depends(admin_session),
) -> dict:
    """Phase 4.1 — Haiku 로 worker_errors 한 줄 요약."""
    from hydra.ai.agents.error_summary_agent import summarize_errors
    db = _db_session.SessionLocal()
    try:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        q = db.query(WorkerError).filter(WorkerError.received_at >= cutoff)
        if kind:
            q = q.filter(WorkerError.kind == kind)
        rows = q.order_by(desc(WorkerError.received_at)).limit(200).all()
        as_dicts = [{
            "kind": r.kind,
            "message": r.message,
            "screen_state": r.screen_state,
            "failure_taxonomy": r.failure_taxonomy,
            "captured_url": r.captured_url,
            "received_at": r.received_at.isoformat() if r.received_at else None,
            "worker_id": r.worker_id,
        } for r in rows]
        summary = summarize_errors(as_dicts, window_hint=f"최근 {hours}시간")
        return {
            "ok": True,
            "count": len(rows),
            "window_hours": hours,
            "kind_filter": kind,
            "summary": summary,
        }
    finally:
        db.close()


@router.get("/resolutions", response_model=list[dict])
def list_resolutions(
    screen_state: str | None = Query(default=None),
    approved_only: bool = Query(default=False),
    _user=Depends(admin_session),
) -> list[dict]:
    """저장된 ScreenResolution 목록 (운영자가 만든 라벨)."""
    db = _db_session.SessionLocal()
    try:
        q = db.query(ScreenResolution)
        if screen_state:
            q = q.filter(ScreenResolution.screen_state == screen_state)
        if approved_only:
            q = q.filter(ScreenResolution.approved.is_(True))
        q = q.order_by(desc(ScreenResolution.created_at)).limit(200)
        out = []
        for r in q.all():
            out.append({
                "id": r.id,
                "screen_state": r.screen_state,
                "url_pattern": r.url_pattern,
                "title_pattern": r.title_pattern,
                "dom_signature": r.dom_signature,
                "resolution_type": r.resolution_type,
                "action_config": json.loads(r.action_config) if r.action_config else None,
                "approved": r.approved,
                "hit_count": r.hit_count,
                "last_hit_at": r.last_hit_at.isoformat() if r.last_hit_at else None,
                "created_at": r.created_at.isoformat(),
                "source_error_id": r.source_error_id,
                "notes": r.notes,
            })
        return out
    finally:
        db.close()
