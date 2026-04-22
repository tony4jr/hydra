"""어드민 전용 — 워커 관리 엔드포인트.

- POST /api/admin/workers/enroll : 새 워커용 1회용 enrollment 토큰 + PowerShell 설치 명령 발급

이후 Task 25 에서 카나리/일시정지 등 추가.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hydra.core.enrollment import generate_enrollment_token
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()


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
