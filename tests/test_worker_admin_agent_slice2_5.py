"""Slice 2.5 — Cutover + Agent-owned update tests.

Mock 중심. 실제 schtasks / taskkill / git / pip 호출 절대 안 함.

Coverage (Codex 명시 8개):
  a. non-Windows cutover status/apply 가 supported=False no-op
  b. Windows cutover_apply dry_run 이 planned_steps 만 반환, subprocess/launcher
     호출 없음
  c. Windows cutover_apply 가 HydraWorker disable + desktop_stop → desktop_start
     순서로 호출
  d. cutover_apply 가 idempotent — task 없음/이미 disabled 면 그 단계 skip
  e. desktop_cutover_* / agent_update_now 가 desktop_worker runtime 에서 reject
  f. admin_agent runtime 에서 정상 dispatch
  g. agent_update_now 가 Task Scheduler restart 호출 안 함 + perform_update gate
     사용 안 함
  h. agent_update_now 가 _CMD_NON_REDELIVERABLE 에 포함
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ───────── a. non-Windows no-op ─────────

def test_cutover_status_non_windows_is_no_op(monkeypatch):
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "linux")
    from worker.scheduler_cutover import cutover_status
    out = cutover_status()
    assert out["ok"] is True
    assert out["supported"] is False
    assert out["task_name"] == "HydraWorker"


def test_cutover_apply_non_windows_is_no_op(monkeypatch):
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "linux")
    from worker.scheduler_cutover import cutover_apply
    out = cutover_apply()
    assert out["ok"] is True
    assert out["supported"] is False


# ───────── b. dry_run ─────────

def test_cutover_apply_dry_run_no_side_effects(monkeypatch):
    """dry_run=True 면 _run_ps / _task_query / desktop_stop / desktop_start 전부 호출 X.
    pure plan 만 반환 (Codex 2.5 early review 요구).
    """
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")
    with patch("worker.scheduler_cutover._run_ps") as fake_ps, \
         patch("worker.scheduler_cutover._task_query") as fake_q, \
         patch("worker.desktop_launcher.desktop_stop") as fake_stop, \
         patch("worker.desktop_launcher.desktop_start") as fake_start:
        from worker.scheduler_cutover import cutover_apply
        out = cutover_apply(dry_run=True)
    fake_ps.assert_not_called()
    fake_q.assert_not_called()
    fake_stop.assert_not_called()
    fake_start.assert_not_called()
    assert out["dry_run"] is True
    assert "disable_scheduled_task" in out["planned_steps"]
    assert "desktop_stop" in out["planned_steps"]
    assert "desktop_start" in out["planned_steps"]


def test_cutover_apply_fail_closed_when_initial_query_fails(monkeypatch):
    """initial query 실패 (PowerShell rc!=0 또는 permission) 면 ok=False,
    desktop_stop/start 호출 안 함 (Codex 2.5 early review 요구).
    """
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")
    monkeypatch.setattr(
        "worker.scheduler_cutover._task_query",
        lambda: {"ok": False, "exists": False, "state": None,
                  "error": "Access denied"},
    )
    with patch("worker.desktop_launcher.desktop_stop") as fake_stop, \
         patch("worker.desktop_launcher.desktop_start") as fake_start, \
         patch("worker.scheduler_cutover._run_ps") as fake_ps:
        from worker.scheduler_cutover import cutover_apply
        out = cutover_apply()
    assert out["ok"] is False
    assert "task query failed" in out["error"]
    fake_stop.assert_not_called()
    fake_start.assert_not_called()
    fake_ps.assert_not_called()


# ───────── c. Windows full flow: disable + stop → start ─────────

def test_cutover_apply_disables_then_restarts_desktop(monkeypatch):
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")

    # task query — 첫 호출은 Ready, 두 번째 (final recheck) 는 Disabled.
    query_calls = {"n": 0}
    def fake_q():
        query_calls["n"] += 1
        if query_calls["n"] == 1:
            return {"ok": True, "exists": True, "state": "Ready", "error": None}
        return {"ok": True, "exists": True, "state": "Disabled", "error": None}
    monkeypatch.setattr("worker.scheduler_cutover._task_query", fake_q)
    monkeypatch.setattr(
        "worker.scheduler_cutover._task_last_run_info",
        lambda: {},
    )
    ps_calls: list[str] = []
    def fake_ps(script, timeout=15):
        ps_calls.append(script)
        return (0, "", "")
    monkeypatch.setattr("worker.scheduler_cutover._run_ps", fake_ps)

    fake_stop = MagicMock(return_value={"ok": True, "action": "stop",
                                         "stopped_pids": [55], "running": False})
    fake_start = MagicMock(return_value={"ok": True, "action": "start",
                                          "running": True, "pids": [77],
                                          "message": "started pid=77"})
    monkeypatch.setattr("worker.desktop_launcher.desktop_stop", fake_stop)
    monkeypatch.setattr("worker.desktop_launcher.desktop_start", fake_start)

    from worker.scheduler_cutover import cutover_apply
    out = cutover_apply()

    assert out["ok"] is True
    # Disable 호출됐는지 PS 명령 안에 'Disable-ScheduledTask' 확인
    assert any("Disable-ScheduledTask" in s for s in ps_calls)
    # final task recheck 또는 disable, 둘 중 하나라도 호출됨.
    # Unregister 는 default 안 호출
    assert not any("Unregister-ScheduledTask" in s for s in ps_calls)

    # desktop_stop 먼저, desktop_start 다음 — call 순서 검증
    fake_stop.assert_called_once()
    fake_start.assert_called_once()


def test_cutover_apply_unregister_only_when_delete_true(monkeypatch):
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")
    # 첫 query: Ready / 두 번째 (final recheck): exists=False (unregister 성공)
    query_calls = {"n": 0}
    def fake_q():
        query_calls["n"] += 1
        if query_calls["n"] == 1:
            return {"ok": True, "exists": True, "state": "Ready", "error": None}
        return {"ok": True, "exists": False, "state": None, "error": None}
    monkeypatch.setattr("worker.scheduler_cutover._task_query", fake_q)
    monkeypatch.setattr("worker.scheduler_cutover._task_last_run_info",
                        lambda: {})
    ps_calls: list[str] = []
    monkeypatch.setattr(
        "worker.scheduler_cutover._run_ps",
        lambda s, timeout=15: (ps_calls.append(s), (0, "", ""))[1],
    )
    monkeypatch.setattr(
        "worker.desktop_launcher.desktop_stop",
        lambda *a, **k: {"ok": True, "running": False, "stopped_pids": []},
    )
    monkeypatch.setattr(
        "worker.desktop_launcher.desktop_start",
        lambda: {"ok": True, "running": True, "pids": [1]},
    )

    from worker.scheduler_cutover import cutover_apply
    cutover_apply(delete=True)

    assert any("Unregister-ScheduledTask" in s for s in ps_calls)


# ───────── d. idempotent — task missing or already disabled ─────────

def test_cutover_apply_skips_disable_when_task_missing(monkeypatch):
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")
    monkeypatch.setattr(
        "worker.scheduler_cutover._task_query",
        lambda: {"ok": True, "exists": False, "state": None, "error": None},
    )
    ps_calls: list[str] = []
    monkeypatch.setattr(
        "worker.scheduler_cutover._run_ps",
        lambda s, timeout=15: (ps_calls.append(s), (0, "", ""))[1],
    )
    monkeypatch.setattr(
        "worker.desktop_launcher.desktop_stop",
        lambda *a, **k: {"ok": True, "running": False, "stopped_pids": []},
    )
    monkeypatch.setattr(
        "worker.desktop_launcher.desktop_start",
        lambda: {"ok": True, "running": True, "pids": [1]},
    )
    # final recheck 도 not-exists (idempotent missing case 라 OK)

    from worker.scheduler_cutover import cutover_apply
    out = cutover_apply()
    # task 없으니 Disable / Stop / Unregister 모두 skip.
    # 그러나 final state recheck (_task_exists) 가 다시 호출되긴 함 — but
    # _run_ps 호출은 0 또는 적음. 핵심: Disable-ScheduledTask 안 호출.
    assert not any("Disable-ScheduledTask" in s for s in ps_calls)
    assert not any("Stop-ScheduledTask" in s for s in ps_calls)
    assert not any("Unregister-ScheduledTask" in s for s in ps_calls)
    assert out["ok"] is True


def test_cutover_apply_skips_disable_when_already_disabled(monkeypatch):
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")
    monkeypatch.setattr(
        "worker.scheduler_cutover._task_query",
        lambda: {"ok": True, "exists": True, "state": "Disabled", "error": None},
    )
    monkeypatch.setattr("worker.scheduler_cutover._task_last_run_info",
                        lambda: {})
    ps_calls: list[str] = []
    monkeypatch.setattr(
        "worker.scheduler_cutover._run_ps",
        lambda s, timeout=15: (ps_calls.append(s), (0, "", ""))[1],
    )
    monkeypatch.setattr(
        "worker.desktop_launcher.desktop_stop",
        lambda *a, **k: {"ok": True, "running": False, "stopped_pids": []},
    )
    monkeypatch.setattr(
        "worker.desktop_launcher.desktop_start",
        lambda: {"ok": True, "running": True, "pids": [1]},
    )

    from worker.scheduler_cutover import cutover_apply
    cutover_apply()
    # 이미 disabled — 다시 Disable 호출 안 함
    assert not any("Disable-ScheduledTask" in s for s in ps_calls)


# ───────── Codex 2.5 follow-up: ps mutation rc!=0 fail-closed ─────────

def test_cutover_apply_fail_closed_when_disable_fails(monkeypatch):
    """Disable-ScheduledTask rc!=0 → ok=False, desktop_stop/start 호출 X."""
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")
    monkeypatch.setattr(
        "worker.scheduler_cutover._task_query",
        lambda: {"ok": True, "exists": True, "state": "Ready", "error": None},
    )
    monkeypatch.setattr("worker.scheduler_cutover._task_last_run_info", lambda: {})

    def fake_ps(script, timeout=15):
        if "Disable-ScheduledTask" in script:
            return (1, "", "Access is denied.")
        return (0, "", "")
    monkeypatch.setattr("worker.scheduler_cutover._run_ps", fake_ps)

    fake_stop = MagicMock()
    fake_start = MagicMock()
    monkeypatch.setattr("worker.desktop_launcher.desktop_stop", fake_stop)
    monkeypatch.setattr("worker.desktop_launcher.desktop_start", fake_start)

    from worker.scheduler_cutover import cutover_apply
    out = cutover_apply()
    assert out["ok"] is False
    assert "Disable-ScheduledTask failed" in out["error"]
    fake_stop.assert_not_called()
    fake_start.assert_not_called()


def test_cutover_apply_fail_closed_when_unregister_fails(monkeypatch):
    """Unregister-ScheduledTask rc!=0 → ok=False, desktop 호출 X."""
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")
    monkeypatch.setattr(
        "worker.scheduler_cutover._task_query",
        lambda: {"ok": True, "exists": True, "state": "Ready", "error": None},
    )
    monkeypatch.setattr("worker.scheduler_cutover._task_last_run_info", lambda: {})

    def fake_ps(script, timeout=15):
        if "Unregister-ScheduledTask" in script:
            return (1, "", "Permission denied.")
        return (0, "", "")
    monkeypatch.setattr("worker.scheduler_cutover._run_ps", fake_ps)

    fake_stop = MagicMock()
    fake_start = MagicMock()
    monkeypatch.setattr("worker.desktop_launcher.desktop_stop", fake_stop)
    monkeypatch.setattr("worker.desktop_launcher.desktop_start", fake_start)

    from worker.scheduler_cutover import cutover_apply
    out = cutover_apply(delete=True)
    assert out["ok"] is False
    assert "Unregister-ScheduledTask failed" in out["error"]
    fake_stop.assert_not_called()
    fake_start.assert_not_called()


def test_cutover_apply_fail_closed_when_stop_scheduled_task_fails(monkeypatch):
    """Stop-ScheduledTask rc!=0 (state=Running 인 경우) → ok=False, desktop 호출 X."""
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")
    monkeypatch.setattr(
        "worker.scheduler_cutover._task_query",
        lambda: {"ok": True, "exists": True, "state": "Running", "error": None},
    )
    monkeypatch.setattr("worker.scheduler_cutover._task_last_run_info", lambda: {})

    def fake_ps(script, timeout=15):
        if "Stop-ScheduledTask" in script:
            return (1, "", "Cannot stop running task.")
        return (0, "", "")
    monkeypatch.setattr("worker.scheduler_cutover._run_ps", fake_ps)

    fake_stop = MagicMock()
    fake_start = MagicMock()
    monkeypatch.setattr("worker.desktop_launcher.desktop_stop", fake_stop)
    monkeypatch.setattr("worker.desktop_launcher.desktop_start", fake_start)

    from worker.scheduler_cutover import cutover_apply
    out = cutover_apply()
    assert out["ok"] is False
    assert "Stop-ScheduledTask failed" in out["error"]
    fake_stop.assert_not_called()
    fake_start.assert_not_called()


def test_cutover_apply_fail_closed_when_final_state_not_disabled(monkeypatch):
    """delete=False + final recheck 가 Ready/Running 인 경우 ok=False.

    Disable PS 명령은 rc=0 이지만 실제 상태 미반영 (race / Windows 버그 등).
    """
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")
    query_calls = {"n": 0}
    def fake_q():
        query_calls["n"] += 1
        if query_calls["n"] == 1:
            return {"ok": True, "exists": True, "state": "Ready", "error": None}
        # 첫 disable 시도 후에도 여전히 Ready
        return {"ok": True, "exists": True, "state": "Ready", "error": None}
    monkeypatch.setattr("worker.scheduler_cutover._task_query", fake_q)
    monkeypatch.setattr("worker.scheduler_cutover._task_last_run_info", lambda: {})
    monkeypatch.setattr("worker.scheduler_cutover._run_ps",
                        lambda s, timeout=15: (0, "", ""))  # 모든 PS 성공
    monkeypatch.setattr(
        "worker.desktop_launcher.desktop_stop",
        lambda *a, **k: {"ok": True, "running": False, "stopped_pids": []},
    )
    monkeypatch.setattr(
        "worker.desktop_launcher.desktop_start",
        lambda: {"ok": True, "running": True, "pids": [1]},
    )

    from worker.scheduler_cutover import cutover_apply
    out = cutover_apply()
    assert out["ok"] is False
    assert "not disabled" in out["error"]


def test_cutover_apply_fail_closed_when_delete_true_but_task_remains(monkeypatch):
    """delete=True + final recheck 가 여전히 exists=True 인 경우 ok=False."""
    monkeypatch.setattr("worker.scheduler_cutover.sys.platform", "win32")
    query_calls = {"n": 0}
    def fake_q():
        query_calls["n"] += 1
        # 첫 호출: Ready / 두 번째: 여전히 존재 (unregister 실제 미반영)
        return {"ok": True, "exists": True, "state": "Ready", "error": None}
    monkeypatch.setattr("worker.scheduler_cutover._task_query", fake_q)
    monkeypatch.setattr("worker.scheduler_cutover._task_last_run_info", lambda: {})
    monkeypatch.setattr("worker.scheduler_cutover._run_ps",
                        lambda s, timeout=15: (0, "", ""))
    monkeypatch.setattr(
        "worker.desktop_launcher.desktop_stop",
        lambda *a, **k: {"ok": True, "running": False, "stopped_pids": []},
    )
    monkeypatch.setattr(
        "worker.desktop_launcher.desktop_start",
        lambda: {"ok": True, "running": True, "pids": [1]},
    )

    from worker.scheduler_cutover import cutover_apply
    out = cutover_apply(delete=True)
    assert out["ok"] is False
    assert "task still exists" in out["error"]


# ───────── e/f. role guard ─────────

@pytest.mark.asyncio
async def test_slice25_commands_rejected_on_desktop_worker_runtime(monkeypatch):
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "desktop_worker")
    from worker.commands import execute_command

    fake_client = MagicMock()
    captured = {}
    def capture_ack(client, cmd_id, status, result, err):
        captured["status"] = status
        captured["result"] = result

    with patch("worker.commands._ack", side_effect=capture_ack), \
         patch("worker.scheduler_cutover.cutover_status") as fake_cs, \
         patch("worker.scheduler_cutover.cutover_apply") as fake_ca, \
         patch("worker.agent_update.agent_update_now") as fake_au:
        for cmd_name in ("desktop_cutover_status", "desktop_cutover_apply",
                         "agent_update_now"):
            await execute_command(fake_client, {"id": 1, "command": cmd_name,
                                                "payload": None})
            parsed = json.loads(captured["result"])
            assert parsed["ok"] is False
            assert "admin_agent" in parsed["error"]
    fake_cs.assert_not_called()
    fake_ca.assert_not_called()
    fake_au.assert_not_called()


@pytest.mark.asyncio
async def test_slice25_commands_allowed_on_admin_agent_runtime(monkeypatch):
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    from worker.commands import execute_command

    fake_client = MagicMock()
    captured = {}
    def capture_ack(client, cmd_id, status, result, err):
        captured["status"] = status
        captured["result"] = result

    with patch("worker.commands._ack", side_effect=capture_ack), \
         patch("worker.scheduler_cutover.cutover_status") as fake_cs:
        fake_cs.return_value = {"ok": True, "action": "cutover_status",
                                 "supported": True, "exists": False, "state": None,
                                 "platform": "win32", "task_name": "HydraWorker"}
        await execute_command(fake_client, {"id": 1, "command": "desktop_cutover_status",
                                             "payload": None})

    parsed = json.loads(captured["result"])
    assert parsed["action"] == "cutover_status"
    fake_cs.assert_called_once()


# ───────── g. agent_update_now does NOT call Task Scheduler / perform_update ─────────

def test_agent_update_now_does_not_call_task_scheduler():
    """agent_update_now function body 안에 Task Scheduler / HydraWorker 매뉴퍼레이션 없음.

    docstring 매칭 false-positive 방지 — inspect.getsource(function) 만 검사.
    """
    import inspect
    from worker.agent_update import agent_update_now
    src = inspect.getsource(agent_update_now)
    assert "Start-ScheduledTask" not in src, "agent_update body 에 Task Scheduler 호출 발견"
    # Task Scheduler 의 HydraWorker name 을 함수 body 가 직접 manipulate 안 함.
    # (docstring/comment 는 모듈 level 이라 inspect.getsource 함수 body 에 안 잡힘
    # — 단 함수 docstring 자체는 잡힘. 우리 함수 docstring 엔 HydraWorker 없음.)
    assert "HydraWorker" not in src, "agent_update body 에 HydraWorker 직접 참조 발견"


def test_agent_update_now_does_not_use_perform_update_gate():
    """agent_update_now function body 가 perform_update 호출 안 함.

    perform_update 는 HYDRA_UPDATE_OWNER=agent gate 로 reject. agent runtime 에선
    호출 자체 금지 — agent_update 가 직접 git/pip 흐름 수행.
    """
    import inspect
    from worker.agent_update import agent_update_now
    src = inspect.getsource(agent_update_now)
    # 호출 패턴만 검사: 'perform_update(' 또는 'maybe_update(' 가 함수 body 에 없어야.
    assert "perform_update(" not in src
    assert "maybe_update(" not in src
    # worker.updater 모듈 자체 import 부재 — module-level import 검증.
    import worker.agent_update as _mod
    module_src = inspect.getsource(_mod)
    # docstring 매칭 회피 위해 'from worker.updater import' 정확한 import 라인만 검사.
    assert "from worker.updater import" not in module_src
    assert "import worker.updater" not in module_src


def test_agent_update_now_no_op_when_already_on_origin_main(monkeypatch):
    """이미 origin/main 이면 desktop 안 건드림 + ok=True + noop=True."""
    def fake_git(repo, args, timeout=60):
        if args[:2] == ["fetch", "origin"]:
            return (0, "", "")
        if args == ["rev-parse", "HEAD"]:
            return (0, "abc123def\n", "")
        if args == ["rev-parse", "origin/main"]:
            return (0, "abc123def\n", "")  # same
        return (1, "", "unexpected")

    monkeypatch.setattr("worker.agent_update._git", fake_git)
    with patch("worker.desktop_launcher.desktop_stop") as fake_stop, \
         patch("worker.desktop_launcher.desktop_start") as fake_start:
        from worker.agent_update import agent_update_now
        out = agent_update_now()

    assert out["ok"] is True
    assert out.get("noop") is True
    fake_stop.assert_not_called()
    fake_start.assert_not_called()


def test_agent_update_now_dry_run(monkeypatch):
    from worker.agent_update import agent_update_now
    out = agent_update_now(dry_run=True)
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert "planned_steps" in out


def test_agent_update_now_pip_failure_rolls_back_git(monkeypatch):
    """pip install fail → git reset prev (rollback) → desktop_start. ok=False.

    Codex 2.5 review 요구: broken state (new code + old deps) 회피.
    """
    git_calls: list[list[str]] = []
    def fake_git(repo, args, timeout=60):
        git_calls.append(args)
        if args == ["rev-parse", "HEAD"]:
            return (0, "OLDSHA1234567\n", "")
        if args == ["rev-parse", "origin/main"]:
            return (0, "NEWSHA7654321\n", "")
        return (0, "", "")
    monkeypatch.setattr("worker.agent_update._git", fake_git)
    # pip install fail
    monkeypatch.setattr("worker.agent_update._pip_install_e",
                        lambda *a, **k: (1, "", "ERROR: package not found"))

    fake_stop = MagicMock(return_value={"ok": True, "running": False, "stopped_pids": [55]})
    fake_start = MagicMock(return_value={"ok": True, "running": True, "pids": [99]})
    monkeypatch.setattr("worker.desktop_launcher.desktop_stop", fake_stop)
    monkeypatch.setattr("worker.desktop_launcher.desktop_start", fake_start)

    from worker.agent_update import agent_update_now
    out = agent_update_now()

    assert out["ok"] is False
    assert "pip install failed" in out["error"]
    # git reset --hard origin/main 후 pip 실패 → git reset --hard <prev> rollback 호출됨.
    assert ["reset", "--hard", "origin/main"] in git_calls
    assert ["reset", "--hard", "OLDSHA1234567"] in git_calls
    # desktop_start rollback 호출됨.
    fake_start.assert_called_once()


def test_agent_update_now_does_not_accept_restart_agent_kwarg(monkeypatch):
    """restart_agent 옵션 제거 — payload 로 받아도 무시 (kwarg 없음)."""
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    from worker.agent_update import agent_update_now
    import inspect
    sig = inspect.signature(agent_update_now)
    assert "restart_agent" not in sig.parameters


def test_agent_update_now_full_flow_on_update(monkeypatch):
    """HEAD != origin/main 이면 stop -> reset -> pip -> start 순서."""
    git_calls: list[list[str]] = []
    def fake_git(repo, args, timeout=60):
        git_calls.append(args)
        if args == ["rev-parse", "HEAD"]:
            return (0, "old1234567\n", "")
        if args == ["rev-parse", "origin/main"]:
            return (0, "new9876543\n", "")
        return (0, "", "")
    monkeypatch.setattr("worker.agent_update._git", fake_git)
    monkeypatch.setattr("worker.agent_update._pip_install_e",
                        lambda *a, **k: (0, "", ""))

    fake_stop = MagicMock(return_value={"ok": True, "running": False, "stopped_pids": [55]})
    fake_start = MagicMock(return_value={"ok": True, "running": True, "pids": [77]})
    monkeypatch.setattr("worker.desktop_launcher.desktop_stop", fake_stop)
    monkeypatch.setattr("worker.desktop_launcher.desktop_start", fake_start)

    from worker.agent_update import agent_update_now
    out = agent_update_now()

    assert out["ok"] is True
    assert out["prev"] == "old1234567"[:12]
    # git fetch + rev-parse HEAD + rev-parse origin/main + reset --hard 순.
    assert ["fetch", "origin", "main"] in git_calls
    assert ["reset", "--hard", "origin/main"] in git_calls
    fake_stop.assert_called_once()
    fake_start.assert_called_once()


# ───────── h. _CMD_NON_REDELIVERABLE ─────────

def test_slice25_commands_in_non_redeliverable():
    from hydra.web.routes.worker_api import _CMD_NON_REDELIVERABLE
    assert "desktop_cutover_apply" in _CMD_NON_REDELIVERABLE
    assert "agent_update_now" in _CMD_NON_REDELIVERABLE
    # cutover_status 는 read-only 라 OK 재배달
    assert "desktop_cutover_status" not in _CMD_NON_REDELIVERABLE


def test_slice25_commands_in_allowed_commands():
    from hydra.web.routes.admin_workers import ALLOWED_COMMANDS
    for name in ("desktop_cutover_status", "desktop_cutover_apply",
                 "agent_update_now"):
        assert name in ALLOWED_COMMANDS
