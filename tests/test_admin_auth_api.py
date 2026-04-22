"""Admin auth API — /api/admin/auth/login, /logout + admin_session Depends."""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, User


@pytest.fixture(autouse=True)
def _isolated_db_and_jwt(monkeypatch):
    """in-memory sqlite + 고정 JWT_SECRET 로 테스트 격리."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)
    monkeypatch.setenv("JWT_SECRET", "test-secret-1234567890")

    # 시드 유저
    db = TestSession()
    db.add(User(
        email="testadmin@hydra.local",
        password_hash=hash_password("testpass123"),
        role="admin",
    ))
    db.commit()
    db.close()
    yield
    engine.dispose()


@pytest.fixture
def client():
    # 앱은 import 시점에 session_mod.SessionLocal 을 참조만 하고,
    # 라우트 실행 시점에 해당 심볼을 재조회하므로 monkeypatch 가 반영됨.
    from hydra.web.app import app
    return TestClient(app)


def test_login_success_returns_session_token(client):
    resp = client.post(
        "/api/admin/auth/login",
        json={"email": "testadmin@hydra.local", "password": "testpass123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "admin"
    assert body["user_id"] >= 1
    assert isinstance(body["token"], str) and body["token"].count(".") == 2


def test_login_wrong_password_401(client):
    resp = client.post(
        "/api/admin/auth/login",
        json={"email": "testadmin@hydra.local", "password": "WRONG"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid credentials"


def test_login_nonexistent_user_same_message_401(client):
    """존재 여부 노출 방지 — 동일 메시지."""
    resp = client.post(
        "/api/admin/auth/login",
        json={"email": "ghost@hydra.local", "password": "anything"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid credentials"


def test_logout_noop(client):
    resp = client.post("/api/admin/auth/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_admin_session_depends_accepts_valid_token(client):
    """login 받은 토큰으로 admin_session 이 검증 통과하는지 — 일시 보호 라우트로 확인."""
    login = client.post(
        "/api/admin/auth/login",
        json={"email": "testadmin@hydra.local", "password": "testpass123"},
    )
    token = login.json()["token"]

    # admin_session 을 직접 호출해 검증 (엔드포인트 없이도 함수 레벨 테스트)
    from hydra.web.routes.admin_auth import admin_session
    data = admin_session(authorization=f"Bearer {token}")
    assert data["role"] == "admin"


def test_admin_session_rejects_missing_token():
    from fastapi import HTTPException
    from hydra.web.routes.admin_auth import admin_session
    with pytest.raises(HTTPException) as exc:
        admin_session(authorization="")
    assert exc.value.status_code == 401


def test_admin_session_rejects_invalid_token():
    from fastapi import HTTPException
    from hydra.web.routes.admin_auth import admin_session
    with pytest.raises(HTTPException) as exc:
        admin_session(authorization="Bearer not-a-real-token")
    assert exc.value.status_code == 401
