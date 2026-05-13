"""Phase 4 Slice 4.3 — interrupt + process tree kill + stale recovery.

Coverage:
  1. POST /admin/terminal/{id}/interrupt
     - WorkerCommand terminal_interrupt + target_role admin_agent
     - 종료 상태면 noop
     - status=active → closing 마킹
  2. POST /workers/terminal/recover-stale
     - 자기 worker 의 active/closing/pending → timeout
  3. worker interrupt_session:
     - registry 에 있으면 _kill_process_tree + closed POST
     - registry 에 없으면 closed POST 만 (noop)
  4. _kill_process_tree:
     - psutil 있으면 children + parent 다 kill
     - psutil 없으면 proc.kill() fallback
  5. dispatcher terminal_interrupt → interrupt_session 호출
  6. stale_recovery_batch helper: status=active + idle > 5분 → timeout
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, TerminalSession, Worker, WorkerCommand


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture(autouse=True)
def _clear_registry():
    from worker import agent_terminal as _term
    _term.clear_registry_for_testing()
    yield
    _term.clear_registry_for_testing()


@pytest.fixture
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TS)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")
    monkeypatch.setenv("ENROLLMENT_SECRET", "x" * 32)
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")

    db = TS()
    atoken = "a-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    a = Worker(
        name="agent-1", token_hash=hash_password(atoken),
        token_sha256=_sha(atoken), token_prefix=atoken[:8],
        role="admin_agent",
    )
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
    yield {
        "client": client, "Session": TS,
        "agent_id": aid, "agent_token": atoken,
        "admin_jwt": admin_jwt,
    }
    engine.dispose()


def _admin(env):
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


def _make_session(env, status="active"):
    db = env["Session"]()
    ts = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
        status=status, shell="powershell",
        session_token=f"tok-{status}",
    )
    db.add(ts); db.commit(); db.refresh(ts)
    sid = ts.id
    db.close()
    return sid


# ───────── 1. admin /interrupt endpoint ─────────

def test_admin_interrupt_issues_command(env):
    sid = _make_session(env, status="active")
    r = env["client"].post(
        f"/api/admin/terminal/{sid}/interrupt", headers=_admin(env),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "closing"
    cmd_id = body["command_id"]

    db = env["Session"]()
    cmd = db.get(WorkerCommand, cmd_id)
    assert cmd.command == "terminal_interrupt"
    assert cmd.target_role == "admin_agent"
    payload = json.loads(cmd.payload)
    assert payload["session_id"] == sid
    assert "session_token" in payload
    db.close()


def test_admin_interrupt_noop_when_closed(env):
    sid = _make_session(env, status="closed")
    r = env["client"].post(
        f"/api/admin/terminal/{sid}/interrupt", headers=_admin(env),
    )
    assert r.status_code == 200
    assert r.json().get("noop") is True


def test_admin_interrupt_404(env):
    r = env["client"].post(
        "/api/admin/terminal/999999/interrupt", headers=_admin(env),
    )
    assert r.status_code == 404


def test_admin_interrupt_requires_admin_jwt(env):
    sid = _make_session(env, status="active")
    r = env["client"].post(f"/api/admin/terminal/{sid}/interrupt")
    assert r.status_code == 401


# ───────── 2. worker /recover-stale ─────────

def test_worker_recover_stale_marks_active_as_timeout(env):
    """admin_agent boot 시 자기 worker 의 active/closing → timeout.
    partial unique 가 active+closing+pending 1개만 허용 → active 1 + closed 1.
    """
    s1 = _make_session(env, status="active")
    db = env["Session"]()
    ts2 = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
        status="closed", shell="powershell",
        session_token="tok-closed",
        closed_at=datetime.now(UTC),
    )
    db.add(ts2); db.commit(); db.refresh(ts2)
    s2 = ts2.id
    db.close()

    r = env["client"].post(
        "/api/workers/terminal/recover-stale",
        headers={"X-Worker-Token": env["agent_token"]},
    )
    assert r.status_code == 200
    assert r.json()["stale_marked"] == 1

    db = env["Session"]()
    assert db.get(TerminalSession, s1).status == "timeout"
    assert db.get(TerminalSession, s2).status == "closed"  # 변경 X
    db.close()


def test_worker_recover_stale_requires_worker_token(env):
    r = env["client"].post("/api/workers/terminal/recover-stale")
    assert r.status_code == 401


# ───────── 3. _kill_process_tree ─────────

def test_kill_process_tree_with_psutil():
    from worker import agent_terminal as _term
    proc = MagicMock(); proc.pid = 12345
    fake_parent = MagicMock()
    fake_child1 = MagicMock(); fake_child2 = MagicMock()
    fake_parent.children.return_value = [fake_child1, fake_child2]
    with patch.dict("sys.modules", {"psutil": MagicMock()}) as mods:
        psutil_mock = mods["psutil"]
        psutil_mock.Process.return_value = fake_parent
        _term._kill_process_tree(proc)
    fake_child1.kill.assert_called()
    fake_child2.kill.assert_called()
    fake_parent.kill.assert_called()


def test_kill_process_tree_fallback_without_psutil(monkeypatch):
    from worker import agent_terminal as _term
    proc = MagicMock(); proc.pid = 999
    # psutil import 실패 시뮬레이트
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **kw):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    _term._kill_process_tree(proc)
    proc.kill.assert_called()


# ───────── 4. interrupt_session ─────────

def test_interrupt_session_kills_tree_and_posts_closed(monkeypatch):
    from worker import agent_terminal as _term
    proc = MagicMock(); proc.pid = 1111
    proc.poll.return_value = None
    _term._REGISTRY[42] = {
        "proc": proc, "session_token": "tok-42", "shell": "powershell",
        "input_stop": MagicMock(),
    }
    client = MagicMock(); client.headers = {}
    resp = MagicMock(); resp.status_code = 200
    client._request.return_value = resp

    with patch.object(_term, "_kill_process_tree") as mkill:
        out = _term.interrupt_session(client, 42, "tok-42")
    assert out["ok"] is True
    assert out["killed_pid"] == 1111
    mkill.assert_called_once_with(proc)
    # closed POST
    calls = [c.args[1] for c in client._request.call_args_list]
    assert any("/closed" in p for p in calls)
    # registry 에서 제거됨
    assert 42 not in _term._REGISTRY


def test_interrupt_session_noop_when_no_registry():
    from worker import agent_terminal as _term
    client = MagicMock(); client.headers = {}
    resp = MagicMock(); resp.status_code = 200
    client._request.return_value = resp
    out = _term.interrupt_session(client, 999, "tok-999")
    assert out.get("noop") is True
    calls = [c.args[1] for c in client._request.call_args_list]
    assert any("/closed" in p for p in calls)


# ───────── 5. dispatcher (commands.execute_command) ─────────

def test_dispatcher_terminal_interrupt_calls_interrupt_session(monkeypatch):
    import asyncio
    from worker.commands import execute_command
    monkeypatch.setenv("HYDRA_PROCESS_ROLE", "admin_agent")
    client = MagicMock(); client.headers = {}
    resp = MagicMock(); resp.status_code = 200
    resp.json.return_value = {"ok": True}
    client._request.return_value = resp

    with patch(
        "worker.agent_terminal.interrupt_session",
        return_value={"ok": True, "killed_pid": 555},
    ) as mint:
        asyncio.run(execute_command(client, {
            "id": 5, "command": "terminal_interrupt",
            "payload": {"session_id": 7, "session_token": "tok-7"},
        }))
    mint.assert_called_once_with(client, 7, "tok-7")


# ───────── 6. stale_recovery_batch helper ─────────

def test_stale_recovery_batch_marks_idle_active(env):
    """1 worker per session 제약 때문에 별도 worker 2개 만들어 검증."""
    from hydra.web.routes.terminal import stale_recovery_batch
    db = env["Session"]()
    # 추가 admin_agent worker
    btoken = "b-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    b = Worker(
        name="agent-2", token_hash=hash_password(btoken),
        token_sha256=_sha(btoken), token_prefix=btoken[:8],
        role="admin_agent",
    )
    db.add(b); db.commit(); db.refresh(b)
    bid = b.id

    # worker A: idle 10분 → stale
    ts_old = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC) - timedelta(minutes=20),
        last_activity_at=datetime.now(UTC) - timedelta(minutes=10),
        status="active", shell="powershell", session_token="tok-old",
    )
    # worker B: idle 1분 → 유지
    ts_fresh = TerminalSession(
        worker_id=bid,
        opened_at=datetime.now(UTC) - timedelta(minutes=2),
        last_activity_at=datetime.now(UTC) - timedelta(minutes=1),
        status="active", shell="powershell", session_token="tok-fresh",
    )
    db.add_all([ts_old, ts_fresh]); db.commit()
    n = stale_recovery_batch(db)
    db.commit()
    assert n == 1
    db.refresh(ts_old); db.refresh(ts_fresh)
    assert ts_old.status == "timeout"
    assert ts_fresh.status == "active"
    db.close()
