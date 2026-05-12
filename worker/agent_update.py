"""Slice 2.5 — Agent-owned update flow.

worker.updater.perform_update() 는 HYDRA_UPDATE_OWNER=agent gate 로 reject.
desktop self-update 차단 + Task Scheduler 의존 — 이제 admin agent 가
update 소유.

흐름:
  1) desktop_stop (정상 종료 보장)
  2) git fetch + reset --hard origin/main (in repo root)
  3) pip install -e . (venv python)
  4) desktop_start
  5) (optional) agent 자기 process exit → NSSM 가 restart

이미 origin/main 이면 (3) skip + (1),(4) 도 skip 권장 — desktop 멈춤 없이 ok.

Start-ScheduledTask HydraWorker 절대 호출 X (cutover 됐다고 가정).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_venv_python() -> str:
    root = _repo_root()
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return sys.executable


def _git(repo: Path, args: list[str], timeout: int = 60) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo)] + args,
            capture_output=True, timeout=timeout, text=True,
        )
        return (proc.returncode, proc.stdout or "", proc.stderr or "")
    except Exception as e:
        return (-1, "", f"{type(e).__name__}: {e}")


def _pip_install_e(python_exe: str, repo: Path, timeout: int = 600) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            [python_exe, "-m", "pip", "install", "-e", str(repo), "--quiet"],
            capture_output=True, timeout=timeout, text=True,
        )
        return (proc.returncode, proc.stdout or "", proc.stderr or "")
    except Exception as e:
        return (-1, "", f"{type(e).__name__}: {e}")


def agent_update_now(
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """admin agent 가 소유한 update 흐름.

    Slice 2.5 — restart_agent 옵션 제거 (Codex review 권장 A).
    agent 자기 self-restart 는 별도 command 로 분리 (NSSM service restart 전담).
    여기선 update + desktop restart 까지만 deterministic 하게.

    Args:
        dry_run: True 면 plan 만 반환, 실제 subprocess/launcher 호출 안 함.

    Returns:
        {ok, action='agent_update_now', steps, ...}.
        repo 이미 origin/main 이면 desktop 멈춤 없이 ok=True + noop=True.
        pip install 실패 시 git reset prev 로 rollback + desktop_start.
    """
    out: dict[str, Any] = {
        "ok": True,
        "action": "agent_update_now",
        "dry_run": dry_run,
        "steps": [],
    }
    repo = _repo_root()
    python = _resolve_venv_python()
    out["repo"] = str(repo)
    out["python"] = python

    # 1. git fetch (인터넷 필요)
    if dry_run:
        out["planned_steps"] = [
            "git fetch origin main",
            "compare HEAD vs origin/main",
            "if equal -> noop",
            "else -> desktop_stop, git reset --hard origin/main, pip install -e .,"
            " desktop_start (pip fail -> git reset prev + desktop_start rollback)",
        ]
        out["message"] = "dry_run — no actions taken"
        return out

    rc, so, se = _git(repo, ["fetch", "origin", "main"], timeout=60)
    out["steps"].append({"step": "git_fetch", "rc": rc,
                         "stderr": (se or "").strip()[:300]})
    if rc != 0:
        out["ok"] = False
        out["error"] = f"git fetch failed: {se.strip()[:300]}"
        return out

    # 2. HEAD vs origin/main 비교
    rc1, prev, _ = _git(repo, ["rev-parse", "HEAD"], timeout=10)
    rc2, remote, _ = _git(repo, ["rev-parse", "origin/main"], timeout=10)
    prev = prev.strip()
    remote = remote.strip()
    out["steps"].append({"step": "compare", "prev": prev[:12], "remote": remote[:12]})
    if rc1 != 0 or rc2 != 0:
        out["ok"] = False
        out["error"] = "git rev-parse failed"
        return out

    if prev == remote:
        # noop — desktop 안 건드림.
        out["noop"] = True
        out["message"] = f"already on origin/main ({remote[:12]}) — skipping update"
        return out

    # 3. desktop_stop (실제 update 시작)
    from worker.desktop_launcher import desktop_stop as _stop
    stop_result = _stop(timeout_sec=15)
    out["steps"].append({"step": "desktop_stop", "result": stop_result})
    if not stop_result.get("ok", False):
        out["ok"] = False
        out["error"] = f"desktop_stop failed: {stop_result.get('error','')}"
        return out

    # 4. git reset
    rc, so, se = _git(repo, ["reset", "--hard", "origin/main"], timeout=30)
    out["steps"].append({"step": "git_reset", "rc": rc,
                         "stderr": (se or "").strip()[:300]})
    if rc != 0:
        out["ok"] = False
        out["error"] = f"git reset failed: {se.strip()[:300]}"
        # 그래도 desktop_start 시도 — 옛 코드라도 살리는 게 stop 상태 유지보다 나음.
        from worker.desktop_launcher import desktop_start as _start
        rollback_start = _start()
        out["steps"].append({"step": "desktop_start_rollback", "result": rollback_start})
        return out

    # 5. pip install
    rc, so, se = _pip_install_e(python, repo)
    out["steps"].append({"step": "pip_install", "rc": rc,
                         "stderr": (se or "").strip()[:300]})
    if rc != 0:
        out["ok"] = False
        out["error"] = f"pip install failed: {se.strip()[:300]}"
        # Slice 2.5 fix — pip 실패 시 git 도 prev 로 rollback. 그래야 desktop_start
        # 가 옛 코드 + 옛 dependencies 일관성 유지. broken (new code + old deps) 회피.
        rrc, rso, rse = _git(repo, ["reset", "--hard", prev], timeout=30)
        out["steps"].append({"step": "git_rollback", "rc": rrc,
                             "stderr": (rse or "").strip()[:300]})
        from worker.desktop_launcher import desktop_start as _start
        rb = _start()
        out["steps"].append({"step": "desktop_start_rollback", "result": rb})
        return out

    # 6. desktop_start
    from worker.desktop_launcher import desktop_start as _start
    start_result = _start()
    out["steps"].append({"step": "desktop_start", "result": start_result})
    if not start_result.get("ok", False):
        out["ok"] = False
        out["error"] = f"desktop_start after update failed: {start_result.get('error','')}"
        return out

    out["prev"] = prev[:12]
    out["new"] = remote[:12]
    out["message"] = f"updated {prev[:12]} -> {remote[:12]}"
    return out
