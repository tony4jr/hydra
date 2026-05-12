"""Slice 2.5 — Legacy HydraWorker Task Scheduler cutover.

기존 Task Scheduler 가 desktop worker 를 띄우면 Admin Agent 가 띄운 것과
중복 실행/heartbeat race. cutover module 은:

  1) HydraWorker scheduled task 를 stop + disable (delete 는 explicit option).
  2) 현재 떠있는 desktop process 를 desktop_launcher 로 stop.
  3) start_desktop=True 면 desktop_launcher 로 새 desktop 시작.

idempotent. 두 번 돌려도 안전. non-Windows 는 supported=False no-op.

Phase 3 의 target_role / capability dispatch 는 안 함. 여기선 단순히
admin_agent runtime 에서만 호출되는 정책 — commands.py guard 가 책임.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Any

# Windows ScheduledTasks PowerShell cmdlet 사용 우선. schtasks fallback.
TASK_NAME = "HydraWorker"


def _run_ps(script: str, timeout: int = 15) -> tuple[int, str, str]:
    """PowerShell 단발 실행 — (exit_code, stdout, stderr).

    test mock 대상. 실제 환경에선 Windows 만 의미 있음.
    """
    if sys.platform != "win32":
        return (-1, "", "non-windows")
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=timeout, text=True,
        )
        return (proc.returncode, proc.stdout or "", proc.stderr or "")
    except Exception as e:
        return (-2, "", f"{type(e).__name__}: {e}")


def _task_query() -> dict[str, Any]:
    """HydraWorker task 상태 query.

    Returns:
      {"ok": bool, "exists": bool, "state": str|None, "error": str|None}.
      rc != 0 (PowerShell/permission/missing module 등) 는 ok=False — 'task
      missing' 이 아닌 'query failed'. cutover_apply 는 이 경우 fail-closed.
      rc == 0 + stdout == 'NONE' 이 진짜 missing.
    """
    rc, out, err = _run_ps(
        f"$t = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue;"
        f" if ($t) {{ $t.State }} else {{ 'NONE' }}"
    )
    if rc != 0:
        return {
            "ok": False, "exists": False, "state": None,
            "error": (err or "").strip()[:300] or f"PowerShell rc={rc}",
        }
    state = (out or "").strip()
    if not state or state == "NONE":
        return {"ok": True, "exists": False, "state": None, "error": None}
    return {"ok": True, "exists": True, "state": state, "error": None}


def _task_last_run_info() -> dict[str, Any]:
    """간단한 last run info — 없으면 빈 dict."""
    rc, out, err = _run_ps(
        f"Get-ScheduledTaskInfo -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue |"
        f" Select-Object LastRunTime, NextRunTime, LastTaskResult |"
        f" ConvertTo-Json -Compress"
    )
    if rc != 0 or not out.strip():
        return {}
    import json as _json
    try:
        return _json.loads(out)
    except Exception:
        return {}


def cutover_status() -> dict[str, Any]:
    """현재 cutover 상태 보고.

    non-Windows: ok=True, supported=False (no-op).
    Windows: HydraWorker task 의 존재/상태 + desktop launcher 의 desktop_status
             summary 포함. query 자체가 실패하면 ok=False + error.
    """
    out: dict[str, Any] = {
        "ok": True,
        "action": "cutover_status",
        "task_name": TASK_NAME,
        "platform": sys.platform,
    }
    if sys.platform != "win32":
        out["supported"] = False
        out["message"] = "cutover only meaningful on Windows worker host"
        return out

    out["supported"] = True
    q = _task_query()
    out["query_ok"] = q["ok"]
    out["exists"] = q["exists"]
    out["state"] = q["state"]
    if q["error"]:
        out["error"] = q["error"]
        out["ok"] = False
    if q["ok"] and q["exists"]:
        out["last_run"] = _task_last_run_info()
    else:
        out["last_run"] = {}

    # desktop process 현황 — desktop_launcher.desktop_status 결과 그대로.
    try:
        from worker.desktop_launcher import desktop_status as _ds
        out["desktop"] = _ds()
    except Exception as e:
        out["desktop"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return out


def cutover_apply(
    *,
    dry_run: bool = False,
    start_desktop: bool = True,
    delete: bool = False,
) -> dict[str, Any]:
    """cutover sequence — idempotent.

    plan:
      1) HydraWorker task 가 있으면: Stop-ScheduledTask (running 이면 종료)
      2) HydraWorker task 가 있으면: Disable-ScheduledTask (또는 delete=True 면 Unregister)
      3) desktop_launcher.desktop_stop() — running desktop 정리
      4) start_desktop=True 면 desktop_launcher.desktop_start()

    dry_run=True 면 위 plan 만 반환, subprocess/launcher 호출 안 함.
    delete=True 는 default False — disable 이 reversible 이라 안전.
    """
    out: dict[str, Any] = {
        "ok": True,
        "action": "cutover_apply",
        "task_name": TASK_NAME,
        "platform": sys.platform,
        "dry_run": dry_run,
        "start_desktop": start_desktop,
        "delete": delete,
        "steps": [],
    }
    if sys.platform != "win32":
        out["supported"] = False
        out["message"] = "non-windows host — no-op"
        return out
    out["supported"] = True

    # ── dry_run: pure plan only. system query / subprocess / launcher 호출 X.
    if dry_run:
        planned: list[str] = [
            "query_task_state",
            "stop_scheduled_task_if_running",
            ("unregister_scheduled_task" if delete else "disable_scheduled_task"),
            "desktop_stop",
        ]
        if start_desktop:
            planned.append("desktop_start")
        out["planned_steps"] = planned
        out["message"] = "dry_run — no actions taken (pure plan, no system query)"
        return out

    # ── 1. task 상태 query (fail-closed)
    q = _task_query()
    out["initial_state"] = q["state"]
    out["initial_exists"] = q["exists"]
    if not q["ok"]:
        # query 자체 실패 — task 상태 모름. desktop_stop/start 진행하면 위험.
        out["ok"] = False
        out["error"] = f"task query failed: {q['error']}"
        return out

    exists, state = q["exists"], q["state"]

    # planned_steps 기록 (실제 실행 path 와 동기화)
    planned: list[str] = []
    if exists:
        if state and state.lower() == "running":
            planned.append("stop_scheduled_task")
        if delete:
            planned.append("unregister_scheduled_task")
        else:
            if not (state and state.lower() == "disabled"):
                planned.append("disable_scheduled_task")
    planned.append("desktop_stop")
    if start_desktop:
        planned.append("desktop_start")
    out["planned_steps"] = planned

    # ── 2. 실행 — scheduled-task mutation 은 fail-closed.
    # rc != 0 면 즉시 ok=False return, desktop_stop/start 절대 호출 X.
    # 이유: Task Scheduler 상태가 애매한데 agent 가 desktop 띄우면 중복 실행 위험
    # (Slice 2.5 의 핵심 목적 정면 위반).
    def step(label: str, rc: int, stdout: str = "", stderr: str = "") -> None:
        out["steps"].append({
            "step": label, "rc": rc,
            "stdout": (stdout or "").strip()[:500],
            "stderr": (stderr or "").strip()[:500],
        })

    def fail_closed(reason: str) -> dict[str, Any]:
        out["ok"] = False
        out["error"] = reason
        return out

    if exists:
        if state and state.lower() == "running":
            rc, so, se = _run_ps(
                f"Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue"
            )
            step("stop_scheduled_task", rc, so, se)
            if rc != 0:
                return fail_closed(
                    f"Stop-ScheduledTask failed (rc={rc}): {(se or '').strip()[:200]}"
                )
        if delete:
            rc, so, se = _run_ps(
                f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false"
                f" -ErrorAction SilentlyContinue"
            )
            step("unregister_scheduled_task", rc, so, se)
            if rc != 0:
                return fail_closed(
                    f"Unregister-ScheduledTask failed (rc={rc}): {(se or '').strip()[:200]}"
                )
        else:
            if not (state and state.lower() == "disabled"):
                rc, so, se = _run_ps(
                    f"Disable-ScheduledTask -TaskName '{TASK_NAME}'"
                    f" -ErrorAction SilentlyContinue"
                )
                step("disable_scheduled_task", rc, so, se)
                if rc != 0:
                    return fail_closed(
                        f"Disable-ScheduledTask failed (rc={rc}): {(se or '').strip()[:200]}"
                    )

    # ── 3. mutation recheck (Codex 2.5 follow-up #2) — desktop_stop/start 전에
    # 반드시 desired-state 확인. Windows cmdlet 이 rc=0 인데 실제 상태 반영
    # 안 된 race / 버그 케이스에서 legacy task 가 살아있는 채로 desktop 띄우는
    # 위험 방지 (fail-closed).
    if exists:
        q2 = _task_query()
        out["task_state_after_mutation"] = q2["state"]
        out["task_exists_after_mutation"] = q2["exists"]
        if not q2["ok"]:
            return fail_closed(f"mutation recheck failed: {q2['error']}")
        if delete and q2["exists"]:
            return fail_closed(
                f"delete=True but task still exists after mutation "
                f"(state={q2['state']!r})"
            )
        if not delete and q2["exists"]:
            if (q2["state"] or "").lower() != "disabled":
                return fail_closed(
                    f"task not disabled after mutation (state={q2['state']!r})"
                )

    # ── 4. desktop process 정리 (mutation recheck 통과한 후에만)
    from worker.desktop_launcher import desktop_stop as _stop
    stop_result = _stop(timeout_sec=15)
    out["steps"].append({"step": "desktop_stop", "result": stop_result})
    if not stop_result.get("ok", False):
        out["ok"] = False
        out["message"] = f"desktop_stop failed: {stop_result.get('error', 'unknown')}"
        return out

    # ── 5. start
    if start_desktop:
        from worker.desktop_launcher import desktop_start as _start
        start_result = _start()
        out["steps"].append({"step": "desktop_start", "result": start_result})
        out["ok"] = bool(start_result.get("ok"))
        out["message"] = start_result.get("message", "")
    else:
        out["message"] = "skipped desktop_start (start_desktop=False)"

    return out
