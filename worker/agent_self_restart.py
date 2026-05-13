"""Slice 3.3 — admin agent self-restart via NSSM (ack-then-spawn).

- ADMIN_AGENT_SERVICE_NAME: setup/install-admin-agent-service.ps1 의 기본값
  과 동일 (테스트로 동기화 검증)
- resolve_nssm_path(): nssm 실행 파일 위치 찾기. 우선순위:
    1) HYDRA_NSSM_PATH env
    2) shutil.which("nssm")
    3) C:\\ProgramData\\chocolatey\\bin\\nssm.exe
  fallback 모두 실패 시 RuntimeError → ack 전에 fail 처리 가능.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


# Slice 3.3 — service name 은 고정. payload service_name 받지 않음.
# install-admin-agent-service.ps1 의 -ServiceName 기본값과 동일해야 함
# (테스트로 동기화 검증).
ADMIN_AGENT_SERVICE_NAME = "HydraAdminAgent"


_CHOCOLATEY_NSSM = r"C:\ProgramData\chocolatey\bin\nssm.exe"


def resolve_nssm_path() -> str:
    """nssm 실행 파일 경로 찾기. 못 찾으면 RuntimeError.

    우선순위 (Codex Slice 3.3 권고):
      1. HYDRA_NSSM_PATH env (운영자가 명시 지정)
      2. shutil.which("nssm") — PATH 검색
      3. C:\\ProgramData\\chocolatey\\bin\\nssm.exe — Windows choco install 기본
    """
    env_path = os.environ.get("HYDRA_NSSM_PATH", "").strip()
    if env_path and Path(env_path).is_file():
        return env_path
    which = shutil.which("nssm")
    if which:
        return which
    if Path(_CHOCOLATEY_NSSM).is_file():
        return _CHOCOLATEY_NSSM
    raise RuntimeError(
        "nssm not found (checked HYDRA_NSSM_PATH, PATH, chocolatey default)"
    )


def helper_log_path() -> str:
    """helper subprocess 의 stdout/stderr 가 들어갈 로그 파일 경로."""
    tmp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    return str(Path(tmp) / "hydra_agent_self_restart.log")


def spawn_restart_helper(
    *,
    nssm_path: str,
    service_name: str,
    delay_sec: int,
    log_path: str,
) -> subprocess.Popen:
    """detached helper 프로세스 spawn — sleep 후 nssm restart 호출.

    Windows: DETACHED_PROCESS | CREATE_NO_WINDOW
    POSIX (dev): start_new_session=True

    이 함수는 ack 후에만 호출됨 (Codex 권고: ack-then-spawn).
    Popen 자체 실패 시 호출자가 worker_error 보고.
    """
    argv = [
        sys.executable,
        "-m",
        "worker.agent_self_restart_helper",
        str(int(delay_sec)),
        service_name,
        nssm_path,
        log_path,
    ]
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        # DETACHED_PROCESS=0x00000008, CREATE_NO_WINDOW=0x08000000
        # parent (admin agent) 가 service stop 으로 죽어도 helper 는 살아남음
        kwargs["creationflags"] = 0x00000008 | 0x08000000
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(argv, **kwargs)
