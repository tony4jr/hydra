"""원격 명령 핸들러 — heartbeat 응답으로 받은 pending_commands 처리.

각 명령은 짧은 동작 (수 초~수십 초). 오래 걸리는 작업(diag/preload) 은
subprocess 로 비동기 실행 + 즉시 ack (실행 시작) 하는 식이 안전.

설계:
- 명령 실행 중 예외 → status=failed, error_message
- 실행 후 ack POST
- restart/update_now 는 ack 직후 sys.exit (Task Scheduler 가 재시작)
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worker.client import ServerClient


_REPO_DIR = r"C:\hydra" if sys.platform == "win32" else os.path.dirname(os.path.dirname(__file__))


async def execute_command(client: "ServerClient", cmd: dict) -> None:
    """명령 1개 실행 + ack. 실패해도 본체 흐름 영향 X."""
    cmd_id = cmd["id"]
    name = cmd["command"]
    payload = cmd.get("payload") or {}
    status = "done"
    result: str | None = None
    err: str | None = None

    try:
        if name == "restart":
            _ack(client, cmd_id, "done", "restarting...")
            print("[Worker] restart command — exit(0)")
            sys.exit(0)

        elif name == "update_now":
            result = _run_update()

        elif name == "run_diag":
            # diag 스크립트 비동기 실행 — 결과는 별도로 worker_errors 에 업로드
            script = payload.get("script", "diag_adspower_profiles.py")
            _spawn_diag(script)
            result = f"spawned {script}"

        elif name == "retry_task":
            # 서버 측에서 처리 (POST /tasks/v2/retry?task_id=) — 워커는 ack 만
            result = "retry handled by server side"

        elif name == "screenshot_now":
            # 현재 활성 브라우저 캡처는 WorkerSession 컨텍스트가 필요.
            # 단독 실행은 어려우므로 메시지만 ack — 향후 WorkerApp 의 current_session 활용.
            result = "screenshot_now: no active session" if not _has_active_session(client) else "captured"

        elif name == "stop_all_browsers":
            result = await _adspower_stop_all()

        elif name == "refresh_fingerprint":
            profile_ids = payload.get("profile_ids", [])
            result = await _adspower_new_fingerprint(profile_ids)

        elif name == "update_adspower_patch":
            version_type = payload.get("version_type", "stable")
            result = await _adspower_update_patch(version_type)

        else:
            status = "failed"
            err = f"unknown command: {name}"

    except SystemExit:
        raise
    except Exception as e:
        import traceback as _tb
        status = "failed"
        err = f"{type(e).__name__}: {e}"
        result = _tb.format_exc()[:1000]

    _ack(client, cmd_id, status, result, err)


def _ack(client: "ServerClient", cmd_id: int, status: str,
         result: str | None = None, err: str | None = None) -> None:
    try:
        client._request(
            "POST", f"/api/workers/command/{cmd_id}/ack",
            headers=client.headers,
            json={"status": status, "result": result, "error_message": err},
        )
    except Exception:
        pass


def _run_update() -> str:
    """git pull + pip install + sys.exit (Task Scheduler 가 재시작)."""
    subprocess.check_call(["git", "-C", _REPO_DIR, "fetch", "origin", "main"], timeout=60)
    prev = subprocess.check_output(
        ["git", "-C", _REPO_DIR, "rev-parse", "HEAD"], timeout=10).decode().strip()
    subprocess.check_call(
        ["git", "-C", _REPO_DIR, "reset", "--hard", "origin/main"], timeout=30)
    new = subprocess.check_output(
        ["git", "-C", _REPO_DIR, "rev-parse", "HEAD"], timeout=10).decode().strip()
    if prev == new:
        return f"already on {new[:7]}"
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-e", _REPO_DIR, "--quiet"], timeout=300)
    # ack 후 exit
    return f"updated {prev[:7]} → {new[:7]}, exiting"


def _spawn_diag(script: str) -> None:
    """진단 스크립트 비동기 실행 — 결과는 스크립트 자체가 worker_errors 로 업로드."""
    script_path = os.path.join(_REPO_DIR, "scripts", script)
    if sys.platform == "win32":
        py = os.path.join(_REPO_DIR, ".venv", "Scripts", "python.exe")
    else:
        py = sys.executable
    if not os.path.isfile(script_path):
        raise FileNotFoundError(script_path)
    subprocess.Popen([py, script_path], cwd=_REPO_DIR,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _has_active_session(client: "ServerClient") -> bool:
    return False  # placeholder — 실제로는 WorkerApp 에서 주입


async def _adspower_stop_all() -> str:
    import httpx
    base = os.environ.get("ADSPOWER_API_URL", "http://127.0.0.1:50325")
    key = os.environ.get("ADSPOWER_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{base}/api/v2/browser-profile/stop-all", headers=headers)
        return f"http {r.status_code}: {r.text[:200]}"


async def _adspower_new_fingerprint(profile_ids: list[str]) -> str:
    import httpx
    base = os.environ.get("ADSPOWER_API_URL", "http://127.0.0.1:50325")
    key = os.environ.get("ADSPOWER_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{base}/api/v2/browser-profile/new-fingerprint",
            headers=headers,
            json={"profile_id": profile_ids},
        )
        return f"http {r.status_code}: {r.text[:200]}"


async def _adspower_update_patch(version_type: str) -> str:
    import httpx
    base = os.environ.get("ADSPOWER_API_URL", "http://127.0.0.1:50325")
    key = os.environ.get("ADSPOWER_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{base}/api/v2/browser-profile/update-patch",
            headers=headers,
            json={"version_type": version_type},
        )
        return f"http {r.status_code}: {r.text[:300]}"
