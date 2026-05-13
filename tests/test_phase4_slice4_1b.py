"""Phase 4 Slice 4.1b — worker terminal_open/close + registry + UTF-8 + shutdown.

Coverage:
  1. open_session: spawn shell + active POST 성공 → registry 등록
  2. open_session: 같은 session_id 이미 등록 (살아있음) → no-op + active 재시도
  3. open_session: 등록되어 있지만 죽음 → 정리 + 새 spawn
  4. open_session: active POST 실패 → process kill + failed POST + ok=False
  5. open_session: spawn 즉시 exit → failed POST + ok=False
  6. close_session: terminate + closed POST + registry 제거
  7. close_session: 이미 죽었거나 없음 → closed POST 만 (graceful)
  8. shutdown_all: 모든 registry process kill + 비움 + count 반환
  9. dispatcher (commands.execute_command):
     - terminal_open: HYDRA_PROCESS_ROLE != admin_agent → fail-closed
     - terminal_open: payload session_id/token 누락 → fail-closed
     - terminal_open: 정상 → agent_terminal.open_session 호출 + ack done
     - terminal_close: 정상 → close_session 호출 + ack done
 10. UTF-8 chcp 65001 + InputEncoding/OutputEncoding 이 PowerShell startup 인자에 포함
 11. shell whitelist
"""
from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import MagicMock, patch, call

import pytest


@pytest.fixture(autouse=True)
def _clear_registry():
    from worker import agent_terminal as _term
    _term.clear_registry_for_testing()
    yield
    _term.clear_registry_for_testing()


def _make_client(active_ok: bool = True, closed_ok: bool = True):
    """ServerClient mock — _request 결과 제어."""
    client = MagicMock()
    client.headers = {}

    def _req(method, path, **kw):
        resp = MagicMock()
        resp.status_code = 200
        if "/active" in path:
            resp.status_code = 200 if active_ok else 403
            resp.json.return_value = {"ok": active_ok, "status": "active"}
        elif "/closed" in path:
            resp.status_code = 200 if closed_ok else 500
            resp.json.return_value = {"ok": closed_ok}
        elif "/failed" in path:
            resp.json.return_value = {"ok": True}
        else:
            resp.json.return_value = {"ok": True}
        return resp

    client._request.side_effect = _req
    return client


# ───────── PowerShell UTF-8 startup script ─────────

def test_ps_startup_script_includes_utf8_initialization():
    from worker.agent_terminal import _PS_STARTUP_SCRIPT
    assert "chcp 65001" in _PS_STARTUP_SCRIPT
    assert "InputEncoding=[Text.Encoding]::UTF8" in _PS_STARTUP_SCRIPT
    assert "OutputEncoding=[Text.Encoding]::UTF8" in _PS_STARTUP_SCRIPT


def test_spawn_shell_powershell_argv_on_windows(monkeypatch):
    from worker import agent_terminal as _term
    monkeypatch.setattr(_term.sys, "platform", "win32")
    fake_proc = MagicMock(returncode=None)
    fake_proc.wait.side_effect = _term.subprocess.TimeoutExpired(cmd="x", timeout=0.1)
    fake_proc.poll.return_value = None
    with patch.object(_term.subprocess, "Popen", return_value=fake_proc) as p:
        _term._spawn_shell("powershell")
        argv = p.call_args.args[0]
        assert argv[0] == "powershell.exe"
        assert "-NoExit" in argv
        assert "-NoLogo" in argv
        assert "-NoProfile" in argv
        # startup script 가 -Command 다음 인자
        cmd_idx = argv.index("-Command")
        startup = argv[cmd_idx + 1]
        assert "chcp 65001" in startup


def test_spawn_shell_rejects_unknown_shell():
    from worker.agent_terminal import _spawn_shell
    with pytest.raises(ValueError, match="unsupported shell"):
        _spawn_shell("evil_shell")


# ───────── open_session ─────────

def _fake_alive_proc(pid: int = 1234):
    p = MagicMock()
    p.pid = pid
    p.poll.return_value = None  # 살아있음
    p.wait.side_effect = __import__("subprocess").TimeoutExpired(cmd="x", timeout=0.1)
    p.terminate = MagicMock()
    p.kill = MagicMock()
    return p


def test_open_session_spawn_and_active_post(monkeypatch):
    from worker import agent_terminal as _term
    client = _make_client(active_ok=True)
    fake_proc = _fake_alive_proc(pid=1111)
    with patch.object(_term, "_spawn_shell", return_value=fake_proc) as mspawn:
        out = _term.open_session(client, 7, "tok-abc", "powershell")
    assert out["ok"] is True
    assert out["pid"] == 1111
    assert 7 in _term._REGISTRY
    mspawn.assert_called_once_with("powershell")
    # active POST 호출됨
    calls = [c.args[1] for c in client._request.call_args_list]
    assert any("/active" in p for p in calls)


