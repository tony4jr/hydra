"""Desktop Worker Launcher — Slice 2.4.

Admin Agent (`worker.admin_agent`) 가 같은 PC 의 Desktop Worker (`python -m worker`)
프로세스를 start / stop / restart / status 관리.

scope:
  - Desktop Worker process 만 관리. Admin Agent 자신/Windows Service/NSSM/
    Task Scheduler disable 은 **절대** 안 만짐.
  - Slice 2.5 의 cutover (기존 HydraWorker Task Scheduler disable / update
    ownership 이전) 는 out of scope.

process 식별:
  - command line 이 `python -m worker` 또는 `worker/__main__.py` / `worker/app.py`
    desktop worker 패턴.
  - `worker.admin_agent` 는 명시적으로 **제외** (agent 가 자기 자신 kill 방지).
  - Windows venv launcher 가 `C:\\hydra\\.venv\\Scripts\\python.exe -m worker`
    parent 와 `C:\\Python311\\python.exe -m worker` child 를 동시에 노출하는
    경우가 있어 parent/child match 는 top-level PID 만 반환.

env 정책 (start 시):
  - HYDRA_DISABLE_TASK_REGISTER=1
  - HYDRA_UPDATE_OWNER=agent
  - HYDRA_AGENT_WORKER_TOKEN 은 **절대 HYDRA_WORKER_TOKEN 으로 복사 안 함**
    (desktop 은 자신의 secrets.enc / desktop env 사용).

return: JSON-serializable dict.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import psutil  # type: ignore
    _PSUTIL_AVAILABLE = True
except Exception:
    psutil = None  # type: ignore
    _PSUTIL_AVAILABLE = False


# Desktop worker 식별 토큰. 이것들 중 하나라도 cmdline 에 있고 'admin_agent' 가
# 없으면 desktop 으로 간주.
_DESKTOP_MATCHERS = (
    "-m worker",            # python -m worker (가장 일반)
    "worker/__main__.py",   # 일부 환경에서 module 경로 직접
    "worker\\__main__.py",  # Windows backslash
    "worker/app.py",
    "worker\\app.py",
)
_ADMIN_AGENT_MARKER = "admin_agent"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_venv_python() -> str:
    root = _repo_root()
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",   # Windows venv
        root / ".venv" / "bin" / "python",            # POSIX venv
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return sys.executable


def _cmdline_is_desktop(cmdline: list[str]) -> bool:
    """cmdline list 가 desktop worker 패턴인지. admin_agent 는 명시적 제외."""
    if not cmdline:
        return False
    joined = " ".join(cmdline)
    if _ADMIN_AGENT_MARKER in joined:
        return False
    return any(token in joined for token in _DESKTOP_MATCHERS)


def _find_desktop_pids() -> list[int]:
    """현재 running desktop worker process 의 PID list. admin_agent 는 제외.

    psutil 가 있으면 사용 (정확). 없으면 빈 list (운영상 admin agent 환경엔
    psutil 항상 있음 — preflight 가 import 함).
    """
    matches: dict[int, int | None] = {}
    if not _PSUTIL_AVAILABLE:
        return []
    for proc in psutil.process_iter(["pid", "ppid", "name", "cmdline"]):
        try:
            info = proc.info
            cmdline = info.get("cmdline") or []
            if _cmdline_is_desktop(cmdline):
                pid = int(info["pid"])
                ppid_raw = info.get("ppid")
                matches[pid] = int(ppid_raw) if ppid_raw is not None else None
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            continue
    # Windows venv launcher may show as two matching Python processes:
    #   venv python.exe -m worker -> base Python311 python.exe -m worker
    # Treat that as one desktop worker and manage the top-level process.
    matched_pids = set(matches)
    return sorted(pid for pid, ppid in matches.items() if ppid not in matched_pids)


# ───────── public API ─────────


def desktop_status() -> dict[str, Any]:
    """현재 desktop worker 실행 여부 + PID list."""
    pids = _find_desktop_pids()
    out: dict[str, Any] = {
        "ok": _PSUTIL_AVAILABLE,
        "action": "status",
        "running": bool(pids),
        "pids": pids,
        "psutil_available": _PSUTIL_AVAILABLE,
    }
    if not _PSUTIL_AVAILABLE:
        out["error"] = "psutil unavailable — process detection unreliable"
    return out


def desktop_start() -> dict[str, Any]:
    """desktop worker 시작. 이미 running 이면 no-op.

    env 주입:
      - HYDRA_DISABLE_TASK_REGISTER=1
      - HYDRA_UPDATE_OWNER=agent
      - HYDRA_PROCESS_ROLE=desktop_worker (commands.py 의 desktop_* 분기 guard)
    agent token 류는 child env 에서 명시 제거:
      - HYDRA_AGENT_WORKER_TOKEN (어떤 경우든 pop — desktop 에 leak 안 됨)
      - HYDRA_ADMIN_AGENT_TOKEN (pop)
      - HYDRA_WORKER_TOKEN 이 agent token 과 같으면 pop (desktop 의 자기 token
        과 다르면 유지)

    Slice 2.4 follow-up — fail-closed: psutil 미설치면 중복 detection 불가 →
    desktop_start 가 spawn 거부. status 만 가능.
    """
    if not _PSUTIL_AVAILABLE:
        return {
            "ok": False,
            "action": "start",
            "running": False,
            "pids": [],
            "started_pid": None,
            "psutil_available": False,
            "error": "psutil unavailable — refuse to spawn (duplicate detection impossible)",
        }
    existing = _find_desktop_pids()
    if existing:
        return {
            "ok": True,
            "action": "start",
            "running": True,
            "pids": existing,
            "started_pid": None,
            "message": "already running, no-op",
        }

    python = _resolve_venv_python()
    repo = str(_repo_root())

    # env: 부모 env 복제 후 override + agent token leak 차단.
    env = dict(os.environ)
    env["HYDRA_DISABLE_TASK_REGISTER"] = "1"
    env["HYDRA_UPDATE_OWNER"] = "agent"
    env["HYDRA_PROCESS_ROLE"] = "desktop_worker"

    # Slice 2.4 follow-up — agent token 류는 child env 에 absolutely 남기지 않음.
    # worker.config 가 안 읽더라도 process 환경에 token 평문 leak 자체 차단.
    agent_token = env.pop("HYDRA_AGENT_WORKER_TOKEN", "") or env.pop(
        "HYDRA_ADMIN_AGENT_TOKEN", ""
    )
    # HYDRA_ADMIN_AGENT_TOKEN 이 별도로도 있을 수 있어 한 번 더 pop
    env.pop("HYDRA_ADMIN_AGENT_TOKEN", None)
    # WORKER_TOKEN 이 agent token 과 동일하면 pop. 다른 desktop token 이면 유지.
    desktop_token = env.get("HYDRA_WORKER_TOKEN", "")
    if agent_token and desktop_token == agent_token:
        env.pop("HYDRA_WORKER_TOKEN", None)
    # Slice 2.4 follow-up #2 — admin_agent fallback path:
    # admin_agent token 우선순위가 AGENT_WORKER_TOKEN > ADMIN_AGENT_TOKEN >
    # HYDRA_WORKER_TOKEN. service 가 마지막 fallback (HYDRA_WORKER_TOKEN) 만
    # 박혀있는 경우, 부모 process role 이 admin_agent 면 그 token 자체가
    # agent token 이므로 child desktop env 에서도 pop 해야 leak 차단.
    parent_role = os.environ.get("HYDRA_PROCESS_ROLE", "")
    if (
        parent_role == "admin_agent"
        and not agent_token
        and env.get("HYDRA_WORKER_TOKEN")
    ):
        env.pop("HYDRA_WORKER_TOKEN", None)

    cmd = [python, "-m", "worker"]
    creationflags = 0
    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        cmd,
        cwd=repo,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )
    return {
        "ok": True,
        "action": "start",
        "running": True,
        "pids": [proc.pid],
        "started_pid": proc.pid,
        "message": f"started pid={proc.pid}",
    }


def desktop_stop(timeout_sec: int = 15) -> dict[str, Any]:
    """desktop worker 종료. graceful 우선 → timeout 후 force.

    admin_agent process 는 *_find_desktop_pids* 가 이미 제외하므로 안전.
    psutil 미설치 시 fail-closed — 빈 list 가 진짜 no-op 인지 detection 실패인지
    구분 불가, 거짓 성공 방지.
    """
    if not _PSUTIL_AVAILABLE:
        return {
            "ok": False,
            "action": "stop",
            "running": False,
            "pids": [],
            "stopped_pids": [],
            "psutil_available": False,
            "error": "psutil unavailable — process detection impossible, refuse to claim stop",
        }
    pids = _find_desktop_pids()
    if not pids:
        return {
            "ok": True,
            "action": "stop",
            "running": False,
            "pids": [],
            "stopped_pids": [],
            "message": "no desktop worker running",
        }

    stopped: list[int] = []
    forced: list[int] = []

    # 1) graceful
    for pid in pids:
        try:
            if sys.platform == "win32":
                # taskkill without /F = graceful (WM_CLOSE)
                subprocess.run(
                    ["taskkill", "/PID", str(pid)],
                    capture_output=True, timeout=5,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            continue

    # 2) wait
    deadline = time.monotonic() + max(1, int(timeout_sec))
    remaining = list(pids)
    while remaining and time.monotonic() < deadline:
        still_running = _find_desktop_pids()
        # 우리가 stop 요청한 pid 중 still_running 에 없는 것 = 종료됨.
        remaining = [p for p in remaining if p in still_running]
        if not remaining:
            break
        time.sleep(0.5)

    stopped = [p for p in pids if p not in remaining]

    # 3) force kill remaining
    for pid in remaining:
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, timeout=5,
                )
            else:
                os.kill(pid, signal.SIGKILL)
            forced.append(pid)
            stopped.append(pid)
        except Exception:
            continue

    return {
        "ok": True,
        "action": "stop",
        "running": False,
        "pids": [],
        "stopped_pids": sorted(set(stopped)),
        "forced_pids": forced,
        "message": (
            f"stopped {len(stopped)} pid(s)" if not forced
            else f"stopped {len(stopped)} pid(s), forced {len(forced)}"
        ),
    }


def desktop_restart(timeout_sec: int = 15) -> dict[str, Any]:
    """stop + start. graceful timeout 적용. stop 실패 시 start 시도 안 함."""
    if not _PSUTIL_AVAILABLE:
        return {
            "ok": False,
            "action": "restart",
            "running": False,
            "pids": [],
            "psutil_available": False,
            "error": "psutil unavailable — refuse to restart",
        }
    stop_result = desktop_stop(timeout_sec=timeout_sec)
    if not stop_result.get("ok", False):
        return {
            "ok": False,
            "action": "restart",
            "running": False,
            "pids": [],
            "stopped_pids": stop_result.get("stopped_pids", []),
            "error": (
                f"restart aborted — stop failed: {stop_result.get('error', stop_result.get('message',''))}"
            ),
        }
    # 시작 직전 race 회피용 잠깐 sleep (NSSM 의 restart delay 와 비슷).
    time.sleep(1.0)
    start_result = desktop_start()
    return {
        "ok": stop_result.get("ok", False) and start_result.get("ok", False),
        "action": "restart",
        "running": start_result.get("running", False),
        "pids": start_result.get("pids", []),
        "started_pid": start_result.get("started_pid"),
        "stopped_pids": stop_result.get("stopped_pids", []),
        "forced_pids": stop_result.get("forced_pids", []),
        "message": f"stop: {stop_result.get('message','')} | start: {start_result.get('message','')}",
    }
