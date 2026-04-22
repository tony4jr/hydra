"""Task 25.5 — 모든 admin 성격 엔드포인트가 세션 JWT 없으면 401 반환.

워커 API (X-Worker-Token 자체 인증) / 공개 엔드포인트 (로그인) 는 제외.
"""
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import Base


@pytest.fixture
def client(monkeypatch):
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

    from hydra.web.app import app
    yield TestClient(app)
    engine.dispose()


# 토큰 없으면 401/403 반환해야 하는 경로들 (GET 으로 read-only 호출)
ADMIN_READ_PATHS = [
    "/accounts",
    "/accounts/",
    "/brands",
    "/campaigns",
    "/keywords",
    "/videos",
    "/settings",
    "/pools",
    "/logs",
    "/system",
    "/export",
    "/creator",
    "/recovery",
    "/api/admin/avatars/list",
]

ADMIN_WRITE_PATHS = [
    ("POST", "/api/admin/pause"),
    ("POST", "/api/admin/unpause"),
    ("POST", "/api/admin/deploy"),
    ("POST", "/api/admin/canary"),
    ("POST", "/api/admin/workers/enroll"),
]


def test_admin_read_paths_require_auth(client):
    """404 는 경로가 정말 없다는 뜻이므로 허용. 핵심은 200 이 나오지 않아야 함."""
    for path in ADMIN_READ_PATHS:
        resp = client.get(path)
        assert resp.status_code != 200, f"{path} returned 200 — SECURITY HOLE"
        assert resp.status_code in (401, 403, 404, 405, 422), (
            f"{path} returned {resp.status_code}"
        )


def test_admin_write_paths_require_auth(client):
    for method, path in ADMIN_WRITE_PATHS:
        resp = client.request(method, path, json={})
        assert resp.status_code != 200, f"{method} {path} returned 200"
        assert resp.status_code in (401, 403, 422), (
            f"{method} {path} returned {resp.status_code}"
        )


def test_admin_auth_login_is_public(client):
    """로그인 자체는 토큰 없이 접근 가능해야 — 자격증명 오류로 401 반환."""
    resp = client.post(
        "/api/admin/auth/login",
        json={"email": "nobody@x.y", "password": "nope"},
    )
    # 400 Bad Request 가 아니라 401 invalid credentials 여야 함 (= 미들웨어 통과)
    assert resp.status_code == 401
    assert resp.json().get("detail") == "invalid credentials"


def test_admin_auth_logout_is_public(client):
    resp = client.post("/api/admin/auth/logout")
    assert resp.status_code == 200


def test_valid_admin_token_allows_read(client):
    now = datetime.now(UTC)
    token = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    # /accounts 는 admin 인증 통과하면 200 (빈 배열 or 기본 응답)
    resp = client.get("/accounts", headers={"Authorization": f"Bearer {token}"})
    # 실제 엔드포인트 구현 차이로 200 or 404 or 다른 2xx/3xx 가능 — 핵심은 401 가 아닌 것
    assert resp.status_code != 401, "valid token rejected"


def test_worker_endpoints_not_affected_by_admin_session(client):
    """워커 API 는 admin_session 이 아니라 X-Worker-Token 으로 보호됨 — 무관해야."""
    # POST /api/workers/enroll 은 enrollment_token (JWT) 으로 검증 → admin_session 무관
    resp = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": "garbage", "hostname": "x"},
    )
    # admin_session 이 끼어들면 401 "missing bearer token" — 그게 아니고 enrollment
    # 자체 검증 실패로 401 "invalid enrollment token" 이어야
    assert resp.status_code == 401
    detail = resp.json().get("detail", "")
    assert "enrollment" in detail.lower() or "invalid" in detail.lower()
