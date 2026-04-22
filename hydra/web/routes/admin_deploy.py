"""배포 트리거 + 긴급정지 + 카나리 엔드포인트.

- POST /api/admin/deploy        : scripts/deploy.sh 비동기 실행
- POST /api/admin/pause|unpause : SystemConfig.paused 토글
- POST /api/admin/canary        : canary_worker_ids 갱신

전부 Depends(admin_session) 필수.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hydra.core import server_config as scfg
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()

DEPLOY_SCRIPT = Path("/opt/hydra/scripts/deploy.sh")


@router.post("/deploy")
def trigger_deploy(_session: dict = Depends(admin_session)) -> dict:
    """scripts/deploy.sh 비동기 실행.

    systemctl restart 로 hydra-server 자신이 죽을 수 있으므로 start_new_session 으로
    프로세스 세션 분리 (부모 죽어도 deploy.sh 계속 진행).
    stdout/stderr 는 systemd journal 로 (PIPE 안 씀 — 버퍼 막힘 방지).
    """
    if not DEPLOY_SCRIPT.is_file():
        raise HTTPException(500, f"deploy script not found: {DEPLOY_SCRIPT}")
    proc = subprocess.Popen(
        ["bash", str(DEPLOY_SCRIPT)],
        start_new_session=True,  # 부모 세션 죽어도 child 유지
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"started": True, "pid": proc.pid}


@router.post("/pause")
def pause_all(_session: dict = Depends(admin_session)) -> dict:
    scfg.set_paused(True)
    return {"paused": True}


@router.post("/unpause")
def unpause_all(_session: dict = Depends(admin_session)) -> dict:
    scfg.set_paused(False)
    return {"paused": False}


class CanaryRequest(BaseModel):
    worker_ids: list[int] = Field(default_factory=list)


@router.post("/canary")
def set_canary(
    req: CanaryRequest,
    _session: dict = Depends(admin_session),
) -> dict:
    scfg.set_canary_worker_ids(req.worker_ids)
    return {"canary_worker_ids": req.worker_ids}
