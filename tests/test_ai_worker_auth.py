"""M1-9: /api/generate-comment 이 admin_session 이 아닌 worker_auth 로 작동."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.enrollment import generate_enrollment_token
from hydra.db.models import Base


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
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-12345")
    monkeypatch.setenv("SERVER_URL", "https://test.example.com")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")

    from hydra.web.app import app
    client = TestClient(app)
    et = generate_enrollment_token("wk", ttl_hours=1)
    wt = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": et, "hostname": "wk"},
    ).json()["worker_token"]
    yield {"client": client, "wt": wt}
    engine.dispose()


def test_generate_comment_requires_worker_token(env):
    r = env["client"].post("/api/generate-comment", json={"video_id": "x"})
    assert r.status_code == 401


def test_generate_comment_accepts_worker_token(env):
    """실 AI 호출은 외부이므로 200 or 500 가능, 핵심은 401 아닌 것."""
    r = env["client"].post(
        "/api/generate-comment",
        headers={"X-Worker-Token": env["wt"]},
        json={"video_id": "x"},
    )
    assert r.status_code != 401


def test_generate_comment_rejects_admin_jwt(env):
    """admin JWT 로는 이제 통과 안 됨 (worker_auth 만)."""
    from datetime import UTC, datetime, timedelta
    import jwt as _jwt
    now = datetime.now(UTC)
    token = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    r = env["client"].post(
        "/api/generate-comment",
        headers={"Authorization": f"Bearer {token}"},
        json={"video_id": "x"},
    )
    assert r.status_code == 401
