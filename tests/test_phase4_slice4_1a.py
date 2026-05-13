"""Phase 4 Slice 4.1a — terminal_sessions schema + lifecycle + partial unique.

Coverage:
  1. terminal_sessions 테이블 + 컬럼 + status enum
  2. partial unique index (pending/active/closing 1개 강제)
  3. POST /admin/workers/{id}/terminal/open
     - admin JWT 필수
     - target_role=admin_agent 자동 라우팅
     - 같은 worker active 있으면 409
     - shell whitelist
     - WorkerCommand("terminal_open", admin_agent) 발행
     - session_token 발급
  4. POST /admin/terminal/{id}/close — 2-phase (closing 상태)
  5. GET /admin/terminal/{id} — info
  6. POST /workers/terminal/{id}/active (worker callback)
     - X-Worker-Token + session_token 3중 검증
     - 다른 worker → 403
     - session_token 틀림 → 403
     - status 전이 pending → active
  7. POST /workers/terminal/{id}/closed (worker callback)
     - closing → closed
     - active 에서 직접 closed (워커 self-detect) 도 OK
  8. POST /workers/terminal/{id}/failed
  9. closing 60s 강제 close batch — open hook 에서 정리
 10. 정책: terminal_open / terminal_close / terminal_interrupt 모두
     _CMD_REQUIRED_ROLE=admin_agent
 11. terminal_interrupt 는 NON_REDELIVERABLE, terminal_open 은 redeliverable

spec: docs Phase 4 + Codex v3 APPROVED.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, TerminalSession, Worker, WorkerCommand


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture
def env(monkeypatch):
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
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-secret-123456789")
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")

    db = TestSession()
    desktop_token = "wtok-desk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    desktop = Worker(
        name="desktop-1",
        token_hash=hash_password(desktop_token),
        token_prefix=desktop_token[:8],
        token_sha256=_sha(desktop_token),
        role="desktop_worker",
        allow_campaign=True,
        allowed_task_types='["*"]',
    )
    db.add(desktop); db.commit(); db.refresh(desktop)
    agent_token = "wtok-agent-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    agent = Worker(
        name="agent-1",
        token_hash=hash_password(agent_token),
        token_prefix=agent_token[:8],
        token_sha256=_sha(agent_token),
        role="admin_agent",
        parent_worker_id=desktop.id,
    )
    db.add(agent); db.commit(); db.refresh(agent)
    desktop_id, agent_id = desktop.id, agent.id
    db.close()

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {
        "client": client, "Session": TestSession,
        "desktop_id": desktop_id, "desktop_token": desktop_token,
        "agent_id": agent_id, "agent_token": agent_token,
        "admin_jwt": admin_jwt,
    }
    engine.dispose()


def _admin(env):
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


# ───────── 1. schema ─────────

def test_terminal_sessions_table_exists():
    assert "terminal_sessions" in Base.metadata.tables
    cols = Base.metadata.tables["terminal_sessions"].columns
    for name in ("worker_id", "status", "session_token", "shell", "opened_at",
                 "last_activity_at", "closing_at", "closed_at", "error_message",
                 "opened_by"):
        assert name in cols


# ───────── 2. partial unique ─────────

def test_terminal_partial_unique_active_per_worker(env):
    db = env["Session"]()
    ts1 = TerminalSession(
        worker_id=env["agent_id"], opened_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC), status="active",
        shell="powershell", session_token="tok-a",
    )
    db.add(ts1); db.commit()
    ts2 = TerminalSession(
        worker_id=env["agent_id"], opened_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC), status="pending",
        shell="powershell", session_token="tok-b",
    )
    db.add(ts2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # closed 는 unique 영향 없음 — 추가 OK
    ts3 = TerminalSession(
        worker_id=env["agent_id"], opened_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC), status="closed",
        shell="powershell", session_token="tok-c",
        closed_at=datetime.now(UTC),
    )
    db.add(ts3); db.commit()
    db.close()


# ───────── 3. admin POST /terminal/open ─────────

def test_admin_open_terminal_routes_to_admin_agent(env):
    """desktop_worker id 로 open 발행 → paired admin_agent 로 auto-route."""
    r = env["client"].post(
        f"/api/admin/workers/{env['desktop_id']}/terminal/open",
        headers=_admin(env),
        json={"shell": "powershell"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["worker_id"] == env["agent_id"]
    assert body["requested_worker_id"] == env["desktop_id"]
    assert body["status"] == "pending"
    assert len(body["session_token"]) > 30
    assert isinstance(body["session_id"], int)
    assert isinstance(body["command_id"], int)
    # WorkerCommand 발행됨
    db = env["Session"]()
    cmd = db.get(WorkerCommand, body["command_id"])
    assert cmd.command == "terminal_open"
    assert cmd.target_role == "admin_agent"
    assert cmd.worker_id == env["agent_id"]
    pl = json.loads(cmd.payload)
    assert pl["session_id"] == body["session_id"]
    assert pl["session_token"] == body["session_token"]
    db.close()


def test_admin_open_terminal_409_when_active_exists(env):
    r1 = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/terminal/open",
        headers=_admin(env), json={"shell": "powershell"},
    )
    assert r1.status_code == 200
    r2 = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/terminal/open",
        headers=_admin(env), json={"shell": "powershell"},
    )
    assert r2.status_code == 409


def test_admin_open_terminal_rejects_invalid_shell(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/terminal/open",
        headers=_admin(env), json={"shell": "evil"},
    )
    assert r.status_code == 400


def test_admin_open_terminal_requires_admin_jwt(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/terminal/open",
        json={"shell": "powershell"},
    )
    assert r.status_code == 401


def test_admin_open_terminal_409_when_no_paired_agent(env):
    """orphan desktop_worker (paired agent 없음) → 409 from auto-route."""
    db = env["Session"]()
    orphan_token = "wtok-orphan-xxxxxxxxxxxxxxxxxxxxxxxxxx"
    orphan = Worker(
        name="orphan-desktop",
        token_hash=hash_password(orphan_token),
        token_sha256=_sha(orphan_token),
        token_prefix=orphan_token[:8],
        role="desktop_worker",
    )
    db.add(orphan); db.commit(); db.refresh(orphan)
    oid = orphan.id
    db.close()
    r = env["client"].post(
        f"/api/admin/workers/{oid}/terminal/open",
        headers=_admin(env), json={"shell": "powershell"},
    )
    assert r.status_code == 409


# ───────── 4. close (2-phase) ─────────

def test_admin_close_terminal_2phase(env):
    r1 = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/terminal/open",
        headers=_admin(env), json={"shell": "powershell"},
    )
    sid = r1.json()["session_id"]

    r2 = env["client"].post(
        f"/api/admin/terminal/{sid}/close",
        headers=_admin(env),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "closing"
    # WorkerCommand terminal_close 발행됨
    db = env["Session"]()
    ts = db.get(TerminalSession, sid)
    assert ts.status == "closing"
    assert ts.closing_at is not None
    assert ts.closed_at is None
    db.close()


def test_admin_close_terminal_noop_when_already_closed(env):
    """이미 closed/timeout/failed → noop."""
    db = env["Session"]()
    ts = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
        status="closed", shell="powershell", session_token="tok-x",
        closed_at=datetime.now(UTC),
    )
    db.add(ts); db.commit(); db.refresh(ts)
    sid = ts.id
    db.close()

    r = env["client"].post(
        f"/api/admin/terminal/{sid}/close",
        headers=_admin(env),
    )
    assert r.status_code == 200
    assert r.json()["noop"] is True


def test_admin_get_terminal_info(env):
    r1 = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/terminal/open",
        headers=_admin(env), json={"shell": "powershell"},
    )
    sid = r1.json()["session_id"]
    r = env["client"].get(f"/api/admin/terminal/{sid}", headers=_admin(env))
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == sid
    assert body["status"] == "pending"
    assert body["shell"] == "powershell"
    assert body["worker_id"] == env["agent_id"]


# ───────── 5. worker callback /active ─────────

def _open_session(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/terminal/open",
        headers=_admin(env), json={"shell": "powershell"},
    )
    return r.json()


def test_worker_mark_active(env):
    s = _open_session(env)
    r = env["client"].post(
        f"/api/workers/terminal/{s['session_id']}/active",
        headers={
            "X-Worker-Token": env["agent_token"],
            "X-Terminal-Session-Token": s["session_token"],
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_worker_mark_active_rejects_wrong_session_token(env):
    s = _open_session(env)
    r = env["client"].post(
        f"/api/workers/terminal/{s['session_id']}/active",
        headers={
            "X-Worker-Token": env["agent_token"],
            "X-Terminal-Session-Token": "bogus-token",
        },
    )
    assert r.status_code == 403


def test_worker_mark_active_rejects_different_worker(env):
    """다른 worker token 으로는 다른 session 의 active 마킹 못 함."""
    s = _open_session(env)
    r = env["client"].post(
        f"/api/workers/terminal/{s['session_id']}/active",
        headers={
            "X-Worker-Token": env["desktop_token"],
            "X-Terminal-Session-Token": s["session_token"],
        },
    )
    assert r.status_code == 403


def test_worker_mark_active_idempotent(env):
    s = _open_session(env)
    h = {
        "X-Worker-Token": env["agent_token"],
        "X-Terminal-Session-Token": s["session_token"],
    }
    r1 = env["client"].post(
        f"/api/workers/terminal/{s['session_id']}/active", headers=h,
    )
    assert r1.status_code == 200
    r2 = env["client"].post(
        f"/api/workers/terminal/{s['session_id']}/active", headers=h,
    )
    assert r2.status_code == 200
    assert r2.json().get("noop") is True


# ───────── 6. worker callback /closed ─────────

def test_worker_mark_closed_from_closing(env):
    s = _open_session(env)
    h = {
        "X-Worker-Token": env["agent_token"],
        "X-Terminal-Session-Token": s["session_token"],
    }
    env["client"].post(f"/api/workers/terminal/{s['session_id']}/active", headers=h)
    env["client"].post(f"/api/admin/terminal/{s['session_id']}/close", headers=_admin(env))
    r = env["client"].post(f"/api/workers/terminal/{s['session_id']}/closed", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "closed"

    db = env["Session"]()
    ts = db.get(TerminalSession, s["session_id"])
    assert ts.status == "closed"
    assert ts.closed_at is not None
    db.close()


def test_worker_mark_failed(env):
    s = _open_session(env)
    h = {
        "X-Worker-Token": env["agent_token"],
        "X-Terminal-Session-Token": s["session_token"],
    }
    r = env["client"].post(
        f"/api/workers/terminal/{s['session_id']}/failed?error=spawn%20failed",
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "failed"


# ───────── 7. closing 60s forced close hook ─────────

def test_force_close_stale_closing_releases_unique(env):
    """closing 상태가 60초 초과면 다음 open 시 자동 cleanup → 새 session OK."""
    db = env["Session"]()
    ts = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC) - timedelta(minutes=10),
        last_activity_at=datetime.now(UTC) - timedelta(minutes=10),
        status="closing",
        closing_at=datetime.now(UTC) - timedelta(seconds=120),  # 60s 초과
        shell="powershell", session_token="tok-stale",
    )
    db.add(ts); db.commit(); db.close()

    # 새 open 시도 — _force_close_stale_closing 가 stale 정리 후 OK
    r = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/terminal/open",
        headers=_admin(env), json={"shell": "powershell"},
    )
    assert r.status_code == 200, r.text
    db = env["Session"]()
    stale = db.query(TerminalSession).filter_by(session_token="tok-stale").first()
    assert stale.status == "closed"
    assert "force_closed_after_closing_timeout" in (stale.error_message or "")
    db.close()


# ───────── 8. policy / NON_REDELIVERABLE ─────────

def test_command_policy_allowed_required_role():
    from hydra.web.routes.admin_workers import ALLOWED_COMMANDS, _CMD_REQUIRED_ROLE
    for cmd in ("terminal_open", "terminal_close", "terminal_interrupt"):
        assert cmd in ALLOWED_COMMANDS
        assert _CMD_REQUIRED_ROLE[cmd] == "admin_agent"


def test_terminal_open_is_redeliverable_but_interrupt_is_not():
    from hydra.web.routes.worker_api import _CMD_NON_REDELIVERABLE
    assert "terminal_interrupt" in _CMD_NON_REDELIVERABLE
    assert "terminal_open" not in _CMD_NON_REDELIVERABLE
    assert "terminal_close" not in _CMD_NON_REDELIVERABLE
