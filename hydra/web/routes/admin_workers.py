"""어드민 전용 — 워커 관리 엔드포인트.

- POST /api/admin/workers/enroll : 새 워커용 1회용 enrollment 토큰 + PowerShell 설치 명령 발급

이후 Task 25 에서 카나리/일시정지 등 추가.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hydra.core.enrollment import generate_enrollment_token
from hydra.db import session as _db_session
from hydra.db.models import Task, Worker
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()

VALID_TASK_TYPES = {
    "*",
    "create_account",
    "comment",
    "like",
    "watch_video",
    "warmup",
    "onboarding_verify",
}


class EnrollRequest(BaseModel):
    worker_name: str = Field(..., min_length=1, max_length=64)
    ttl_hours: int = Field(default=24, ge=1, le=24 * 7)


class EnrollResponse(BaseModel):
    enrollment_token: str
    install_command: str
    expires_in_hours: int


@router.post("/enroll", response_model=EnrollResponse)
def create_enrollment(
    req: EnrollRequest,
    _session: dict = Depends(admin_session),
) -> EnrollResponse:
    name = req.worker_name.strip()
    if not name:
        raise HTTPException(400, "worker_name required")

    token = generate_enrollment_token(name, ttl_hours=req.ttl_hours)
    server_url = os.getenv("SERVER_URL", "").rstrip("/")
    if not server_url:
        raise HTTPException(500, "SERVER_URL not configured")

    install_command = (
        f"iwr -Uri {server_url}/api/workers/setup.ps1 -OutFile setup.ps1; "
        f".\\setup.ps1 -Token '{token}' -ServerUrl '{server_url}'"
    )
    return EnrollResponse(
        enrollment_token=token,
        install_command=install_command,
        expires_in_hours=req.ttl_hours,
    )


class CurrentTaskInfo(BaseModel):
    id: int
    task_type: str
    started_at: Optional[datetime] = None


class WorkerOut(BaseModel):
    id: int
    name: str
    status: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    current_version: Optional[str] = None
    os_type: Optional[str] = None
    allow_preparation: Optional[bool] = None
    allow_campaign: Optional[bool] = None
    allowed_task_types: list[str] = []
    enrolled_at: Optional[datetime] = None
    current_task: Optional[CurrentTaskInfo] = None  # M2.1-5


def _worker_to_out(w: Worker, current_task: Optional[Task] = None) -> WorkerOut:
    try:
        types = json.loads(w.allowed_task_types or '["*"]')
        if not isinstance(types, list):
            types = ["*"]
    except json.JSONDecodeError:
        types = ["*"]
    ct = None
    if current_task is not None:
        ct = CurrentTaskInfo(
            id=current_task.id,
            task_type=current_task.task_type,
            started_at=current_task.started_at,
        )
    return WorkerOut(
        id=w.id, name=w.name, status=w.status,
        last_heartbeat=w.last_heartbeat,
        current_version=w.current_version, os_type=w.os_type,
        allow_preparation=w.allow_preparation, allow_campaign=w.allow_campaign,
        allowed_task_types=[str(t) for t in types],
        enrolled_at=w.enrolled_at,
        current_task=ct,
    )


@router.get("/", response_model=list[WorkerOut])
def list_workers(_session: dict = Depends(admin_session)) -> list[WorkerOut]:
    db = _db_session.SessionLocal()
    try:
        workers = db.query(Worker).order_by(Worker.id).all()
        result = []
        for w in workers:
            running = (
                db.query(Task)
                .filter(Task.worker_id == w.id, Task.status == "running")
                .first()
            )
            result.append(_worker_to_out(w, running))
        return result
    finally:
        db.close()


class WorkerPatch(BaseModel):
    allowed_task_types: Optional[list[str]] = None
    allow_preparation: Optional[bool] = None
    allow_campaign: Optional[bool] = None
    status: Optional[str] = None  # online|offline|paused
    adspower_api_key: Optional[str] = None  # 평문 입력, 서버에서 Fernet 암호화 저장
                                            # 빈 문자열 "" 은 제거 의미


@router.patch("/{worker_id}", response_model=WorkerOut)
def update_worker(
    worker_id: int,
    req: WorkerPatch,
    _session: dict = Depends(admin_session),
) -> WorkerOut:
    db = _db_session.SessionLocal()
    try:
        w = db.get(Worker, worker_id)
        if w is None:
            raise HTTPException(404, "worker not found")

        if req.allowed_task_types is not None:
            types = list(req.allowed_task_types)
            unknown = [t for t in types if t not in VALID_TASK_TYPES]
            if unknown:
                raise HTTPException(
                    400, f"unknown task_type(s): {unknown}. "
                    f"allowed: {sorted(VALID_TASK_TYPES)}",
                )
            # wildcard 는 단독
            if "*" in types:
                types = ["*"]
            w.allowed_task_types = json.dumps(types)

        if req.allow_preparation is not None:
            w.allow_preparation = bool(req.allow_preparation)
        if req.allow_campaign is not None:
            w.allow_campaign = bool(req.allow_campaign)
        if req.status is not None:
            if req.status not in ("online", "offline", "paused"):
                raise HTTPException(400, f"invalid status: {req.status}")
            w.status = req.status
        if req.adspower_api_key is not None:
            from hydra.core import crypto
            if req.adspower_api_key == "":
                w.adspower_api_key_enc = None
            else:
                w.adspower_api_key_enc = crypto.encrypt(req.adspower_api_key)

        db.commit()
        db.refresh(w)
        running = (
            db.query(Task)
            .filter(Task.worker_id == w.id, Task.status == "running")
            .first()
        )
        return _worker_to_out(w, running)
    finally:
        db.close()


# ───────────── worker errors listing ─────────────
class WorkerErrorOut(BaseModel):
    id: int
    worker_id: int
    worker_name: str
    kind: str
    message: str
    traceback: Optional[str] = None
    context: Optional[dict] = None
    occurred_at: str
    received_at: str


@router.get("/errors")
def list_worker_errors(
    _session: dict = Depends(admin_session),
    worker_id: Optional[int] = None,
    kind: Optional[str] = None,
    limit: int = 200,
) -> list[WorkerErrorOut]:
    """워커 에러 로그 조회 (최신순).

    필터: worker_id, kind. limit 최대 1000.
    """
    from hydra.db.models import WorkerError
    limit = max(1, min(limit, 1000))

    db = _db_session.SessionLocal()
    try:
        q = db.query(WorkerError, Worker).join(Worker, WorkerError.worker_id == Worker.id)
        if worker_id is not None:
            q = q.filter(WorkerError.worker_id == worker_id)
        if kind:
            q = q.filter(WorkerError.kind == kind)
        q = q.order_by(WorkerError.received_at.desc()).limit(limit)

        out = []
        for err, worker in q.all():
            ctx = None
            if err.context:
                try:
                    ctx = json.loads(err.context)
                except Exception:
                    ctx = {"_raw": err.context}
            out.append(WorkerErrorOut(
                id=err.id,
                worker_id=err.worker_id,
                worker_name=worker.name,
                kind=err.kind,
                message=err.message,
                traceback=err.traceback,
                context=ctx,
                occurred_at=err.occurred_at.isoformat(),
                received_at=err.received_at.isoformat(),
            ))
        return out
    finally:
        db.close()
