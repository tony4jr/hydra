"""Phase 4 minor follow-ups (3 items).

1. /closed POST 가 timeout/failed 면 noop (status 보존)
2. pending terminal_close 있으면 batch/admin 가 dedup
3. session row 90일 retention (chunks 7일 + session 90일)
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, TerminalChunk, TerminalInput, TerminalSession, Worker, WorkerCommand


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


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
        "agent_id": aid, "agent_token": atoken, "admin_jwt": admin_jwt,
    }
    engine.dispose()


def _admin(env):
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


# ───────── #1: /closed POST timeout/failed → noop ─────────

def test_worker_closed_post_does_not_override_timeout(env):
    db = env["Session"]()
    ts = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
        status="timeout", shell="powershell",
        session_token="tok-T",
        closed_at=datetime.now(UTC),
        error_message="inactivity_timeout_after=900s",
    )
    db.add(ts); db.commit(); db.refresh(ts)
    sid = ts.id
    stok = ts.session_token
    db.close()

    r = env["client"].post(
        f"/api/workers/terminal/{sid}/closed",
        headers={
            "X-Worker-Token": env["agent_token"],
            "X-Terminal-Session-Token": stok,
        },
    )
    assert r.status_code == 200
    assert r.json().get("noop") is True

    db = env["Session"]()
    ts2 = db.get(TerminalSession, sid)
    assert ts2.status == "timeout"  # 변경 안 됨
    assert "inactivity_timeout" in (ts2.error_message or "")
    db.close()


def test_worker_closed_post_does_not_override_failed(env):
    db = env["Session"]()
    ts = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
        status="failed", shell="powershell",
        session_token="tok-F",
        closed_at=datetime.now(UTC),
    )
    db.add(ts); db.commit(); db.refresh(ts)
    sid = ts.id
    db.close()

    r = env["client"].post(
        f"/api/workers/terminal/{sid}/closed",
        headers={
            "X-Worker-Token": env["agent_token"],
            "X-Terminal-Session-Token": "tok-F",
        },
    )
    assert r.status_code == 200
    db = env["Session"]()
    assert db.get(TerminalSession, sid).status == "failed"
    db.close()


# ───────── #2: pending terminal_close dedup ─────────

def test_admin_close_skips_when_pending_close_exists(env):
    """admin /close 가 이미 pending terminal_close 있으면 skip."""
    # session open
    r1 = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/terminal/open",
        headers=_admin(env), json={"shell": "powershell"},
    )
    sid = r1.json()["session_id"]
    stok = r1.json()["session_token"]
    h = {
        "X-Worker-Token": env["agent_token"],
        "X-Terminal-Session-Token": stok,
    }
    env["client"].post(f"/api/workers/terminal/{sid}/active", headers=h)

    # 첫 close → terminal_close 1개 발행
    r2 = env["client"].post(f"/api/admin/terminal/{sid}/close", headers=_admin(env))
    assert r2.status_code == 200
    assert r2.json()["status"] == "closing"

    # 두 번째 close → closing 상태라 noop (Slice 4.1a)
    r3 = env["client"].post(f"/api/admin/terminal/{sid}/close", headers=_admin(env))
    assert r3.json().get("noop") is True

    db = env["Session"]()
    cnt = db.query(WorkerCommand).filter(
        WorkerCommand.command == "terminal_close",
    ).count()
    assert cnt == 1
    db.close()


def test_inactivity_batch_skips_when_pending_close_exists(env):
    """inactivity batch 가 이미 pending close 있는 session 에 명령 재발행 안 함."""
    from hydra.web.routes.terminal import inactivity_timeout_batch
    db = env["Session"]()
    ts = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC) - timedelta(hours=1),
        last_activity_at=datetime.now(UTC) - timedelta(minutes=20),
        status="active", shell="powershell", session_token="tok-i",
    )
    db.add(ts); db.commit(); db.refresh(ts)
    sid = ts.id
    # 이미 pending close 존재
    db.add(WorkerCommand(
        worker_id=env["agent_id"], command="terminal_close",
        payload=json.dumps({"session_id": sid, "session_token": "tok-i"}),
        status="pending", issued_at=datetime.now(UTC),
        target_role="admin_agent",
    ))
    db.commit()
    initial_count = db.query(WorkerCommand).filter(
        WorkerCommand.command == "terminal_close",
    ).count()
    assert initial_count == 1

    n = inactivity_timeout_batch(db)
    db.commit()
    assert n == 1  # session 마킹은 됨
    # 하지만 새 terminal_close 명령은 안 추가
    final_count = db.query(WorkerCommand).filter(
        WorkerCommand.command == "terminal_close",
    ).count()
    assert final_count == 1
    db.close()


def test_max_lifetime_batch_skips_when_pending_close_exists(env):
    from hydra.web.routes.terminal import max_lifetime_batch
    db = env["Session"]()
    ts = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC) - timedelta(hours=5),
        last_activity_at=datetime.now(UTC),
        status="active", shell="powershell", session_token="tok-m",
    )
    db.add(ts); db.commit(); db.refresh(ts)
    sid = ts.id
    db.add(WorkerCommand(
        worker_id=env["agent_id"], command="terminal_close",
        payload=json.dumps({"session_id": sid, "session_token": "tok-m"}),
        status="pending", issued_at=datetime.now(UTC),
        target_role="admin_agent",
    ))
    db.commit()
    n = max_lifetime_batch(db)
    db.commit()
    assert n == 1
    cnt = db.query(WorkerCommand).filter(
        WorkerCommand.command == "terminal_close",
    ).count()
    assert cnt == 1  # 중복 안 됨
    db.close()


# ───────── #3: session row 90일 retention ─────────

def test_retention_deletes_old_sessions_after_90d(env):
    from hydra.web.routes.terminal import retention_cleanup_batch
    db = env["Session"]()
    # 100일 전 closed → 삭제 대상
    ts_ancient = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC) - timedelta(days=100),
        last_activity_at=datetime.now(UTC) - timedelta(days=100),
        closed_at=datetime.now(UTC) - timedelta(days=100),
        status="closed", shell="powershell", session_token="tok-ancient",
    )
    # 30일 전 closed → chunks/inputs 만 삭제 (session 보존)
    ts_30d = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC) - timedelta(days=30),
        last_activity_at=datetime.now(UTC) - timedelta(days=30),
        closed_at=datetime.now(UTC) - timedelta(days=30),
        status="closed", shell="powershell", session_token="tok-30d",
    )
    db.add_all([ts_ancient, ts_30d]); db.commit()
    db.refresh(ts_ancient); db.refresh(ts_30d)

    # 100일 전 세션에 chunks 추가
    db.add(TerminalChunk(
        session_id=ts_ancient.id, stream="stdout", seq=1,
        data="x", byte_size=1, produced_at=datetime.now(UTC),
    ))
    db.commit()

    r = retention_cleanup_batch(db)
    db.commit()
    assert r["sessions_deleted"] == 1  # 100일짜리 row 삭제
    assert r["sessions"] >= 1  # 7일+ closed 세션 (chunks 삭제)
    # 100일 row 사라짐, 30일 row 유지
    assert db.query(TerminalSession).filter_by(session_token="tok-ancient").first() is None
    assert db.query(TerminalSession).filter_by(session_token="tok-30d").first() is not None
    db.close()


def test_retention_keeps_recent_sessions(env):
    """1주일 미만 세션은 chunks 도 유지."""
    from hydra.web.routes.terminal import retention_cleanup_batch
    db = env["Session"]()
    ts = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC) - timedelta(days=2),
        last_activity_at=datetime.now(UTC) - timedelta(days=2),
        closed_at=datetime.now(UTC) - timedelta(days=2),
        status="closed", shell="powershell", session_token="tok-recent",
    )
    db.add(ts); db.commit(); db.refresh(ts)
    db.add(TerminalChunk(
        session_id=ts.id, stream="stdout", seq=1,
        data="x", byte_size=1, produced_at=datetime.now(UTC),
    ))
    db.commit()

    r = retention_cleanup_batch(db)
    db.commit()
    assert r["sessions"] == 0
    assert r["sessions_deleted"] == 0
    assert db.query(TerminalChunk).filter_by(session_id=ts.id).count() == 1
    db.close()
