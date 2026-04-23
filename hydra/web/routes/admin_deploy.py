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
DEPLOY_UNIT = "hydra-deploy.service"


@router.get("/server-config")
def get_server_config(_session: dict = Depends(admin_session)) -> dict:
    """현재 서버 상태 (버전/정지/카나리). UI 상단 킬스위치 바에서 10초마다 폴링."""
    return {
        "current_version": scfg.get_current_version(),
        "paused": scfg.is_paused(),
        "canary_worker_ids": scfg.get_canary_worker_ids(),
    }


@router.post("/deploy")
def trigger_deploy(_session: dict = Depends(admin_session)) -> dict:
    """`systemctl start --no-block hydra-deploy.service` 로 트리거.

    deploy.sh 를 별도 systemd oneshot 유닛에서 실행 — hydra-server restart 시 같은
    cgroup 에 있으면 함께 kill 돼서 bump_version 단계에 못 도달하는 문제 방지.
    로그: /var/log/hydra/deploy.log + `journalctl -u hydra-deploy`.
    """
    if not DEPLOY_SCRIPT.is_file():
        raise HTTPException(500, f"deploy script not found: {DEPLOY_SCRIPT}")
    try:
        subprocess.check_call(
            ["sudo", "systemctl", "start", "--no-block", DEPLOY_UNIT],
            timeout=10,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"systemctl start failed (rc={e.returncode})")
    except FileNotFoundError:
        # dev (Mac) 환경 — systemctl 없음. 테스트 모킹으로 커버됨.
        raise HTTPException(500, "systemctl not available")
    return {"started": True, "unit": DEPLOY_UNIT}


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
