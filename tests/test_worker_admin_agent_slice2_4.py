"""Slice 2.4 — Desktop Worker Launcher tests.

Mock-based. 실제 process kill/start 절대 안 함.

Coverage (Codex 명시 8개):
  a. desktop_launcher status 가 admin_agent process 제외
  b. start 가 이미 running 이면 Popen 안 함
  c. start env 에 HYDRA_DISABLE_TASK_REGISTER=1, HYDRA_UPDATE_OWNER=agent
  d. start env 가 HYDRA_AGENT_WORKER_TOKEN 을 HYDRA_WORKER_TOKEN 으로 복사 안 함
  e. stop 은 graceful 후 timeout 시 force path 호출
  f. commands.py 가 desktop_* 를 launcher 로 dispatch + JSON result ack
  g. admin ALLOWED_COMMANDS 가 4개를 받음
  h. desktop_restart 가 non-redeliverable 정책에 포함
"""
from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import MagicMock, patch, call

import pytest


# ───────── a. status 가 admin_agent 제외 ─────────

def test_cmdline_is_desktop_includes_python_m_worker():
    from worker.desktop_launcher import _cmdline_is_desktop
    assert _cmdline_is_desktop(["python", "-m", "worker"])
    assert _cmdline_is_desktop(["C:\\hydra\\.venv\\Scripts\\python.exe", "-m", "worker"])


def test_cmdline_is_desktop_excludes_admin_agent():
    from worker.desktop_launcher import _cmdline_is_desktop
    assert not _cmdline_is_desktop(["python", "-m", "worker.admin_agent"])
    # admin_agent 마커 가 어디든 있으면 제외
    assert not _cmdline_is_desktop(["python", "-m", "worker", "--admin_agent"])
    assert not _cmdline_is_desktop(["python", "worker/admin_agent.py"])


def test_cmdline_is_desktop_recognizes_app_paths():
    from worker.desktop_launcher import _cmdline_is_desktop
    assert _cmdline_is_desktop(["python", "worker/app.py"])
    assert _cmdline_is_desktop(["python", "worker\\app.py"])
    assert _cmdline_is_desktop(["python", "worker/__main__.py"])


def test_desktop_status_excludes_admin_agent_process():
    """psutil mock — admin_agent 와 desktop 이 같이 떠 있어도 admin_agent 만 제외."""
    fake_procs = [
        # admin_agent
        type("P", (), {"info": {"pid": 100, "name": "python.exe",
                                "cmdline": ["python", "-m", "worker.admin_agent"]}})(),
        # desktop
        type("P", (), {"info": {"pid": 200, "name": "python.exe",
                                "cmdline": ["python", "-m", "worker"]}})(),
        # unrelated
        type("P", (), {"info": {"pid": 300, "name": "chrome.exe",
                                "cmdline": ["chrome.exe", "--remote-debugging"]}})(),
    ]
    with patch("worker.desktop_launcher.psutil") as fake_psutil, \
         patch("worker.desktop_launcher._PSUTIL_AVAILABLE", True):
        fake_psutil.process_iter.return_value = iter(fake_procs)
        fake_psutil.NoSuchProcess = Exception
        fake_psutil.AccessDenied = Exception

        from worker.desktop_launcher import desktop_status
        result = desktop_status()

    assert result["ok"] is True
    assert result["action"] == "status"
    assert result["running"] is True
    assert result["pids"] == [200]


# ───────── b. start 이미 running 이면 Popen 안 함 ─────────

def test_desktop_start_no_op_when_running():
    with patch("worker.desktop_launcher._find_desktop_pids", return_value=[200]), \
         patch("worker.desktop_launcher.subprocess.Popen") as fake_popen:
        from worker.desktop_launcher import desktop_start
        result = desktop_start()

    assert result["running"] is True
    assert result["pids"] == [200]
    assert result["started_pid"] is None
    assert "already running" in result["message"]
    fake_popen.assert_not_called()


# ───────── c. start env 가 4종 override ─────────

def test_desktop_start_env_overrides(monkeypatch):
    monkeypatch.delenv("HYDRA_AGENT_WORKER_TOKEN", raising=False)
    monkeypatch.delenv("HYDRA_WORKER_TOKEN", raising=False)

    with patch("worker.desktop_launcher._find_desktop_pids", return_value=[]), \
         patch("worker.desktop_launcher.subprocess.Popen") as fake_popen:
        fake_proc = MagicMock()
        fake_proc.pid = 12345
        fake_popen.return_value = fake_proc

        from worker.desktop_launcher import desktop_start
        result = desktop_start()

    fake_popen.assert_called_once()
    kwargs = fake_popen.call_args.kwargs
    env = kwargs.get("env") or {}
    assert env.get("HYDRA_DISABLE_TASK_REGISTER") == "1"
    assert env.get("HYDRA_UPDATE_OWNER") == "agent"
    assert result["started_pid"] == 12345


