"""Windows Task Scheduler 에 HydraWorker 자동 등록.

진짜 본질 결함이었던 부분 — worker/updater.py 가 update 후 sys.exit 하면
Task Scheduler 가 다시 띄워줘야 하는데, 등록 안 되어 있으면 영원히 죽음.
사용자가 매번 cmd 직접 띄운 root cause.

startup 시 한 번만 schtasks /query 로 확인. 없으면 /create 로 자가 등록.
일반 user 권한으로 등록 가능 (admin 불필요).
"""
from __future__ import annotations

import os
import subprocess
import sys


TASK_NAME = "HydraWorker"


def ensure_registered() -> None:
    """HydraWorker task 등록 보장. Windows 외 OS 는 no-op.

    이미 등록돼 있으면 아무것도 안 함. 없으면 자가 등록.
    실패해도 예외 propagate 안 함 — startup 막지 않음.

    Slice 1 — Admin Agent 도입 후 desktop worker 가 self-register 하면 중복
    실행/중복 heartbeat 가 발생한다. HYDRA_DISABLE_TASK_REGISTER=1 이면 skip
    (Phase 2 의 Admin Agent 가 task scheduler 등록을 owned).
    """
    if os.environ.get("HYDRA_DISABLE_TASK_REGISTER"):
        print("[Worker] task_register skip — HYDRA_DISABLE_TASK_REGISTER set")
        return
    if sys.platform != "win32":
        return
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return  # 이미 등록됨
    except Exception:
        pass  # 조회 실패해도 등록 시도

    # 현재 실행 중인 python.exe 경로 + -m worker 형태
    python_exe = sys.executable  # 예: C:\hydra\.venv\Scripts\python.exe
    # cwd 도 같이 저장 (Task Scheduler 가 다른 dir 에서 실행하지 않게)
    cwd = os.getcwd()
    tr = f'"{python_exe}" -m worker'

    try:
        subprocess.run(
            [
                "schtasks", "/create",
                "/tn", TASK_NAME,
                "/tr", tr,
                "/sc", "onstart",  # OS 부팅 시
                "/rl", "limited",  # admin 권한 불필요
                "/f",              # 이미 있으면 덮어씀
            ],
            check=True,
            capture_output=True,
            timeout=15,
            cwd=cwd,
        )
        print(f"[Worker] Task Scheduler 등록 완료 — name={TASK_NAME}, cmd={tr}")
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("cp949", errors="ignore")
        print(f"[Worker] Task Scheduler 등록 실패: {stderr.strip()}")
    except Exception as e:
        print(f"[Worker] Task Scheduler 등록 예외: {type(e).__name__}: {e}")