def test_open_session_idempotent_when_existing_alive(monkeypatch):
    """같은 session_id 재요청 시 spawn 호출 안 함, active POST 만 재시도."""
    from worker import agent_terminal as _term
    fake_proc = _fake_alive_proc(pid=2222)
    _term._REGISTRY[5] = {"proc": fake_proc, "session_token": "tok-5", "shell": "powershell"}

    client = _make_client(active_ok=True)
    with patch.object(_term, "_spawn_shell") as mspawn:
        out = _term.open_session(client, 5, "tok-5", "powershell")
    mspawn.assert_not_called()
    assert out["noop"] is True
    assert out["pid"] == 2222
    # active POST 는 호출됨 (lease redelivery 시 server 가 active 마킹 누락 가능성 대비)
    calls = [c.args[1] for c in client._request.call_args_list]
    assert any("/active" in p for p in calls)


def test_open_session_cleans_up_dead_registry(monkeypatch):
    from worker import agent_terminal as _term
    dead_proc = MagicMock()
    dead_proc.poll.return_value = 1  # 죽음
    _term._REGISTRY[3] = {"proc": dead_proc, "session_token": "tok-old", "shell": "powershell"}

    new_proc = _fake_alive_proc(pid=3333)
    client = _make_client(active_ok=True)
    with patch.object(_term, "_spawn_shell", return_value=new_proc):
        out = _term.open_session(client, 3, "tok-3", "powershell")
    assert out["ok"] is True
    assert _term._REGISTRY[3]["proc"].pid == 3333
    assert _term._REGISTRY[3]["session_token"] == "tok-3"


def test_open_session_active_post_fail_kills_process(monkeypatch):
    from worker import agent_terminal as _term
    fake_proc = _fake_alive_proc(pid=4444)
    client = _make_client(active_ok=False)
    with patch.object(_term, "_spawn_shell", return_value=fake_proc):
        out = _term.open_session(client, 8, "tok-8", "powershell")
    assert out["ok"] is False
    assert "active_post_failed" in out["error"]
    fake_proc.terminate.assert_called()
    assert 8 not in _term._REGISTRY
    # failed POST 호출됨
    calls = [c.args[1] for c in client._request.call_args_list]
    assert any("/failed" in p for p in calls)


def test_open_session_spawn_exits_immediately(monkeypatch):
    """spawn 직후 process 가 즉시 exit (rc != None) → failed POST."""
    from worker import agent_terminal as _term
    p = MagicMock()
    p.pid = 5555
    p.poll.return_value = None
    p.wait.return_value = 1  # rc=1 즉시 반환 (TimeoutExpired 안 던짐)
    client = _make_client()
    with patch.object(_term, "_spawn_shell", return_value=p):
        out = _term.open_session(client, 9, "tok-9", "powershell")
    assert out["ok"] is False
    assert "spawn exited" in out["error"]
    assert 9 not in _term._REGISTRY


def test_open_session_spawn_exception(monkeypatch):
    from worker import agent_terminal as _term
    client = _make_client()
    with patch.object(_term, "_spawn_shell", side_effect=OSError("denied")):
        out = _term.open_session(client, 10, "tok-10", "powershell")
    assert out["ok"] is False
    assert "spawn_error" in out["error"]
    calls = [c.args[1] for c in client._request.call_args_list]
    assert any("/failed" in p for p in calls)


# ───────── close_session ─────────

def test_close_session_terminates_and_posts_closed(monkeypatch):
    from worker import agent_terminal as _term
    proc = _fake_alive_proc(pid=6666)
    proc.wait.side_effect = [None]  # terminate 후 wait 성공
    _term._REGISTRY[12] = {"proc": proc, "session_token": "tok-12", "shell": "powershell"}
    client = _make_client()
    out = _term.close_session(client, 12, "tok-12")
    assert out["ok"] is True
    proc.terminate.assert_called()
    assert 12 not in _term._REGISTRY
    calls = [c.args[1] for c in client._request.call_args_list]
    assert any("/closed" in p for p in calls)


def test_close_session_no_process_just_posts_closed():
    from worker import agent_terminal as _term
    client = _make_client()
    out = _term.close_session(client, 99, "tok-99")
    assert out["ok"] is True
    calls = [c.args[1] for c in client._request.call_args_list]
    assert any("/closed" in p for p in calls)


# ───────── shutdown_all ─────────

def test_shutdown_all_terminates_all_registered():
    from worker import agent_terminal as _term
    p1 = _fake_alive_proc(pid=7001)
    p1.wait.side_effect = [None]
    p2 = _fake_alive_proc(pid=7002)
    p2.wait.side_effect = [None]
    _term._REGISTRY[1] = {"proc": p1, "session_token": "tok-1", "shell": "powershell"}
    _term._REGISTRY[2] = {"proc": p2, "session_token": "tok-2", "shell": "powershell"}
    n = _term.shutdown_all()
    assert n == 2
    assert len(_term._REGISTRY) == 0
    p1.terminate.assert_called()
    p2.terminate.assert_called()