# ───────── d. start 가 agent token 을 worker token 으로 복사 안 함 ─────────

def test_desktop_start_does_not_propagate_agent_token(monkeypatch):
    """부모 process 가 admin_agent 라 HYDRA_WORKER_TOKEN == HYDRA_AGENT_WORKER_TOKEN
    상태여도 desktop start 시점에 pop 되어 desktop 으로 전달 안 됨.
    """
    monkeypatch.setenv("HYDRA_AGENT_WORKER_TOKEN", "AGENT-TOKEN-XYZ")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "AGENT-TOKEN-XYZ")  # admin_agent main 이 set 한 상태 simulating

    with patch("worker.desktop_launcher._find_desktop_pids", return_value=[]), \
         patch("worker.desktop_launcher.subprocess.Popen") as fake_popen:
        fake_proc = MagicMock(); fake_proc.pid = 1
        fake_popen.return_value = fake_proc

        from worker.desktop_launcher import desktop_start
        desktop_start()

    env = fake_popen.call_args.kwargs.get("env") or {}
    assert env.get("HYDRA_AGENT_WORKER_TOKEN") == "AGENT-TOKEN-XYZ"  # agent token 자체는 유지
    # 핵심: desktop worker 가 agent token 으로 enroll 되지 않도록 pop.
    assert env.get("HYDRA_WORKER_TOKEN") != "AGENT-TOKEN-XYZ"


def test_desktop_start_preserves_independent_desktop_token(monkeypatch):
    """desktop 이 자기 token 을 별도로 갖고 있으면 그건 유지 (agent token 과 다른 경우)."""
    monkeypatch.setenv("HYDRA_AGENT_WORKER_TOKEN", "AGENT-TOKEN")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "DESKTOP-TOKEN")

    with patch("worker.desktop_launcher._find_desktop_pids", return_value=[]), \
         patch("worker.desktop_launcher.subprocess.Popen") as fake_popen:
        fake_proc = MagicMock(); fake_proc.pid = 1
        fake_popen.return_value = fake_proc

        from worker.desktop_launcher import desktop_start
        desktop_start()

    env = fake_popen.call_args.kwargs.get("env") or {}
    # 다른 token 이면 유지 (agent token 과 충돌 안 함)
    assert env.get("HYDRA_WORKER_TOKEN") == "DESKTOP-TOKEN"


# ───────── e. stop graceful → timeout 후 force ─────────

def test_desktop_stop_graceful_then_force_on_posix(monkeypatch):
    """POSIX path: SIGTERM 보냈는데 timeout 안에 안 죽으면 SIGKILL."""
    monkeypatch.setattr("worker.desktop_launcher.sys.platform", "linux")
    pid = 999

    # _find_desktop_pids 호출 순서:
    #   1) stop 시작 시 — running pids 반환 [999]
    #   2) wait loop 안 — graceful timeout 동안 계속 [999] (안 죽음)
    #   3) force 후 — 빈 list
    call_count = {"n": 0}
    def fake_find():
        call_count["n"] += 1
        # 첫 호출: 처음 pid 조회. 이후도 안 죽음 (force 전).
        return [pid] if call_count["n"] < 100 else []
    monkeypatch.setattr("worker.desktop_launcher._find_desktop_pids", fake_find)

    kill_calls: list[tuple[int, int]] = []
    def fake_kill(p, sig):
        kill_calls.append((p, sig))
    monkeypatch.setattr("worker.desktop_launcher.os.kill", fake_kill)
    # time.sleep / time.monotonic 가속
    times = [0.0, 0.5, 1.0, 16.0]  # graceful loop 빠르게 통과
    times_iter = iter(times + [16.0] * 10)
    monkeypatch.setattr("worker.desktop_launcher.time.monotonic", lambda: next(times_iter))
    monkeypatch.setattr("worker.desktop_launcher.time.sleep", lambda _s: None)

    from worker.desktop_launcher import desktop_stop
    import signal as _signal
    result = desktop_stop(timeout_sec=1)

    # graceful SIGTERM + 이후 force SIGKILL 둘 다 호출
    signals = [s for (_p, s) in kill_calls]
    assert _signal.SIGTERM in signals
    assert _signal.SIGKILL in signals
    assert result["action"] == "stop"


def test_desktop_stop_noop_when_not_running():
    with patch("worker.desktop_launcher._find_desktop_pids", return_value=[]):
        from worker.desktop_launcher import desktop_stop
        result = desktop_stop()
    assert result["running"] is False
    assert result["stopped_pids"] == []
    assert "no desktop worker" in result["message"]


# ───────── f. commands.py dispatch + JSON ack ─────────

