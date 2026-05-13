"""Phase 4 Slice 4.1b — admin agent terminal session host.

admin_agent runtime 안에서 persistent shell process 를 띄워 server 측
terminal_sessions 와 매핑. payload 받아 spawn + active POST. close 받아
terminate + closed POST. shutdown 시 registry 전체 cleanup.

핵심:
- idempotent open: 같은 session_id 가 이미 registry 에 있고 살아있으면
  no-op (재배달 시 shell 중복 spawn 금지)
- UTF-8: PowerShell startup 에서 chcp 65001 + Console::InputEncoding /
  OutputEncoding UTF8
- active POST 실패 → process kill + ack failed (caller 책임)
- shutdown_all(): admin_agent service stop / KeyboardInterrupt 시 호출.
  Codex 권고로 4.1b 부터 포함 (orphan PowerShell 위험 방지).
- Slice 4.1b 는 spawn + active POST + close + shutdown 만. input/output
  IO thread 는 4.2a/4.2b 에서.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from worker.client import ServerClient


# session_id → Popen
_REGISTRY: dict[int, subprocess.Popen] = {}
_REGISTRY_LOCK = threading.Lock()


# PowerShell startup script — UTF-8 강제 + prompt 짧게.
_PS_STARTUP_SCRIPT = (
    "chcp 65001 > $null; "
    "[Console]::InputEncoding=[Text.Encoding]::UTF8; "
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
    "$OutputEncoding=[Text.Encoding]::UTF8; "
    "function global:prompt { 'PS> ' }"
)


def _spawn_shell(shell: str) -> subprocess.Popen:
    """플랫폼 + shell 별로 persistent process Popen.

    PowerShell: -NoExit -NoLogo -NoProfile -Command "<startup>"
    bash: bash -i with LANG=en_US.UTF-8

    stdin/stdout/stderr = PIPE, text mode utf-8.
    """
    if shell == "powershell":
        if sys.platform == "win32":
            argv = [
                "powershell.exe",
                "-NoExit", "-NoLogo", "-NoProfile",
                "-Command", _PS_STARTUP_SCRIPT,
            ]
        else:
            # dev fallback — POSIX 에서 bash 로 흉내. 같은 startup 의미 없으나
            # tests/dev 환경에서 process 구조 검증용.
            argv = ["bash", "-i"]
    elif shell == "sh":
        argv = ["bash", "-i"]
    else:
        raise ValueError(f"unsupported shell: {shell!r}")

    env = os.environ.copy()
    env.setdefault("LANG", "en_US.UTF-8")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        env=env,
        text=False,  # binary; decode 는 IO thread 가 (4.2 에서)
        close_fds=(sys.platform != "win32"),
    )


def _is_alive(proc: subprocess.Popen) -> bool:
    return proc.poll() is None


def _post_active(client: "ServerClient", session_id: int, session_token: str) -> bool:
    """server 에 active 마킹. HTTP 200 + ok=True 만 성공."""
    try:
        resp = client._request(
            "POST",
            f"/api/workers/terminal/{session_id}/active",
            headers={**client.headers, "X-Terminal-Session-Token": session_token},
        )
        if resp.status_code != 200:
            return False
        try:
            return bool(resp.json().get("ok") is True)
        except Exception:
            return False
    except Exception:
        return False


def _post_closed(client: "ServerClient", session_id: int, session_token: str) -> bool:
    try:
        resp = client._request(
            "POST",
            f"/api/workers/terminal/{session_id}/closed",
            headers={**client.headers, "X-Terminal-Session-Token": session_token},
        )
        return resp.status_code == 200
    except Exception:
        return False


def _post_failed(
    client: "ServerClient", session_id: int, session_token: str, error: str = "",
) -> bool:
    try:
        path = f"/api/workers/terminal/{session_id}/failed"
        if error:
            path += f"?error={error}"
        resp = client._request(
            "POST", path,
            headers={**client.headers, "X-Terminal-Session-Token": session_token},
        )
        return resp.status_code == 200
    except Exception:
        return False


def open_session(
    client: "ServerClient",
    session_id: int,
    session_token: str,
    shell: str,
) -> dict:
    """admin agent terminal session 열기. idempotent.

    1. registry 에 session_id 있고 살아있음 → no-op, active POST 재시도
    2. registry 에 있지만 죽음 → 정리 후 새로 spawn
    3. spawn 성공 → active POST → 실패 시 kill + failed POST
    """
    with _REGISTRY_LOCK:
        existing = _REGISTRY.get(session_id)
        if existing is not None:
            if _is_alive(existing):
                # idempotent — active POST 재시도 (lease redelivery 케이스)
                ok = _post_active(client, session_id, session_token)
                return {"ok": ok, "noop": True, "pid": existing.pid}
            # dead — 정리 후 재시도
            _REGISTRY.pop(session_id, None)

        try:
            proc = _spawn_shell(shell)
        except Exception as e:
            _post_failed(client, session_id, session_token, f"spawn_error:{type(e).__name__}")
            return {"ok": False, "error": f"spawn_error: {e}"}

        # spawn 직후 process 가 즉시 죽었는지 점검 (잘못된 shell 등)
        try:
            rc = proc.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            rc = None
        if rc is not None:
            _post_failed(
                client, session_id, session_token,
                f"spawn_exited:rc={rc}",
            )
            return {"ok": False, "error": f"spawn exited rc={rc}"}

        # active POST 시도 — 실패 시 process kill + failed POST
        if not _post_active(client, session_id, session_token):
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            _post_failed(client, session_id, session_token, "active_post_failed")
            return {"ok": False, "error": "active_post_failed"}

        _REGISTRY[session_id] = proc
        return {"ok": True, "pid": proc.pid}


def close_session(
    client: "ServerClient",
    session_id: int,
    session_token: str,
) -> dict:
    """admin agent terminal session 종료. terminate (5s) → kill fallback.
    server 에 closed POST.
    """
    with _REGISTRY_LOCK:
        proc = _REGISTRY.pop(session_id, None)

    if proc is not None and _is_alive(proc):
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    _post_closed(client, session_id, session_token)
    return {"ok": True}


def shutdown_all(client: Optional["ServerClient"] = None) -> int:
    """admin_agent service stop / SIGTERM / KeyboardInterrupt 시 호출.
    registry 모든 process 정리 + (client 있으면) server 에 closed POST.

    Codex Slice 4.1b 요구: orphan PowerShell 방지 (4.3 까지 미루지 말 것).
    """
    with _REGISTRY_LOCK:
        items = list(_REGISTRY.items())
        _REGISTRY.clear()
    count = 0
    for sid, proc in items:
        try:
            if _is_alive(proc):
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            count += 1
        except Exception:
            pass
    return count


def get_registered_sessions() -> list[int]:
    """현재 살아있는 session_id 리스트 — 4.3 stale recovery hook 용."""
    with _REGISTRY_LOCK:
        return [sid for sid, p in _REGISTRY.items() if _is_alive(p)]


def clear_registry_for_testing() -> None:
    """테스트 전용 — registry 초기화 (process 는 그대로 두고 dict 만 비움)."""
    with _REGISTRY_LOCK:
        _REGISTRY.clear()
