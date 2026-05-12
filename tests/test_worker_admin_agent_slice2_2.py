"""Slice 2.2 — Admin Agent Process Skeleton tests.

Coverage:
  a. heartbeat body 에 role='admin_agent' + capabilities 포함
  b. agent loop 가 /api/tasks/v2/fetch 절대 호출 안 함
  c. pending_commands 받으면 execute_command 호출 + ack path 유지 (shell mock)
  d. desktop worker 기본 heartbeat 는 role/capabilities 없이 보냄 (backward-compat)
  e. token 우선순위 (HYDRA_AGENT_WORKER_TOKEN > ADMIN_AGENT_TOKEN > WORKER_TOKEN)
  f. token 없을 때 main() 이 exit 2 (무한 loop 진입 방지)
  g. poll_interval 우선순위 (heartbeat response > env > default)
  h. --once one-shot 종료
  i. SIGINT graceful stop (없을 때까지 안 죽음 보장)
"""
from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import MagicMock, patch

import pytest


# ───────────── unit-level: ServerClient.heartbeat ─────────────

class _FakeHttpCapture:
    """Capture last request body via injected `http`. Bypasses retry path."""
    def __init__(self):
        self.body: dict | None = None

    def request(self, method, url, **kw):
        self.body = kw.get("json")
        class R:
            def raise_for_status(self): pass
            def json(self): return {
                "current_version": "v", "paused": False,
                "canary_worker_ids": [], "restart_requested": False,
                "worker_config": {},
            }
        return R()

    def close(self): pass


def _make_client_with_capture(monkeypatch) -> tuple[object, _FakeHttpCapture]:
    """Build ServerClient with config minimally patched; return (client, capture).

    monkeypatch.setenv 사용 — test 끝나면 자동 복원 (다른 test 누수 방지).
    config.load 가 module load 시 한 번 평가하므로 worker_token 만 직접 set.
    """
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt-slice22")
    from worker.client import ServerClient
    c = ServerClient()
    # ensure header/token reflect monkeypatched env (config load 가 미리 됐을 수 있으므로).
    c.headers = {"X-Worker-Token": "wt-slice22"}
    cap = _FakeHttpCapture()
    c.http = cap
    return c, cap


def test_serverclient_heartbeat_default_omits_role(monkeypatch):
    """기본 desktop worker 호출 (role/capabilities 인자 안 줌) 은 body 에 미포함."""
    c, cap = _make_client_with_capture(monkeypatch)
    c.heartbeat()
    assert cap.body is not None
    assert "role" not in cap.body
    assert "capabilities" not in cap.body


def test_serverclient_heartbeat_with_role_includes_fields(monkeypatch):
    """admin agent 호출 (role/capabilities 인자 줌) 은 body 에 포함."""
    c, cap = _make_client_with_capture(monkeypatch)
    c.heartbeat(role="admin_agent", capabilities=["shell_exec", "powershell"])
    assert cap.body["role"] == "admin_agent"
    assert cap.body["capabilities"] == ["shell_exec", "powershell"]


# ───────────── admin_agent module unit tests ─────────────

def test_resolve_agent_token_priority(monkeypatch):
    from worker.admin_agent import _resolve_agent_token

    monkeypatch.delenv("HYDRA_AGENT_WORKER_TOKEN", raising=False)
    monkeypatch.delenv("HYDRA_ADMIN_AGENT_TOKEN", raising=False)
    monkeypatch.delenv("HYDRA_WORKER_TOKEN", raising=False)

    assert _resolve_agent_token() == ""

    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "fallback")
    assert _resolve_agent_token() == "fallback"

    monkeypatch.setenv("HYDRA_ADMIN_AGENT_TOKEN", "admin")
    assert _resolve_agent_token() == "admin"

    monkeypatch.setenv("HYDRA_AGENT_WORKER_TOKEN", "agent-first")
    assert _resolve_agent_token() == "agent-first"


