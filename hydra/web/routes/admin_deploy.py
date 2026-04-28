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


@router.get("/deploy/status")
def deploy_status(_session: dict = Depends(admin_session)) -> dict:
    """현재 systemd 유닛 상태 + 마지막 종료 코드."""
    try:
        active = subprocess.run(
            ["systemctl", "is-active", DEPLOY_UNIT],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        result = subprocess.run(
            ["systemctl", "show", DEPLOY_UNIT, "--property=Result,ExecMainStatus,ActiveEnterTimestamp,InactiveEnterTimestamp"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        props = {}
        for line in result.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v
        return {
            "active": active,  # active|inactive|activating|failed
            "result": props.get("Result", ""),  # success|exit-code|signal|...
            "exit_code": props.get("ExecMainStatus", ""),
            "last_run_started": props.get("ActiveEnterTimestamp", ""),
            "last_run_ended": props.get("InactiveEnterTimestamp", ""),
        }
    except FileNotFoundError:
        raise HTTPException(500, "systemctl not available")
    except subprocess.SubprocessError as e:
        raise HTTPException(500, f"systemctl query failed: {e}")


@router.get("/deploy/log")
def deploy_log(lines: int = 200, _session: dict = Depends(admin_session)) -> dict:
    """최근 배포 로그를 journalctl 에서 가져옴 (파일보다 안정적)."""
    n = max(10, min(lines, 1000))
    try:
        out = subprocess.run(
            ["sudo", "journalctl", "-u", DEPLOY_UNIT, "-n", str(n), "--no-pager", "--output=short-iso"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            # Fallback: log file
            log_file = Path("/var/log/hydra/deploy.log")
            if log_file.is_file():
                content = subprocess.run(
                    ["sudo", "tail", "-n", str(n), str(log_file)],
                    capture_output=True, text=True, timeout=5,
                ).stdout
                return {"source": "file", "lines": content}
            return {"source": "none", "lines": out.stderr or "(no log available)"}
        return {"source": "journal", "lines": out.stdout}
    except FileNotFoundError:
        raise HTTPException(500, "journalctl not available")
    except subprocess.SubprocessError as e:
        raise HTTPException(500, f"log read failed: {e}")


@router.post("/pause")
def pause_all(_session: dict = Depends(admin_session)) -> dict:
    scfg.set_paused(True)
    return {"paused": True}


@router.post("/unpause")
def unpause_all(_session: dict = Depends(admin_session)) -> dict:
    scfg.set_paused(False)
    return {"paused": False}


@router.post("/emergency-stop")
def emergency_stop(_session: dict = Depends(admin_session)) -> dict:
    """T9 비상정지 — server pause + 모든 워커에 stop_all_browsers 명령 fan-out.

    현재 진행중인 브라우저까지 즉시 kill. 어드민 UI 빨간 버튼.
    """
    from hydra.db import session as _db_session
    from hydra.db.models import Worker, WorkerCommand
    from datetime import datetime as _dt, timezone as _tz

    scfg.set_paused(True)

    db = _db_session.SessionLocal()
    try:
        workers = db.query(Worker).filter(Worker.token_hash.isnot(None)).all()
        count = 0
        for w in workers:
            db.add(WorkerCommand(
                worker_id=w.id,
                command="stop_all_browsers",
                payload=None,
                status="pending",
                issued_at=_dt.now(_tz.utc),
            ))
            # 워커 자체도 paused 마킹
            w.status = "paused"
            w.paused_reason = "emergency-stop"
            count += 1
        db.commit()
        return {"paused": True, "emergency": True, "workers_notified": count}
    finally:
        db.close()


class CanaryRequest(BaseModel):
    worker_ids: list[int] = Field(default_factory=list)


@router.post("/canary")
def set_canary(
    req: CanaryRequest,
    _session: dict = Depends(admin_session),
) -> dict:
    scfg.set_canary_worker_ids(req.worker_ids)
    return {"canary_worker_ids": req.worker_ids}
