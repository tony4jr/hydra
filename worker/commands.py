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
            # 본질 fix: update_now 가 _run_update 의 단순 string return 만 받으면
            # 코드는 받지만 메모리 옛 코드 그대로 → 사용자가 별도 restart 필요했음.
            # perform_update 호출 = git pull + pip install + Task Scheduler restart 예약
            # + sys.exit(0). update 완료까지 ack 못 보내는 것은 의도 — restart 후
            # 새 프로세스가 자기 시작 보고하면 됨.
            from worker.updater import perform_update
            _ack(client, cmd_id, "done", "update_now: invoking perform_update, will exit")
            perform_update()
            # already-on-main no-op 케이스는 perform_update 가 exit 없이 return
            result = "update_now: already on origin/main"

        elif name == "ensure_schema":
            # PR-AutoSchema: server 가 워커에 schema 재보장 명령. stdout 결과 ack 로 보고.
            from worker.app import _ensure_local_schema
            try:
                _ensure_local_schema()
                result = "schema ensured"
            except Exception as e:
                result = f"failed: {type(e).__name__}: {e}"

        elif name == "run_diag":
            # PR-Preflight: 워커 즉시 진단 → 결과 ack message + worker_error 보고.
            # admin 이 진단 트리거 후 결과 즉시 확인 가능.
            mode = payload.get("mode", "preflight")
            if mode == "preflight":
                try:
                    from worker.preflight import collect_health
                    health = collect_health()
                    import json as _json
                    result = _json.dumps(health, ensure_ascii=False)
                    # worker_error 로도 같이 (kind=diagnostic) — admin UI 에서 보기 쉽게.
                    try:
                        client.report_error(
                            kind="diagnostic",
                            message=f"run_diag preflight: adb={health.get('adb_devices')} "
                                    f"adspower={health.get('adspower_version')} "
                                    f"cpu={health.get('cpu_percent')}%",
                            context=health,
                        )
                    except Exception:
                        pass
                except Exception as e:
                    result = f"preflight failed: {type(e).__name__}: {e}"
            else:
                # legacy script path
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

        elif name == "shell_exec":
            # Slice 1 — 원격 PowerShell 단발 실행. 결과 JSON 반환.
            shell = payload.get("shell", "powershell")
            script = payload.get("script", "")
            timeout_sec = int(payload.get("timeout_sec", 30))
            result = _run_shell_exec(shell=shell, script=script, timeout_sec=timeout_sec)

        elif name == "agent_self_restart":
            # Slice 3.3 — admin agent 자기 자신 NSSM restart.
            # Codex 권고: ack-then-spawn. helper 를 ack 후에만 띄움.
            import json as _json
            current_role = os.environ.get("HYDRA_PROCESS_ROLE", "")
            if current_role != "admin_agent":
                _ack(
                    client, cmd_id, "failed", None,
                    f"agent_self_restart requires admin_agent runtime "
                    f"(HYDRA_PROCESS_ROLE={current_role!r})",
                )
                return
            # ack 전 검증: nssm path resolve (못 찾으면 helper 가 들고 가도
            # 결과 못 받음 → 미리 fail 처리).
            from worker.agent_self_restart import (
                ADMIN_AGENT_SERVICE_NAME, resolve_nssm_path,
                helper_log_path, spawn_restart_helper,
            )
            try:
                nssm_path = resolve_nssm_path()
            except RuntimeError as e:
                _ack(client, cmd_id, "failed", None, str(e))
                return

            delay_sec = int(payload.get("delay_sec", 3))
            if not (1 <= delay_sec <= 60):
                _ack(client, cmd_id, "failed", None, f"delay_sec out of range: {delay_sec}")
                return
            log_path = helper_log_path()
            service_name = ADMIN_AGENT_SERVICE_NAME  # payload 의 service_name 무시 (보안)

            scheduled = {
                "status": "restart_scheduled",
                "delay_sec": delay_sec,
                "service_name": service_name,
                "nssm_path": nssm_path,
                "helper_log": log_path,
            }
            # ack 먼저 — 성공 시에만 spawn.
            ok = _ack(client, cmd_id, "done", _json.dumps(scheduled, ensure_ascii=False))
            if not ok:
                # ack 실패 → spawn 하지 않음. 다음 lease 만료 후 non-redeliverable
                # 정책에 의해 failed 처리됨.
                return
            try:
                spawn_restart_helper(
                    nssm_path=nssm_path,
                    service_name=service_name,
                    delay_sec=delay_sec,
                    log_path=log_path,
                )
            except Exception as e:
                # ack 이미 done. 실제 restart 실패는 운영자가 helper_log 확인 가능
                # + worker_error 로 알람.
                try:
                    client.report_error(
                        kind="update_fail",
                        message=f"agent_self_restart helper spawn failed: "
                                f"{type(e).__name__}: {e}",
                        context={
                            "service_name": service_name,
                            "nssm_path": nssm_path,
                            "helper_log": log_path,
                        },
                    )
                except Exception:
                    pass
            return

        elif name in ("desktop_cutover_status", "desktop_cutover_apply", "agent_update_now"):
            # Slice 2.5 — Cutover + agent-owned update. admin_agent runtime 전용.
            import json as _json
            current_role = os.environ.get("HYDRA_PROCESS_ROLE", "")
            if current_role != "admin_agent":
                status = "failed"
                err = (
                    f"{name} requires admin_agent runtime "
                    f"(HYDRA_PROCESS_ROLE={current_role!r})"
                )
                result = _json.dumps(
                    {"ok": False, "action": name, "error": err,
                     "process_role": current_role},
                    ensure_ascii=False,
                )
            elif name == "desktop_cutover_status":
                from worker.scheduler_cutover import cutover_status
                result = _json.dumps(cutover_status(), ensure_ascii=False)
            elif name == "desktop_cutover_apply":
                from worker.scheduler_cutover import cutover_apply
                result = _json.dumps(
                    cutover_apply(
                        dry_run=bool(payload.get("dry_run", False)),
                        start_desktop=bool(payload.get("start_desktop", True)),
                        delete=bool(payload.get("delete", False)),
                    ),
                    ensure_ascii=False,
                )
            elif name == "agent_update_now":
                from worker.agent_update import agent_update_now
                # restart_agent option 은 Slice 2.5 review 권장 A 로 제거.
                # agent self-restart 는 별도 NSSM service restart 로 분리.
                result = _json.dumps(
                    agent_update_now(
                        dry_run=bool(payload.get("dry_run", False)),
                    ),
                    ensure_ascii=False,
                )

        elif name in ("desktop_status", "desktop_start", "desktop_stop", "desktop_restart"):
            # Slice 2.4 — admin agent → desktop worker process 관리.
            # Slice 2.4 follow-up: HYDRA_PROCESS_ROLE guard. 서버 routing 이
            # worker_id 단일이라 잘못된 id 발행 시 desktop 이 자기 자신 stop/
            # restart 시도할 수 있음 → 명시 차단.
            import json as _json
            current_role = os.environ.get("HYDRA_PROCESS_ROLE", "")
            if current_role != "admin_agent":
                status = "failed"
                err = (
                    f"desktop_* requires admin_agent runtime "
                    f"(HYDRA_PROCESS_ROLE={current_role!r})"
                )
                result = _json.dumps(
                    {"ok": False, "action": name, "error": err,
                     "process_role": current_role},
                    ensure_ascii=False,
                )
            elif name == "desktop_status":
                from worker.desktop_launcher import desktop_status
                result = _json.dumps(desktop_status(), ensure_ascii=False)
            elif name == "desktop_start":
                from worker.desktop_launcher import desktop_start
                result = _json.dumps(desktop_start(), ensure_ascii=False)
            elif name == "desktop_stop":
                from worker.desktop_launcher import desktop_stop
                timeout_sec = int(payload.get("timeout_sec", 15))
                result = _json.dumps(desktop_stop(timeout_sec=timeout_sec), ensure_ascii=False)
            elif name == "desktop_restart":
                from worker.desktop_launcher import desktop_restart
                timeout_sec = int(payload.get("timeout_sec", 15))
                result = _json.dumps(desktop_restart(timeout_sec=timeout_sec), ensure_ascii=False)

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
         result: str | None = None, err: str | None = None) -> bool:
    """ack 시도. Slice 3.3 — bool 반환 (호환: 옛 호출자는 무시).

    True 조건: HTTP 200 + response json 의 ok == True.
    False: 그 외 (5xx, 4xx, 네트워크 실패, ok 누락).
    """
    try:
        resp = client._request(
            "POST", f"/api/workers/command/{cmd_id}/ack",
            headers=client.headers,
            json={"status": status, "result": result, "error_message": err},
        )
        if resp.status_code != 200:
            return False
        try:
            body = resp.json()
        except Exception:
            return False
        return bool(body.get("ok") is True)
    except Exception:
        return False


