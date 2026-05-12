"""Slice 2.1 — Worker Admin Agent identity + routing schema tests.

Coverage:
  1. workers 모델에 role / parent_worker_id / capabilities 필드 존재
  2. 기존 worker 는 backfill default role='desktop_worker'
  3. heartbeat 가 role/capabilities 받아 DB 갱신
  4. heartbeat 가 role/capabilities 미보내면 기존 값 유지 (backward-compat)
  5. heartbeat 가 invalid role 거부
  6. admin_agent role worker 는 task fetch 빈 list
  7. desktop_worker role worker 는 task fetch 정상
  8. admin WorkerOut response 가 role/parent_worker_id/capabilities 포함

spec: docs/WORKER_ADMIN_AGENT_TASK_0_0.md Phase 2 → Slice 2.1 identity 분리.
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
from hydra.db.models import Base, Worker, Account, Task


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
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")

    db = TestSession()
    desktop_token = "worker-token-desktop-xxxxxxxxxxxxxxxxxxx"
    agent_token = "worker-token-agent-xxxxxxxxxxxxxxxxxxxxx"
    desktop = Worker(
        name="desktop-1",
        token_hash=hash_password(desktop_token),
        token_prefix=desktop_token[:8],
        token_sha256=_sha(desktop_token),
        allow_campaign=True,
        allowed_task_types='["*"]',
    )
    db.add(desktop); db.commit(); db.refresh(desktop)
    agent = Worker(
        name="agent-1",
        token_hash=hash_password(agent_token),
        token_prefix=agent_token[:8],
        token_sha256=_sha(agent_token),
        role="admin_agent",
        parent_worker_id=desktop.id,
        allow_campaign=True,  # 정책상 무관, 그래도 admin_agent 면 fetch 거부됨
        allowed_task_types='["*"]',
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
        "desktop_token": desktop_token, "desktop_id": desktop_id,
        "agent_token": agent_token, "agent_id": agent_id,
        "admin_jwt": admin_jwt,
    }
    engine.dispose()


def _admin(env) -> dict:
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


def _hb_body(**overrides) -> dict:
    body = {
        "version": "test", "os_type": "linux",
        "cpu_percent": 0.0, "mem_used_mb": 0, "disk_free_gb": 0.0,
        "adb_devices": [], "adspower_version": "", "playwright_browsers_ok": True,
    }
    body.update(overrides)
    return body


# ───────── 1. 모델 필드 존재 ─────────

def test_worker_model_has_role_parent_capabilities():
    """workers 테이블/모델에 새 필드 존재 (기존 worker 도 desktop_worker default)."""
    assert "role" in Worker.__table__.columns
    assert "parent_worker_id" in Worker.__table__.columns
    assert "capabilities" in Worker.__table__.columns
    # default 값 검증 (Python-side)
    col = Worker.__table__.columns["role"]
    assert col.default.arg == "desktop_worker"


# ───────── 2. backfill default ─────────

def test_existing_worker_defaults_to_desktop_worker(env):
    """fixture 에서 role 명시 안 한 desktop-1 은 default desktop_worker."""
    db = env["Session"]()
    try:
        w = db.get(Worker, env["desktop_id"])
        assert w.role == "desktop_worker"
        assert w.parent_worker_id is None
    finally:
        db.close()


# ───────── 3-5. heartbeat 가 role/capabilities 업데이트 ─────────

def test_heartbeat_updates_role_and_capabilities(env):
    body = _hb_body(role="admin_agent", capabilities=["powershell", "git"])
    r = env["client"].post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": env["desktop_token"]},
        json=body,
    )
    assert r.status_code == 200, r.text
    db = env["Session"]()
    try:
        w = db.get(Worker, env["desktop_id"])
        assert w.role == "admin_agent"
        # capabilities 는 JSON 문자열로 저장
        assert json.loads(w.capabilities) == ["powershell", "git"]
    finally:
        db.close()


def test_heartbeat_preserves_role_when_omitted(env):
    """role 안 보내면 기존 값 유지 (backward-compat)."""
    # 1. 먼저 agent_token 의 admin_agent role 그대로
    db = env["Session"]()
    try:
        agent = db.get(Worker, env["agent_id"])
        assert agent.role == "admin_agent"
    finally:
        db.close()

    # 2. heartbeat 에 role/capabilities 없이 보냄 (옛 워커 simulation)
    r = env["client"].post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": env["agent_token"]},
        json=_hb_body(),  # role 미설정
    )
    assert r.status_code == 200

    db = env["Session"]()
    try:
        agent = db.get(Worker, env["agent_id"])
        assert agent.role == "admin_agent"  # 변경되지 않음
    finally:
        db.close()


def test_heartbeat_rejects_invalid_role(env):
    r = env["client"].post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": env["desktop_token"]},
        json=_hb_body(role="superadmin"),
    )
    assert r.status_code == 400
    assert "invalid role" in r.text.lower()


# ───────── 6-7. task fetch guard ─────────

def test_admin_agent_cannot_fetch_tasks(env):
    """admin_agent role 워커는 task fetch 빈 list."""
    # 우선 pending task 1건 만들어둠 (account + task)
    db = env["Session"]()
    try:
        acc = Account(
            gmail="test@example.com",
            password="ENC",
            adspower_profile_id="prof-x",
            status="active",
        )
        db.add(acc); db.commit(); db.refresh(acc)
        t = Task(
            account_id=acc.id,
            task_type="like",
            status="pending",
        )
        db.add(t); db.commit()
    finally:
        db.close()

    r = env["client"].post(
        "/api/tasks/v2/fetch",
        headers={"X-Worker-Token": env["agent_token"]},
    )
    assert r.status_code == 200
    assert r.json() == {"tasks": []}


def test_desktop_worker_can_fetch_tasks(env):
    """desktop_worker role 워커는 task fetch 정상 (account 매칭되면 비어있을 수도)."""
    r = env["client"].post(
        "/api/tasks/v2/fetch",
        headers={"X-Worker-Token": env["desktop_token"]},
    )
    assert r.status_code == 200
    # 비어있을 수도 (auto_assign 등 조건), 단 admin_agent guard 처럼 즉시 short-circuit X.
    # 응답 형식만 확인.
    assert "tasks" in r.json()


# ───────── 8. admin WorkerOut response 새 필드 포함 ─────────

def test_admin_workers_list_returns_new_fields(env):
    """GET /api/admin/workers/ 가 role/parent_worker_id/capabilities 포함."""
    # capabilities 가 있는 워커도 만들기
    body = _hb_body(role="admin_agent", capabilities=["powershell", "git", "scheduler"])
    env["client"].post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": env["agent_token"]},
        json=body,
    )

    r = env["client"].get("/api/admin/workers/", headers=_admin(env))
    assert r.status_code == 200
    workers = r.json()
    by_id = {w["id"]: w for w in workers}

    desktop = by_id[env["desktop_id"]]
    assert "role" in desktop
    assert desktop["role"] == "desktop_worker"
    assert "parent_worker_id" in desktop
    assert desktop["parent_worker_id"] is None
    assert "capabilities" in desktop
    assert desktop["capabilities"] == []  # 보고 안 한 워커

    agent = by_id[env["agent_id"]]
    assert agent["role"] == "admin_agent"
    assert agent["parent_worker_id"] == env["desktop_id"]
    assert agent["capabilities"] == ["powershell", "git", "scheduler"]


def test_admin_workers_response_capabilities_malformed_returns_empty(env):
    """capabilities 가 잘못된 JSON 이어도 빈 list 로 fallback (UI 안 깨짐)."""
    db = env["Session"]()
    try:
        w = db.get(Worker, env["desktop_id"])
        w.capabilities = "not a json"
        db.commit()
    finally:
        db.close()

    r = env["client"].get("/api/admin/workers/", headers=_admin(env))
    assert r.status_code == 200
    desktop = next(w for w in r.json() if w["id"] == env["desktop_id"])
    assert desktop["capabilities"] == []