@pytest.mark.asyncio
async def test_commands_dispatch_desktop_status_returns_json():
    from worker.commands import execute_command

    fake_client = MagicMock()
    fake_client._request = MagicMock(return_value=MagicMock())  # ack call
    cmd = {"id": 1, "command": "desktop_status", "payload": None}

    captured = {}
    def capture_ack(client, cmd_id, status, result, err):
        captured["status"] = status
        captured["result"] = result

    with patch("worker.commands._ack", side_effect=capture_ack), \
         patch("worker.desktop_launcher._find_desktop_pids", return_value=[]):
        await execute_command(fake_client, cmd)

    assert captured["status"] == "done"
    parsed = json.loads(captured["result"])
    assert parsed["action"] == "status"
    assert parsed["running"] is False


@pytest.mark.asyncio
async def test_commands_dispatch_desktop_start():
    from worker.commands import execute_command

    fake_client = MagicMock()
    cmd = {"id": 2, "command": "desktop_start", "payload": None}
    captured = {}
    def capture_ack(client, cmd_id, status, result, err):
        captured["status"] = status
        captured["result"] = result

    with patch("worker.commands._ack", side_effect=capture_ack), \
         patch("worker.desktop_launcher._find_desktop_pids", return_value=[55]):
        await execute_command(fake_client, cmd)

    assert captured["status"] == "done"
    parsed = json.loads(captured["result"])
    assert parsed["action"] == "start"
    assert parsed["pids"] == [55]


@pytest.mark.asyncio
async def test_commands_dispatch_desktop_stop_passes_timeout():
    from worker.commands import execute_command

    fake_client = MagicMock()
    cmd = {"id": 3, "command": "desktop_stop", "payload": {"timeout_sec": 7}}

    with patch("worker.commands._ack") as ack, \
         patch("worker.desktop_launcher.desktop_stop") as fake_stop:
        fake_stop.return_value = {"ok": True, "action": "stop", "stopped_pids": [55]}
        await execute_command(fake_client, cmd)

    fake_stop.assert_called_once_with(timeout_sec=7)


@pytest.mark.asyncio
async def test_commands_dispatch_desktop_restart():
    from worker.commands import execute_command

    fake_client = MagicMock()
    cmd = {"id": 4, "command": "desktop_restart", "payload": None}
    captured = {}
    def capture_ack(client, cmd_id, status, result, err):
        captured["status"] = status
        captured["result"] = result

    with patch("worker.commands._ack", side_effect=capture_ack), \
         patch("worker.desktop_launcher.desktop_restart") as fake_restart:
        fake_restart.return_value = {"ok": True, "action": "restart",
                                     "started_pid": 77, "stopped_pids": [55]}
        await execute_command(fake_client, cmd)

    assert captured["status"] == "done"
    parsed = json.loads(captured["result"])
    assert parsed["action"] == "restart"


# ───────── g. admin ALLOWED_COMMANDS 4개 포함 ─────────

def test_admin_allowed_commands_includes_desktop_quartet():
    from hydra.web.routes.admin_workers import ALLOWED_COMMANDS
    for name in ("desktop_status", "desktop_start", "desktop_stop", "desktop_restart"):
        assert name in ALLOWED_COMMANDS, f"{name} 가 ALLOWED_COMMANDS 에 없음"


# ───────── h. desktop_restart non-redeliverable ─────────

def test_desktop_restart_is_non_redeliverable():
    from hydra.web.routes.worker_api import _CMD_NON_REDELIVERABLE
    assert "desktop_restart" in _CMD_NON_REDELIVERABLE
    # idempotent 한 것들은 빠져있어야
    assert "desktop_start" not in _CMD_NON_REDELIVERABLE
    assert "desktop_stop" not in _CMD_NON_REDELIVERABLE
    assert "desktop_status" not in _CMD_NON_REDELIVERABLE


# ───────── extra: launcher 가 admin_agent 자기 자신 절대 kill 안 함 ─────────

def test_stop_never_targets_admin_agent_process():
    """admin_agent process 가 cmdline 에 있어도 _find_desktop_pids 가 제외하므로
    stop 흐름이 절대 그 PID 에 도달 안 함."""
    fake_procs = [
        type("P", (), {"info": {"pid": 100,
                                "cmdline": ["python", "-m", "worker.admin_agent"]}})(),
    ]
    with patch("worker.desktop_launcher.psutil") as fake_psutil, \
         patch("worker.desktop_launcher._PSUTIL_AVAILABLE", True):
        fake_psutil.process_iter.return_value = iter(fake_procs)
        fake_psutil.NoSuchProcess = Exception
        fake_psutil.AccessDenied = Exception

        from worker.desktop_launcher import desktop_stop
        result = desktop_stop()
    assert result["running"] is False
    assert result["stopped_pids"] == []
