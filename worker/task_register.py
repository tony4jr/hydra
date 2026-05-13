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
from pathlib import Path


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
    # Codex 5/12 P1 — task 자체 의 WorkingDirectory ("Start in") 을 명시.
    # 부팅 시 task action 이 C:\Windows\System32 같은 default cwd 에서
    # 시작되면 import / config 경로 깨짐. schtasks /create 는 -WorkingDirectory
    # 옵션 없음 — PowerShell New-ScheduledTaskAction 사용.
    repo_dir = str(Path(__file__).resolve().parent.parent)
    # PowerShell 안에서 quote 처리 — single quote 안의 'path' 를 escape
    # 위해 user-controlled path 의 single quote 는 '' 로 doubling.
    def _ps_escape(s: str) -> str:
        return s.replace("'", "''")
    py_esc = _ps_escape(python_exe)
    repo_esc = _ps_escape(repo_dir)
    ps_script = (
        f"$action = New-ScheduledTaskAction "
        f"-Execute '{py_esc}' -Argument '-m worker' -WorkingDirectory '{repo_esc}'; "
        f"$trigger = New-ScheduledTaskTrigger -AtStartup; "
        f"$settings = New-ScheduledTaskSettingsSet "
        f"-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; "
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' "
        f"-Action $action -Trigger $trigger -Settings $settings -Force | Out-Null"
    )

    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            check=True,
            capture_output=True,
            timeout=20,
        )
        print(
            f"[Worker] Task Scheduler 등록 완료 — name={TASK_NAME}, "
            f"exe={python_exe}, working_dir={repo_dir}"
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("cp949", errors="ignore") or e.stderr.decode(
            "utf-8", errors="ignore"
        ) if e.stderr else ""
        print(f"[Worker] Task Scheduler 등록 실패: {stderr.strip()}")
    except Exception as e:
        print(f"[Worker] Task Scheduler 등록 예외: {type(e).__name__}: {e}")