# Slice 1 — shell_exec implementation -------------------------------------
SHELL_MAX_SCRIPT_LEN = 8000
SHELL_MAX_TIMEOUT_SEC = 120
SHELL_OUTPUT_CAP_BYTES = 64 * 1024  # 64KB per stream


def _run_shell_exec(*, shell: str, script: str, timeout_sec: int) -> str:
    """단발 shell command 실행. JSON 문자열 반환 (ack result 로 그대로 들어감).

    반환 schema (str):
      {"exit_code": int, "stdout": str, "stderr": str, "truncated": bool,
       "duration_ms": int, "shell": str, "error": str?}

    가드:
      - script 길이 SHELL_MAX_SCRIPT_LEN 초과 시 reject (errcode=-2)
      - timeout_sec 1..SHELL_MAX_TIMEOUT_SEC 외 reject (errcode=-3)
      - stdout/stderr 각각 SHELL_OUTPUT_CAP_BYTES 초과 시 잘림 + truncated=True
      - timeout 발생 시 exit_code=-1 + error="timeout"

    plaintext credentials/secret 흘림 방지는 호출자 책임 (UI/admin guard).
    """
    import json as _json

    def _pack(exit_code: int, stdout: str = "", stderr: str = "",
              truncated: bool = False, duration_ms: int = 0,
              error: str | None = None) -> str:
        obj: dict = {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": truncated,
            "duration_ms": duration_ms,
            "shell": shell,
        }
        if error is not None:
            obj["error"] = error
        return _json.dumps(obj, ensure_ascii=False)

    if not isinstance(script, str) or not script:
        return _pack(-2, error="empty script")
    if len(script) > SHELL_MAX_SCRIPT_LEN:
        return _pack(-2, error=f"script length {len(script)} exceeds {SHELL_MAX_SCRIPT_LEN}")
    if not (1 <= timeout_sec <= SHELL_MAX_TIMEOUT_SEC):
        return _pack(-3, error=f"timeout_sec must be 1..{SHELL_MAX_TIMEOUT_SEC}")

    if shell == "powershell":
        if sys.platform == "win32":
            argv = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]
        else:
            # dev/non-Windows fallback — sh 로 흉내. 결과 schema 유지.
            argv = ["sh", "-c", script]
    elif shell == "sh":
        argv = ["sh", "-c", script]
    else:
        return _pack(-4, error=f"unsupported shell: {shell}")

    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        dur = int((time.monotonic() - start) * 1000)
        stdout_b = (e.stdout or b"")[:SHELL_OUTPUT_CAP_BYTES]
        stderr_b = (e.stderr or b"")[:SHELL_OUTPUT_CAP_BYTES]
        truncated = (
            len(e.stdout or b"") > SHELL_OUTPUT_CAP_BYTES
            or len(e.stderr or b"") > SHELL_OUTPUT_CAP_BYTES
        )
        return _pack(
            exit_code=-1,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            truncated=truncated,
            duration_ms=dur,
            error="timeout",
        )
    except FileNotFoundError as e:
        return _pack(-5, duration_ms=int((time.monotonic() - start) * 1000),
                     error=f"shell not found: {e}")

    dur = int((time.monotonic() - start) * 1000)
    stdout_b = (proc.stdout or b"")[:SHELL_OUTPUT_CAP_BYTES]
    stderr_b = (proc.stderr or b"")[:SHELL_OUTPUT_CAP_BYTES]
    truncated = (
        len(proc.stdout or b"") > SHELL_OUTPUT_CAP_BYTES
        or len(proc.stderr or b"") > SHELL_OUTPUT_CAP_BYTES
    )
    return _pack(
        exit_code=int(proc.returncode),
        stdout=stdout_b.decode("utf-8", errors="replace"),
        stderr=stderr_b.decode("utf-8", errors="replace"),
        truncated=truncated,
        duration_ms=dur,
    )


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
    from hydra.browser.adspower import _normalize_api_key
    key = _normalize_api_key(os.environ.get("ADSPOWER_API_KEY", ""))
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{base}/api/v2/browser-profile/stop-all", headers=headers)
        return f"http {r.status_code}: {r.text[:200]}"


async def _adspower_new_fingerprint(profile_ids: list[str]) -> str:
    import httpx
    base = os.environ.get("ADSPOWER_API_URL", "http://127.0.0.1:50325")
    from hydra.browser.adspower import _normalize_api_key
    key = _normalize_api_key(os.environ.get("ADSPOWER_API_KEY", ""))
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
    from hydra.browser.adspower import _normalize_api_key
    key = _normalize_api_key(os.environ.get("ADSPOWER_API_KEY", ""))
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{base}/api/v2/browser-profile/update-patch",
            headers=headers,
            json={"version_type": version_type},
        )
        return f"http {r.status_code}: {r.text[:300]}"
