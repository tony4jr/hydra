"""워커 전용 엔드포인트 — enrollment 토큰 소비 + v2 heartbeat.

Legacy `/api/workers/register`, `/api/workers/heartbeat` (hydra.api.workers) 는 당분간
공존. 신규 워커는 아래 flow 사용:

  1. POST /api/workers/enroll   : enrollment_token → worker_token + shared secrets
  2. POST /api/workers/heartbeat/v2 : X-Worker-Token → {current_version, paused, canary}
"""
from __future__ import annotations

import hashlib
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


def _sha256_hex(s: str) -> str:
    """워커 토큰 → SHA-256 hex. 256bit 랜덤 토큰이라 bcrypt 불필요."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


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
        worker.token_hash = hash_password(raw_token)  # [LEGACY] 폐기 예정
        worker.token_prefix = raw_token[:8]            # [LEGACY] 폐기 예정
        worker.token_sha256 = _sha256_hex(raw_token)   # [PRIMARY] O(1) auth
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
    """워커 토큰 검증 — O(1) SHA-256 조회 우선, 레거시 bcrypt fallback.

    설계 근거: 워커 토큰은 `secrets.token_urlsafe(32)` (256bit 랜덤) 이라
    brute force 불가. bcrypt (slow hash) 는 사람 비밀번호용이지 API 토큰용이 아님.
    SHA-256 + UNIQUE 인덱스면 잘못된 토큰도 DB 0건 = 즉시 401 (bcrypt 순회 없음).
    """
    if not x_worker_token:
        raise HTTPException(401, "missing worker token")
    db = _db_session.SessionLocal()
    try:
        # [FAST PATH] SHA-256 O(1) 조회 — 정상 경로
        token_sha = _sha256_hex(x_worker_token)
        w = db.query(Worker).filter(Worker.token_sha256 == token_sha).first()
        if w is not None:
            db.expunge(w)
            return w

        # [LEGACY] SHA-256 미백필 워커 — 과도기 경로.
        # 최근 7일 heartbeat 있는 워커만 대상. 죽은 테스트 워커가 bad token 마다
        # bcrypt 당하는 것을 방지 (DoS-ish). 신규 워커는 enroll 시 sha256 세팅되므로
        # 이 경로는 pre-migration 워커 전용.
        from datetime import timedelta
        recent_cutoff = datetime.now(UTC) - timedelta(days=7)
        legacy = db.query(Worker).filter(
            Worker.token_hash.isnot(None),
            Worker.token_sha256.is_(None),
            Worker.last_heartbeat.isnot(None),
            Worker.last_heartbeat > recent_cutoff,
        ).all()
        for lw in legacy:
            if verify_password(x_worker_token, lw.token_hash):
                # 재발견 시 sha256 + prefix 백필 (다음 요청부터 fast path)
                lw.token_sha256 = token_sha
                lw.token_prefix = x_worker_token[:8]
                db.commit()
                db.refresh(lw)
                db.expunge(lw)
                return lw

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
    # 워커 전용 비밀 — null 이면 미설정 / 있으면 평문. 워커는 이걸 os.environ 에 주입.
    adspower_api_key: str | None = None


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

        ads_key: str | None = None
        if w.adspower_api_key_enc:
            try:
                from hydra.core import crypto
                ads_key = crypto.decrypt(w.adspower_api_key_enc)
            except Exception:
                ads_key = None
        return HeartbeatResponse(
            current_version=scfg.get_current_version(session=db) or "",
            paused=scfg.is_paused(session=db),
            canary_worker_ids=scfg.get_canary_worker_ids(session=db),
            worker_config={
                "poll_interval_sec": 15,
                "max_concurrent_tasks": 1,
                "drain_timeout_minutes": 15,
            },
            adspower_api_key=ads_key,
        )
    finally:
        db.close()
