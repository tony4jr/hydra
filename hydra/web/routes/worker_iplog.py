"""PR-D: IpLog 서버화 endpoints.

워커는 더 이상 로컬 SQLite IpLog 사용하지 않음. 모든 IP 추적은 server-side.

엔드포인트:
- POST /api/workers/ip-check {ip_address, account_id, cooldown_minutes} → {available: bool}
- POST /api/workers/ip-log/start {account_id, ip_address, device_id} → {log_id}
- POST /api/workers/ip-log/end {log_id} → {ok}

소유권: account_id 가 envelope 에서 온 거라 worker_auth 만으로 충분.
"""
from __future__ import annotations

from datetime import datetime, UTC, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hydra.db import session as _db_session
from hydra.db.models import IpLog, Worker
from hydra.web.routes.worker_api import worker_auth

router = APIRouter()


class IpCheckRequest(BaseModel):
    ip_address: str
    account_id: int
    cooldown_minutes: int = 30


class IpCheckResponse(BaseModel):
    available: bool


@router.post("/ip-check", response_model=IpCheckResponse)
def ip_check(
    req: IpCheckRequest,
    worker: Worker = Depends(worker_auth),
) -> IpCheckResponse:
    """다른 계정이 cooldown 내에 이 IP 를 썼는지 server-side query."""
    db = _db_session.SessionLocal()
    try:
        cutoff = datetime.now(UTC) - timedelta(minutes=req.cooldown_minutes)
        # SQLAlchemy DateTime — server prod 는 tz-naive 로 저장됨.
        cutoff_naive = cutoff.replace(tzinfo=None)
        conflict = (
            db.query(IpLog)
            .filter(
                IpLog.ip_address == req.ip_address,
                IpLog.started_at >= cutoff_naive,
                IpLog.account_id != req.account_id,
            )
            .first()
        )
        return IpCheckResponse(available=conflict is None)
    finally:
        db.close()


class IpLogStartRequest(BaseModel):
    account_id: int
    ip_address: str
    device_id: Optional[str] = None


class IpLogStartResponse(BaseModel):
    log_id: int


@router.post("/ip-log/start", response_model=IpLogStartResponse)
def ip_log_start(
    req: IpLogStartRequest,
    worker: Worker = Depends(worker_auth),
) -> IpLogStartResponse:
    """IpLog INSERT — server Postgres.

    소유권 검증 (Codex 권고): 워커가 현재 잡고 있는 running task 중 req.account_id 와
    일치하는 게 있어야 함. 다른 워커/계정으로 ghost 기록 차단.
    """
    from hydra.db.models import Task
    db = _db_session.SessionLocal()
    try:
        owned = (
            db.query(Task)
            .filter(
                Task.worker_id == worker.id,
                Task.status == "running",
                Task.account_id == req.account_id,
            )
            .first()
        )
        if owned is None:
            raise HTTPException(
                403,
                f"account_id={req.account_id} not owned by worker_id={worker.id} "
                "(no running task)",
            )
        # Codex 5/12 P2 — worker_id 기록. end 시 동일 worker 인지 verify.
        record = IpLog(
            account_id=req.account_id,
            ip_address=req.ip_address,
            device_id=req.device_id,
            worker_id=worker.id,
        )
        db.add(record)
        db.commit()
        return IpLogStartResponse(log_id=record.id)
    finally:
        db.close()


class IpLogEndRequest(BaseModel):
    log_id: int = Field(..., gt=0)


@router.post("/ip-log/end")
def ip_log_end(
    req: IpLogEndRequest,
    worker: Worker = Depends(worker_auth),
) -> dict:
    """IpLog.ended_at 기록.

    Codex 5/12 P2 — 소유권 검증: start 시 worker_id 가 박혀있으면 호출 worker
    와 일치해야 함. NULL (옛 backfill row) 은 soft pass (호환). 다른 worker
    가 ended 처리 시도하면 403.
    """
    db = _db_session.SessionLocal()
    try:
        record = db.get(IpLog, req.log_id)
        if record is None:
            raise HTTPException(404, "ip_log not found")
        # 옛 row 는 worker_id NULL — soft pass. 새 row 는 ownership 강제.
        if record.worker_id is not None and record.worker_id != worker.id:
            raise HTTPException(
                403,
                "ip_log not owned by this worker "
                f"(owned by worker_id={record.worker_id})",
            )
        record.ended_at = datetime.now(UTC)
        db.commit()
        return {"ok": True}
    finally:
        db.close()