def test_get_registered_sessions_filters_dead():
    from worker import agent_terminal as _term
    alive = _fake_alive_proc(pid=8001)
    dead = MagicMock(); dead.poll.return_value = 1
    _term._REGISTRY[1] = {"proc": alive, "session_token": "t1", "shell": "powershell"}
    _term._REGISTRY[2] = {"proc": dead, "session_token": "t2", "shell": "powershell"}
    assert _term.get_registered_sessions() == [1]


# ───────── dispatcher (commands.execute_command) ─────────

def test_dispatcher_terminal_open_requires_admin_agent(monkeypatch):
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "desktop_worker")
    client = _make_client()
    with patch("worker.agent_terminal.open_session") as mopen:
        asyncio.run(execute_command(client, {
            "id": 1, "command": "terminal_open",
            "payload": {"session_id": 1, "session_token": "tok", "shell": "powershell"},
        }))
        mopen.assert_not_called()
    body = client._request.call_args.kwargs["json"]
    assert body["status"] == "failed"
    assert "admin_agent" in body["error_message"]


def test_dispatcher_terminal_open_missing_payload(monkeypatch):
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    client = _make_client()
    with patch("worker.agent_terminal.open_session") as mopen:
        asyncio.run(execute_command(client, {
            "id": 2, "command": "terminal_open", "payload": {},
        }))
        mopen.assert_not_called()
    body = client._request.call_args.kwargs["json"]
    assert body["status"] == "failed"


def test_dispatcher_terminal_open_calls_open_session(monkeypatch):
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    client = _make_client()
    with patch(
        "worker.agent_terminal.open_session",
        return_value={"ok": True, "pid": 9999},
    ) as mopen:
        asyncio.run(execute_command(client, {
            "id": 3, "command": "terminal_open",
            "payload": {
                "session_id": 42, "session_token": "tok-42", "shell": "powershell",
            },
        }))
    mopen.assert_called_once_with(client, 42, "tok-42", "powershell")
    body = client._request.call_args.kwargs["json"]
    assert body["status"] == "done"
    result = json.loads(body["result"])
    assert result["pid"] == 9999


def test_server_close_payload_contract_carries_session_token(monkeypatch):
    """Codex Slice 4.1b 핵심 reject 검증: 서버가 발행하는 terminal_close
    payload 가 worker dispatcher 가 요구하는 session_token 을 포함해야 함.
    """
    import hashlib, json as _json
    from datetime import UTC, datetime, timedelta
    import jwt as _jwt
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    import hydra.db.session as session_mod
    from hydra.core.auth import hash_password
    from hydra.db.models import Base, Worker, WorkerCommand, TerminalSession

    def _sha(s):
        return hashlib.sha256(s.encode()).hexdigest()

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")
    monkeypatch.setenv("ENROLLMENT_SECRET", "x"*32)
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")

    db = TestSession()
    dtoken = "d-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    d = Worker(name="d-1", token_hash=hash_password(dtoken),
               token_sha256=_sha(dtoken), token_prefix=dtoken[:8],
               role="desktop_worker")
    db.add(d); db.commit(); db.refresh(d)
    atoken = "a-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    a = Worker(name="a-1", token_hash=hash_password(atoken),
               token_sha256=_sha(atoken), token_prefix=atoken[:8],
               role="admin_agent", parent_worker_id=d.id)
    db.add(a); db.commit(); db.refresh(a)
    aid = a.id
    db.close()

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {admin_jwt}"}

    r1 = client.post(
        f"/api/admin/workers/{aid}/terminal/open",
        headers=headers, json={"shell": "powershell"},
    )
    sid = r1.json()["session_id"]
    r2 = client.post(f"/api/admin/terminal/{sid}/close", headers=headers)
    assert r2.status_code == 200

    db = TestSession()
    close_cmd = db.query(WorkerCommand).filter_by(command="terminal_close").first()
    payload = _json.loads(close_cmd.payload)
    # Codex blocker fix: payload 에 session_token 포함 필수
    assert "session_token" in payload, (
        "server terminal_close payload missing session_token — worker dispatcher will fail"
    )
    assert payload["session_id"] == sid
    assert isinstance(payload["session_token"], str) and len(payload["session_token"]) > 30
    db.close()
    engine.dispose()


def test_dispatcher_terminal_close_calls_close_session(monkeypatch):
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    client = _make_client()
    with patch(
        "worker.agent_terminal.close_session",
        return_value={"ok": True},
    ) as mclose:
        asyncio.run(execute_command(client, {
            "id": 4, "command": "terminal_close",
            "payload": {"session_id": 42, "session_token": "tok-42"},
        }))
    mclose.assert_called_once_with(client, 42, "tok-42")
    body = client._request.call_args.kwargs["json"]
    assert body["status"] == "done"