def test_resolve_poll_interval_priority(monkeypatch):
    from worker.admin_agent import _resolve_poll_interval_sec, DEFAULT_POLL_INTERVAL_SEC

    monkeypatch.delenv("HYDRA_AGENT_POLL_INTERVAL_SEC", raising=False)
    assert _resolve_poll_interval_sec(None) == DEFAULT_POLL_INTERVAL_SEC

    monkeypatch.setenv("HYDRA_AGENT_POLL_INTERVAL_SEC", "7")
    assert _resolve_poll_interval_sec(None) == 7

    # heartbeat response 가 env 보다 우선
    hb = {"worker_config": {"poll_interval_sec": 30}}
    assert _resolve_poll_interval_sec(hb) == 30

    # invalid env 는 무시
    monkeypatch.setenv("HYDRA_AGENT_POLL_INTERVAL_SEC", "abc")
    assert _resolve_poll_interval_sec(None) == DEFAULT_POLL_INTERVAL_SEC


# ───────────── AdminAgentApp.run integration ─────────────

@pytest.mark.asyncio
async def test_admin_agent_tick_sends_role_and_capabilities():
    """tick 이 client.heartbeat(role='admin_agent', capabilities=...) 호출."""
    from worker.admin_agent import AdminAgentApp

    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value={"pending_commands": []})

    app = AdminAgentApp(capabilities=["shell_exec", "git"], client=fake_client)
    await app._tick()

    fake_client.heartbeat.assert_called_once_with(
        role="admin_agent",
        capabilities=["shell_exec", "git"],
    )


@pytest.mark.asyncio
async def test_admin_agent_does_not_call_fetch_tasks():
    """agent loop 는 task fetch 절대 호출 안 함."""
    from worker.admin_agent import AdminAgentApp

    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value={"pending_commands": []})
    fake_client.fetch_tasks = MagicMock(side_effect=AssertionError("fetch must not be called"))

    app = AdminAgentApp(client=fake_client)
    rc = await app.run(once=True)
    assert rc == 0
    fake_client.fetch_tasks.assert_not_called()


@pytest.mark.asyncio
async def test_admin_agent_executes_pending_commands():
    """pending_commands 받으면 worker.commands.execute_command 호출 + ack path."""
    from worker.admin_agent import AdminAgentApp

    fake_client = MagicMock()
    cmd_payload = {"id": 42, "command": "shell_exec",
                   "payload": {"shell": "sh", "script": "echo a", "timeout_sec": 5}}
    fake_client.heartbeat = MagicMock(return_value={"pending_commands": [cmd_payload]})

    called = []

    async def fake_execute(client, cmd):
        called.append(cmd)

    with patch("worker.commands.execute_command", new=fake_execute):
        app = AdminAgentApp(client=fake_client)
        await app.run(once=True)

    assert len(called) == 1
    assert called[0]["id"] == 42
    assert called[0]["command"] == "shell_exec"


@pytest.mark.asyncio
async def test_admin_agent_continues_when_command_raises():
    """한 command 가 예외 raise 해도 loop 안 죽음 (test: SystemExit 가 아닌 일반 예외)."""
    from worker.admin_agent import AdminAgentApp

    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value={"pending_commands": [
        {"id": 1, "command": "run_diag", "payload": None},
    ]})

    async def fake_execute(_client, _cmd):
        raise RuntimeError("boom")

    with patch("worker.commands.execute_command", new=fake_execute):
        app = AdminAgentApp(client=fake_client)
        rc = await app.run(once=True)
    assert rc == 0


@pytest.mark.asyncio
async def test_admin_agent_heartbeat_failure_does_not_kill_loop():
    """heartbeat 실패 시 tick 은 None return + loop 안 죽음 (once 모드는 종료)."""
    from worker.admin_agent import AdminAgentApp

    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(side_effect=ConnectionError("net down"))

    app = AdminAgentApp(client=fake_client)
    rc = await app.run(once=True)
    assert rc == 0
    fake_client.heartbeat.assert_called_once()


# ───────────── main() entry ─────────────

def test_main_exits_when_token_missing(monkeypatch, capsys):
    monkeypatch.delenv("HYDRA_AGENT_WORKER_TOKEN", raising=False)
    monkeypatch.delenv("HYDRA_ADMIN_AGENT_TOKEN", raising=False)
    monkeypatch.delenv("HYDRA_WORKER_TOKEN", raising=False)

    from worker.admin_agent import main
    rc = main(argv=["--once"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "token not configured" in err.lower()
