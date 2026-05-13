"""Slice 3.3 — agent_self_restart command (ack-then-spawn).

Coverage:
  1. ALLOWED_COMMANDS / _CMD_REQUIRED_ROLE / _CMD_NON_REDELIVERABLE 모두 포함
  2. admin POST /command 발행 → target_role="admin_agent" 자동 박힘
  3. HYDRA_PROCESS_ROLE != admin_agent runtime → fail-closed (Popen 호출 X, ack=failed)
  4. ack 성공 후에만 spawn_restart_helper 호출 (순서 검증)
  5. ack 실패 (200 이지만 ok=False, 또는 5xx) → spawn 안 함
  6. nssm 못 찾으면 ack 전 failed
  7. delay_sec 범위 초과 시 ack=failed (spawn 안 함)
  8. spawn Popen 실패 시 client.report_error 호출 + ack 는 이미 done
  9. helper 단위: subprocess.run mock + sleep mock + log 작성 검증
 10. Windows platform creationflags 분기
 11. PS1 ServiceName 동기화 (install-admin-agent-service.ps1 default == ADMIN_AGENT_SERVICE_NAME)
 12. resolve_nssm_path: env / which / chocolatey fallback 순서

spec: Codex Slice 3.3 plan v2 APPROVED 조건 반영.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ───────── 1. policy ─────────

def test_allowed_commands_includes_agent_self_restart():
    from hydra.web.routes.admin_workers import ALLOWED_COMMANDS, _CMD_REQUIRED_ROLE
    assert "agent_self_restart" in ALLOWED_COMMANDS
    assert _CMD_REQUIRED_ROLE["agent_self_restart"] == "admin_agent"


def test_non_redeliverable_includes_agent_self_restart():
    from hydra.web.routes.worker_api import _CMD_NON_REDELIVERABLE
    assert "agent_self_restart" in _CMD_NON_REDELIVERABLE


# ───────── 2. PS1 service name 동기화 ─────────

def test_ps1_service_name_matches_python_constant():
    """install-admin-agent-service.ps1 의 -ServiceName 기본값과 Python 상수 일치 검증."""
    from worker.agent_self_restart import ADMIN_AGENT_SERVICE_NAME
    repo = Path(__file__).resolve().parents[1]
    ps1 = repo / "setup" / "install-admin-agent-service.ps1"
    text = ps1.read_text(encoding="utf-8")
    m = re.search(r"\[string\]\$ServiceName\s*=\s*'([^']+)'", text)
    assert m is not None, "ServiceName param not found in install-admin-agent-service.ps1"
    assert m.group(1) == ADMIN_AGENT_SERVICE_NAME, (
        f"PS1 default {m.group(1)!r} != Python {ADMIN_AGENT_SERVICE_NAME!r}"
    )


# ───────── 3. resolve_nssm_path fallback ─────────

def test_resolve_nssm_prefers_env(tmp_path, monkeypatch):
    import worker.agent_self_restart as mod
    nssm = tmp_path / "nssm.exe"
    nssm.write_text("stub")
    monkeypatch.setenv("HYDRA_NSSM_PATH", str(nssm))
    assert mod.resolve_nssm_path() == str(nssm)


def test_resolve_nssm_falls_back_to_which(tmp_path, monkeypatch):
    import worker.agent_self_restart as mod
    monkeypatch.delenv("HYDRA_NSSM_PATH", raising=False)
    with patch.object(mod.shutil, "which", return_value="/usr/local/bin/nssm"):
        assert mod.resolve_nssm_path() == "/usr/local/bin/nssm"


def test_resolve_nssm_falls_back_to_chocolatey(tmp_path, monkeypatch):
    import worker.agent_self_restart as mod
    monkeypatch.delenv("HYDRA_NSSM_PATH", raising=False)
    with patch.object(mod.shutil, "which", return_value=None), \
         patch.object(mod, "_CHOCOLATEY_NSSM", str(tmp_path / "nssm.exe")):
        (tmp_path / "nssm.exe").write_text("stub")
        assert mod.resolve_nssm_path() == str(tmp_path / "nssm.exe")


def test_resolve_nssm_raises_when_missing(monkeypatch):
    import worker.agent_self_restart as mod
    monkeypatch.delenv("HYDRA_NSSM_PATH", raising=False)
    with patch.object(mod.shutil, "which", return_value=None), \
         patch.object(mod, "_CHOCOLATEY_NSSM", "/nonexistent/nssm.exe"):
        with pytest.raises(RuntimeError, match="nssm not found"):
            mod.resolve_nssm_path()


# ───────── 4. spawn_restart_helper platform flags ─────────

def test_spawn_helper_uses_detached_flags_on_windows(tmp_path, monkeypatch):
    import worker.agent_self_restart as mod
    monkeypatch.setattr(mod.sys, "platform", "win32")
    fake_proc = MagicMock()
    with patch.object(mod.subprocess, "Popen", return_value=fake_proc) as p:
        mod.spawn_restart_helper(
            nssm_path="C:\\nssm.exe", service_name="HydraAdminAgent",
            delay_sec=3, log_path=str(tmp_path / "x.log"),
        )
        _, kwargs = p.call_args
        # Windows: DETACHED_PROCESS | CREATE_NO_WINDOW
        assert kwargs.get("creationflags") == (0x00000008 | 0x08000000)
        assert "start_new_session" not in kwargs


def test_spawn_helper_uses_start_new_session_on_posix(tmp_path, monkeypatch):
    import worker.agent_self_restart as mod
    monkeypatch.setattr(mod.sys, "platform", "linux")
    fake_proc = MagicMock()
    with patch.object(mod.subprocess, "Popen", return_value=fake_proc) as p:
        mod.spawn_restart_helper(
            nssm_path="/usr/bin/nssm", service_name="HydraAdminAgent",
            delay_sec=3, log_path=str(tmp_path / "x.log"),
        )
        _, kwargs = p.call_args
        assert kwargs.get("start_new_session") is True
        assert "creationflags" not in kwargs


# ───────── 5. execute_command — ack-then-spawn ─────────

def _make_client(ack_response_ok: bool = True, ack_status: int = 200):
    """worker.client.ServerClient mock — _ack 호출 시 응답 제어."""
    client = MagicMock()
    client.headers = {}
    resp = MagicMock()
    resp.status_code = ack_status
    resp.json.return_value = {"ok": ack_response_ok}
    client._request.return_value = resp
    return client


def test_execute_agent_self_restart_fails_when_not_admin_agent(monkeypatch):
    import asyncio
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "desktop_worker")
    client = _make_client()
    with patch("worker.agent_self_restart.spawn_restart_helper") as spawn:
        asyncio.run(execute_command(
            client, {"id": 1, "command": "agent_self_restart", "payload": {}},
        ))
        spawn.assert_not_called()
    # ack 가 failed 로 1번 호출
    call_args = client._request.call_args
    body = call_args.kwargs["json"]
    assert body["status"] == "failed"
    assert "admin_agent" in body["error_message"]


def test_execute_agent_self_restart_fails_when_nssm_missing(monkeypatch, tmp_path):
    import asyncio
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    monkeypatch.delenv("HYDRA_NSSM_PATH", raising=False)
    client = _make_client()
    with patch("worker.agent_self_restart.shutil.which", return_value=None), \
         patch("worker.agent_self_restart._CHOCOLATEY_NSSM", "/nonexistent/nssm"), \
         patch("worker.agent_self_restart.spawn_restart_helper") as spawn:
        asyncio.run(execute_command(
            client, {"id": 2, "command": "agent_self_restart", "payload": {}},
        ))
        spawn.assert_not_called()
    body = client._request.call_args.kwargs["json"]
    assert body["status"] == "failed"
    assert "nssm not found" in body["error_message"]


def test_execute_agent_self_restart_delay_out_of_range(monkeypatch, tmp_path):
    import asyncio
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    nssm = tmp_path / "nssm.exe"
    nssm.write_text("stub")
    monkeypatch.setenv("HYDRA_NSSM_PATH", str(nssm))
    client = _make_client()
    with patch("worker.agent_self_restart.spawn_restart_helper") as spawn:
        asyncio.run(execute_command(
            client, {"id": 3, "command": "agent_self_restart", "payload": {"delay_sec": 999}},
        ))
        spawn.assert_not_called()
    assert client._request.call_args.kwargs["json"]["status"] == "failed"


def test_execute_agent_self_restart_ack_then_spawn_order(monkeypatch, tmp_path):
    """ack 가 spawn 보다 먼저 호출되는지 순서 검증 (Codex 핵심 요구)."""
    import asyncio
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    nssm = tmp_path / "nssm.exe"
    nssm.write_text("stub")
    monkeypatch.setenv("HYDRA_NSSM_PATH", str(nssm))

    events: list[str] = []

    class _Resp:
        status_code = 200
        def json(self): return {"ok": True}

    client = MagicMock()
    client.headers = {}
    def _req(*args, **kwargs):
        events.append("ack")
        return _Resp()
    client._request.side_effect = _req

    def _fake_spawn(**kw):
        events.append("spawn")
        return MagicMock()

    with patch("worker.agent_self_restart.spawn_restart_helper", side_effect=_fake_spawn):
        asyncio.run(execute_command(
            client, {"id": 4, "command": "agent_self_restart", "payload": {"delay_sec": 3}},
        ))
    assert events == ["ack", "spawn"], f"expected ack before spawn, got {events}"
    body = client._request.call_args.kwargs["json"]
    assert body["status"] == "done"
    result = json.loads(body["result"])
    assert result["status"] == "restart_scheduled"
    assert result["delay_sec"] == 3
    assert result["service_name"] == "HydraAdminAgent"
    assert "helper_log" in result


def test_execute_agent_self_restart_does_not_spawn_when_ack_fails(monkeypatch, tmp_path):
    """ack 가 ok=False 또는 5xx 면 spawn 안 함 (Codex 핵심 요구)."""
    import asyncio
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    nssm = tmp_path / "nssm.exe"
    nssm.write_text("stub")
    monkeypatch.setenv("HYDRA_NSSM_PATH", str(nssm))
    client = _make_client(ack_response_ok=False)
    with patch("worker.agent_self_restart.spawn_restart_helper") as spawn:
        asyncio.run(execute_command(
            client, {"id": 5, "command": "agent_self_restart", "payload": {}},
        ))
        spawn.assert_not_called()


def test_execute_agent_self_restart_does_not_spawn_when_ack_5xx(monkeypatch, tmp_path):
    import asyncio
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    nssm = tmp_path / "nssm.exe"
    nssm.write_text("stub")
    monkeypatch.setenv("HYDRA_NSSM_PATH", str(nssm))
    client = _make_client(ack_status=500)
    with patch("worker.agent_self_restart.spawn_restart_helper") as spawn:
        asyncio.run(execute_command(
            client, {"id": 6, "command": "agent_self_restart", "payload": {}},
        ))
        spawn.assert_not_called()


def test_execute_agent_self_restart_reports_error_on_spawn_failure(monkeypatch, tmp_path):
    """spawn 자체가 실패하면 ack 는 이미 done — client.report_error 로 알람."""
    import asyncio
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    nssm = tmp_path / "nssm.exe"
    nssm.write_text("stub")
    monkeypatch.setenv("HYDRA_NSSM_PATH", str(nssm))
    client = _make_client(ack_response_ok=True)
    with patch(
        "worker.agent_self_restart.spawn_restart_helper",
        side_effect=OSError("permission denied"),
    ):
        asyncio.run(execute_command(
            client, {"id": 7, "command": "agent_self_restart", "payload": {}},
        ))
    # ack 는 done 으로 호출됨
    assert client._request.call_args.kwargs["json"]["status"] == "done"
    # report_error 호출됨
    client.report_error.assert_called_once()
    kw = client.report_error.call_args.kwargs
    assert kw["kind"] == "update_fail"
    assert "helper spawn failed" in kw["message"]


# ───────── 6. helper script unit ─────────

def test_helper_script_runs_nssm_after_delay(monkeypatch, tmp_path):
    """helper main 이 sleep 후 nssm restart 호출하고 log 남기는지 검증."""
    import worker.agent_self_restart_helper as helper
    log_path = tmp_path / "helper.log"
    monkeypatch.setattr(helper.sys, "argv", [
        "helper", "0", "HydraAdminAgent", "/fake/nssm", str(log_path),
    ])
    sleep_called = []
    monkeypatch.setattr(helper.time, "sleep", lambda s: sleep_called.append(s))
    fake_rc = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch.object(helper.subprocess, "run", return_value=fake_rc) as mrun:
        rc = helper.main()
    assert rc == 0
    assert mrun.call_args.args[0] == ["/fake/nssm", "restart", "HydraAdminAgent"]
    log_text = log_path.read_text(encoding="utf-8")
    assert "invoking" in log_text
    assert "rc=0" in log_text


def test_helper_script_logs_failure(monkeypatch, tmp_path):
    import worker.agent_self_restart_helper as helper
    log_path = tmp_path / "helper.log"
    monkeypatch.setattr(helper.sys, "argv", [
        "helper", "0", "HydraAdminAgent", "/fake/nssm", str(log_path),
    ])
    monkeypatch.setattr(helper.time, "sleep", lambda s: None)
    with patch.object(helper.subprocess, "run", side_effect=FileNotFoundError("nssm gone")):
        rc = helper.main()
    assert rc == 127
    assert "FileNotFoundError" in log_path.read_text(encoding="utf-8")
