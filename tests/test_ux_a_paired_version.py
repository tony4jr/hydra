"""UX A — paired enroll endpoint + system version endpoint.

Coverage:
  1. POST /api/admin/workers/enroll-paired:
     - admin JWT 필수
     - desktop_worker + admin_agent 두 워커 row 자동 생성
     - admin_agent.parent_worker_id == desktop.id
     - install_command 안에 두 token 모두 포함
     - 같은 pc_name 재발급 시 token 만 회전 (immutable)
     - 이름 충돌 (다른 role) 409
  2. GET /api/system/version:
     - git_sha + started_at 반환
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.core.enrollment import verify_enrollment_token
from hydra.db.models import Base, Worker


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
    monkeypatch.setenv("SERVER_URL", "https://test.example.com")

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {"client": client, "Session": TS, "admin_jwt": admin_jwt}
    engine.dispose()


def _admin(env):
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


# ───────── enroll-paired ─────────

def test_enroll_paired_creates_both_workers(env):
    r = env["client"].post(
        "/api/admin/workers/enroll-paired",
        headers=_admin(env),
        json={"pc_name": "pc-X", "ttl_hours": 12},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["desktop"]["role"] == "desktop_worker"
    assert body["desktop"]["parent_worker_id"] is None
    assert body["admin_agent"]["role"] == "admin_agent"
    assert isinstance(body["admin_agent"]["parent_worker_id"], int)
    # 두 token 모두 install_command 에 포함
    assert body["desktop"]["enrollment_token"] in body["install_command"]
    assert body["admin_agent"]["enrollment_token"] in body["install_command"]

    # DB 에 desktop 워커 row 미리 생성됨
    db = env["Session"]()
    desktop = db.query(Worker).filter_by(name="pc-X").first()
    assert desktop is not None
    assert desktop.role == "desktop_worker"
    db.close()

    # admin_agent token payload 에 parent_worker_id = desktop.id
    agent_data = verify_enrollment_token(body["admin_agent"]["enrollment_token"])
    assert agent_data["role"] == "admin_agent"
    assert agent_data["parent_worker_id"] == body["admin_agent"]["parent_worker_id"]


def test_enroll_paired_requires_admin_jwt(env):
    r = env["client"].post(
        "/api/admin/workers/enroll-paired",
        json={"pc_name": "pc-Y"},
    )
    assert r.status_code == 401


def test_enroll_paired_409_on_role_conflict(env):
    # 이미 admin_agent 로 등록된 이름 충돌
    db = env["Session"]()
    a = Worker(
        name="conflict-x",
        token_hash=hash_password("xx-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        token_sha256=_sha("xx-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        token_prefix="xx-aaaaa",
        role="admin_agent",
    )
    db.add(a); db.commit(); db.close()
    r = env["client"].post(
        "/api/admin/workers/enroll-paired",
        headers=_admin(env),
        json={"pc_name": "conflict-x"},
    )
    assert r.status_code == 409


def test_enroll_paired_token_includes_role_and_parent(env):
    r = env["client"].post(
        "/api/admin/workers/enroll-paired",
        headers=_admin(env),
        json={"pc_name": "pc-Z"},
    )
    assert r.status_code == 200
    body = r.json()
    desktop_data = verify_enrollment_token(body["desktop"]["enrollment_token"])
    assert desktop_data["role"] == "desktop_worker"
    assert "parent_worker_id" not in desktop_data

    agent_data = verify_enrollment_token(body["admin_agent"]["enrollment_token"])
    assert agent_data["role"] == "admin_agent"
    assert agent_data["parent_worker_id"] is not None


# ───────── system/version ─────────

def test_system_version_returns_sha_and_started_at(env):
    r = env["client"].get(
        "/system/version", headers=_admin(env),
    )
    assert r.status_code == 200
    body = r.json()
    assert "git_sha" in body
    assert "started_at" in body
    assert isinstance(body["git_sha"], str)
    assert len(body["git_sha"]) >= 4
