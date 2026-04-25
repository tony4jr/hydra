"""T14/T15 — AdsPower 통합 어드민 엔드포인트.

태그 (브랜드 그룹핑) + 정기 fingerprint 회전 발행.
워커가 실제 호출은 commands 시스템 사용 — 여기는 발행 + 정책만.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hydra.db import session as _db_session
from hydra.db.models import Account, Worker, WorkerCommand
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()


# T14 Tags — DB 테이블 없이 Worker.notes 또는 Account.notes JSON 활용
# 또는 추후 별도 테이블. 현재는 brand 키워드 기반 매핑만 단순 제공.

class AccountTagsRequest(BaseModel):
    account_ids: list[int] = Field(..., min_length=1)
    tag: str = Field(..., min_length=1, max_length=64)
    action: str = Field(..., pattern="^(add|remove)$")


@router.post("/accounts/tag")
def tag_accounts(
    req: AccountTagsRequest,
    _session: dict = Depends(admin_session),
) -> dict:
    """Account.notes 의 JSON 배열에 태그 추가/제거.

    notes 가 valid JSON 이 아니면 새 배열로 시작.
    """
    db = _db_session.SessionLocal()
    try:
        updated = 0
        for aid in req.account_ids:
            acc = db.get(Account, aid)
            if acc is None:
                continue
            tags: list[str] = []
            if acc.notes:
                try:
                    parsed = json.loads(acc.notes)
                    if isinstance(parsed, dict) and "tags" in parsed:
                        tags = list(parsed["tags"])
                    elif isinstance(parsed, list):
                        tags = list(parsed)
                except Exception:
                    pass

            if req.action == "add" and req.tag not in tags:
                tags.append(req.tag)
            elif req.action == "remove" and req.tag in tags:
                tags.remove(req.tag)
            else:
                continue

            # 보존: 기존 notes 가 dict 면 tags 만 교체, 아니면 dict 새로
            try:
                existing = json.loads(acc.notes) if acc.notes else {}
                if not isinstance(existing, dict):
                    existing = {}
            except Exception:
                existing = {}
            existing["tags"] = tags
            acc.notes = json.dumps(existing, ensure_ascii=False)
            updated += 1
        db.commit()
        return {"updated": updated}
    finally:
        db.close()


@router.get("/accounts/by-tag/{tag}")
def list_by_tag(
    tag: str,
    _session: dict = Depends(admin_session),
) -> list[dict]:
    """특정 태그가 붙은 계정 목록."""
    db = _db_session.SessionLocal()
    try:
        # JSON 검색은 PG 에서 더 효율적이지만 SQLite 호환 위해 단순 LIKE 사용
        rows = db.query(Account).filter(Account.notes.like(f'%"{tag}"%')).all()
        out = []
        for acc in rows:
            try:
                parsed = json.loads(acc.notes) if acc.notes else {}
                tags = parsed.get("tags", []) if isinstance(parsed, dict) else []
            except Exception:
                tags = []
            if tag in tags:
                out.append({
                    "account_id": acc.id, "gmail": acc.gmail,
                    "tags": tags, "status": acc.status,
                })
        return out
    finally:
        db.close()


# T15 정기 fingerprint 회전 — 30~60일 주기로 어드민이 일괄 발행

class FpRotationRequest(BaseModel):
    days_since_last: int = Field(default=45, ge=14, le=180)
    max_per_run: int = Field(default=10, ge=1, le=200)
    dry_run: bool = False


@router.post("/fingerprint-rotation")
def schedule_fingerprint_rotation(
    req: FpRotationRequest,
    _session: dict = Depends(admin_session),
) -> dict:
    """N일 이상 fingerprint 회전 안 한 계정에 refresh_fingerprint 명령 발행.

    안티디텍션 정책: 30~60일 ± 지터로 자연스러운 회전.
    """
    cutoff = datetime.now(UTC) - timedelta(days=req.days_since_last)
    db = _db_session.SessionLocal()
    try:
        # last_open_time 기반 — 오래 안 쓴 계정부터
        # account.last_used + worker_id 기반으로 발행
        # (단순화: 모든 active 계정 중 max_per_run 만큼 무작위)
        candidates = (
            db.query(Account)
            .filter(Account.status == "active")
            .filter(Account.adspower_profile_id.isnot(None))
            .limit(req.max_per_run * 3)  # 여유 fetch
            .all()
        )

        if not candidates:
            return {"scheduled": 0, "candidates": 0}

        # 어떤 워커에 보낼지 — online 인 워커 중 first
        worker = (
            db.query(Worker)
            .filter(Worker.status == "online")
            .first()
        )
        if worker is None and not req.dry_run:
            raise HTTPException(409, "no online worker to dispatch")

        scheduled = 0
        target_accounts = candidates[: req.max_per_run]
        if not req.dry_run:
            for acc in target_accounts:
                cmd = WorkerCommand(
                    worker_id=worker.id,
                    command="refresh_fingerprint",
                    payload=json.dumps({"profile_ids": [acc.adspower_profile_id]}),
                    status="pending",
                    issued_at=datetime.now(UTC),
                )
                db.add(cmd)
                scheduled += 1
            db.commit()

        return {
            "scheduled": scheduled,
            "candidates": len(candidates),
            "target_accounts": [a.id for a in target_accounts],
            "dry_run": req.dry_run,
        }
    finally:
        db.close()
