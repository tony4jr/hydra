"""Task 39 — GET /api/admin/workers/ + PATCH /api/admin/workers/{id}."""
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.enrollment import generate_enrollment_token
from hydra.db.models import Base, Worker


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
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-secret-12345")
    monkeypatch.setenv("SERVER_URL", "https://test.example.com")

    from hydra.web.app import app
    client = TestClient(app)

    # 워커 2대 enroll
    for name in ("w1", "w2"):
        tok = generate_enrollment_token(name, ttl_hours=1)
        client.post(
            "/api/workers/enroll",
            json={"enrollment_token": tok, "hostname": name},
        )

    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {"client": client, "admin_jwt": admin_jwt, "session": TestSession}
    engine.dispose()


def _hdr(env):
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


def test_list_requires_auth(env):
    resp = env["client"].get("/api/admin/workers/")
    assert resp.status_code == 401


def test_list_returns_workers_with_defaults(env):
    resp = env["client"].get("/api/admin/workers/", headers=_hdr(env))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    names = sorted(w["name"] for w in body)
    assert names == ["w1", "w2"]
    for w in body:
        assert w["allowed_task_types"] == ["*"]


def test_patch_requires_auth(env):
    resp = env["client"].patch("/api/admin/workers/1", json={"status": "paused"})
    assert resp.status_code == 401


def test_patch_updates_allowed_task_types(env):
    resp = env["client"].patch(
        "/api/admin/workers/1",
        headers=_hdr(env),
        json={"allowed_task_types": ["comment", "like"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["allowed_task_types"] == ["comment", "like"]

    # DB 반영 확인
    s = env["session"]()
    import json as _json
    w = s.get(Worker, 1)
    assert _json.loads(w.allowed_task_types) == ["comment", "like"]
    s.close()


def test_patch_rejects_unknown_task_type(env):
    resp = env["client"].patch(
        "/api/admin/workers/1",
        headers=_hdr(env),
        json={"allowed_task_types": ["bogus"]},
    )
    assert resp.status_code == 400
    assert "bogus" in resp.json()["detail"]


def test_patch_wildcard_normalizes_to_single_star(env):
    """'*' 과 다른 타입이 같이 오면 '*' 만 유지."""
    resp = env["client"].patch(
        "/api/admin/workers/1",
        headers=_hdr(env),
        json={"allowed_task_types": ["*", "comment"]},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed_task_types"] == ["*"]


def test_patch_toggles_allow_flags_and_status(env):
    resp = env["client"].patch(
        "/api/admin/workers/1",
        headers=_hdr(env),
        json={"allow_preparation": False, "allow_campaign": True, "status": "paused"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allow_preparation"] is False
    assert body["allow_campaign"] is True
    assert body["status"] == "paused"


def test_patch_rejects_invalid_status(env):
    resp = env["client"].patch(
        "/api/admin/workers/1",
        headers=_hdr(env),
        json={"status": "unknown"},
    )
    assert resp.status_code == 400


def test_patch_missing_worker_returns_404(env):
    resp = env["client"].patch(
        "/api/admin/workers/99999",
        headers=_hdr(env),
        json={"status": "online"},
    )
    assert resp.status_code == 404
