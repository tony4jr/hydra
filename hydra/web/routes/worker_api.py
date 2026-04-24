"""워커 전용 엔드포인트 — enrollment 토큰 소비 + v2 heartbeat.

Legacy `/api/workers/register`, `/api/workers/heartbeat` (hydra.api.workers) 는 당분간
공존. 신규 워커는 아래 flow 사용:

  1. POST /api/workers/enroll   : enrollment_token → worker_token + shared secrets
  2. POST /api/workers/heartbeat/v2 : X-Worker-Token → {current_version, paused, canary}
"""
from __future__ import annotations

import json
import os
import secrets as _secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pathlib import Path as _Path
from pydantic import BaseModel, Field

from hydra.core import server_config as scfg
from hydra.core.auth import hash_password, verify_password
from hydra.core.enrollment import verify_enrollment_token
from hydra.db import session as _db_session
from hydra.db.models import Worker, WorkerError

router = APIRouter()


_SETUP_PS1 = _Path(__file__).resolve().parents[3] / "setup" / "hydra-worker-setup.ps1"


@router.get("/setup.ps1")
def serve_setup_ps1() -> Response:
    """Windows 워커 설치 스크립트 (공개 — 토큰은 유저가 param 으로 전달).

    UTF-8 BOM 을 prepend — PowerShell 5.1 (Windows 기본) 은 BOM 없으면 cp949 로
    해석해 한글 주석이 깨지며 ParseError 발생.
    """
    if not _SETUP_PS1.is_file():
        raise HTTPException(500, "setup script missing")
    bom = b"\xef\xbb\xbf"
    return Response(
        bom + _SETUP_PS1.read_bytes(),
        media_type="text/plain; charset=utf-8",
    )


# ───────────── enroll ─────────────
class EnrollRequest(BaseModel):
    enrollment_token: str
    hostname: str = Field(..., min_length=1, max_length=128)


class EnrollResponse(BaseModel):
    worker_id: int
    worker_token: str
    secrets: dict


@router.post("/enroll", response_model=EnrollResponse)
def enroll(req: EnrollRequest) -> EnrollResponse:
    try:
        data = verify_enrollment_token(req.enrollment_token)
    except Exception:
        raise HTTPException(401, "invalid enrollment token")
    worker_name = data["worker_name"]

    db = _db_session.SessionLocal()
    try:
        worker = db.query(Worker).filter_by(name=worker_name).first()
        if worker is None:
            worker = Worker(name=worker_name, status="offline")
            db.add(worker)
            db.flush()

        raw_token = _secrets.token_urlsafe(32)
        worker.token_hash = hash_password(raw_token)
        worker.os_type = "windows"
        worker.enrolled_at = datetime.now(UTC)
        db.commit()

        shared = {
            "SERVER_URL": os.getenv("SERVER_URL", ""),
            "DB_CRYPTO_KEY": os.getenv("DB_CRYPTO_KEY") or os.getenv("HYDRA_ENCRYPTION_KEY", ""),
        }
        return EnrollResponse(worker_id=worker.id, worker_token=raw_token, secrets=shared)
    finally:
        db.close()


# ───────────── worker_auth Depends ─────────────
def worker_auth(x_worker_token: str = Header(default="")) -> Worker:
    if not x_worker_token:
        raise HTTPException(401, "missing worker token")
    db = _db_session.SessionLocal()
    try:
        # ~20대 규모 순회 — 100대+ 되면 prefix 인덱스 도입
        for w in db.query(Worker).filter(Worker.token_hash.isnot(None)).all():
            if verify_password(x_worker_token, w.token_hash):
                db.expunge(w)
                return w
        raise HTTPException(401, "invalid worker token")
    finally:
        db.close()


# ───────────── heartbeat v2 ─────────────
class HeartbeatRequest(BaseModel):
    version: str
    os_type: str = "windows"
    cpu_percent: float = 0.0
    mem_used_mb: int = 0
    disk_free_gb: float = 0.0
    adb_devices: list[str] = []
    adspower_version: str = ""
    playwright_browsers_ok: bool = True
    current_task_id: int | None = None
    time_offset_ms: int = 0


class HeartbeatResponse(BaseModel):
    current_version: str
    paused: bool
    canary_worker_ids: list[int]
    restart_requested: bool = False
    worker_config: dict


# ───────────── error report ─────────────
_ALLOWED_ERROR_KINDS = frozenset({
    "heartbeat_fail", "fetch_fail", "task_fail", "diagnostic",
    "update_fail", "other",
})
_DEDUPE_WINDOW_SECONDS = 600  # 10분


class ReportErrorRequest(BaseModel):
    kind: str = Field(..., min_length=1, max_length=32)
    message: str = Field(..., min_length=1, max_length=2000)
    traceback: str | None = None
    context: dict | None = None
    occurred_at: datetime | None = None  # 생략 시 서버 시각


class ReportErrorResponse(BaseModel):
    ok: bool
    deduped: bool = False  # True: 10분 내 중복으로 저장 스킵


@router.post("/report-error", response_model=ReportErrorResponse)
def report_error(
    req: ReportErrorRequest,
    worker: Worker = Depends(worker_auth),
) -> ReportErrorResponse:
    """워커가 발생시킨 에러/진단 리포트 저장.

    dedupe: 같은 (worker_id, kind, message) 가 10분 내에 이미 있으면 저장 스킵.
    """
    kind = req.kind if req.kind in _ALLOWED_ERROR_KINDS else "other"
    occurred_at = req.occurred_at or datetime.now(UTC)
    # occurred_at 이 tz-naive 이면 UTC 로 간주
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)

    db = _db_session.SessionLocal()
    try:
        from datetime import timedelta
        cutoff = datetime.now(UTC) - timedelta(seconds=_DEDUPE_WINDOW_SECONDS)
        dup = (
            db.query(WorkerError)
            .filter(
                WorkerError.worker_id == worker.id,
                WorkerError.kind == kind,
                WorkerError.message == req.message,
                WorkerError.received_at >= cutoff,
            )
            .first()
        )
        if dup is not None:
            return ReportErrorResponse(ok=True, deduped=True)

        ctx_json = json.dumps(req.context, ensure_ascii=False) if req.context else None
        err = WorkerError(
            worker_id=worker.id,
            kind=kind,
            message=req.message,
            traceback=req.traceback,
            context=ctx_json,
            occurred_at=occurred_at,
            received_at=datetime.now(UTC),
        )
        db.add(err)
        db.commit()
        return ReportErrorResponse(ok=True, deduped=False)
    finally:
        db.close()


@router.post("/heartbeat/v2", response_model=HeartbeatResponse)
def heartbeat_v2(
    req: HeartbeatRequest,
    worker: Worker = Depends(worker_auth),
) -> HeartbeatResponse:
    db = _db_session.SessionLocal()
    try:
        w = db.get(Worker, worker.id)
        w.last_heartbeat = datetime.now(UTC)
        w.current_version = req.version
        w.status = "online"
        w.health_snapshot = json.dumps(req.model_dump(), ensure_ascii=False)
        db.commit()

        return HeartbeatResponse(
            current_version=scfg.get_current_version(session=db) or "",
            paused=scfg.is_paused(session=db),
            canary_worker_ids=scfg.get_canary_worker_ids(session=db),
            worker_config={
                "poll_interval_sec": 15,
                "max_concurrent_tasks": 1,
                "drain_timeout_minutes": 15,
            },
        )
    finally:
        db.close()
