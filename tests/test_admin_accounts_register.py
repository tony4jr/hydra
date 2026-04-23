"""Task M1-6: POST /api/admin/accounts/register."""
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import Account, Base, Task


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
    monkeypatch.setenv(
        "HYDRA_ENCRYPTION_KEY",
        "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=",
    )

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    token = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {"client": client, "token": token, "session": TestSession}
    engine.dispose()


def _hdr(env):
    return {"Authorization": f"Bearer {env['token']}"}


def test_register_requires_auth(env):
    r = env["client"].post("/api/admin/accounts/register", json={
        "gmail": "a@x.com", "password": "p", "adspower_profile_id": "p1",
    })
    assert r.status_code == 401


def test_register_creates_account_and_enqueues_onboarding(env):
    r = env["client"].post(
        "/api/admin/accounts/register",
        headers=_hdr(env),
        json={
            "gmail": "new@x.com",
            "password": "Plain!Pass123",
            "adspower_profile_id": "prof-new",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] >= 1

    db = env["session"]()
    acc = db.get(Account, body["account_id"])
    assert acc.gmail == "new@x.com"
    assert acc.status == "registered"
    assert acc.password != "Plain!Pass123"  # 암호화 확인

    tasks = db.query(Task).filter_by(account_id=acc.id).all()
    assert len(tasks) == 1
    assert tasks[0].task_type == "onboarding_verify"
    assert tasks[0].status == "pending"
    db.close()


def test_register_duplicate_gmail_409(env):
    env["client"].post(
        "/api/admin/accounts/register",
        headers=_hdr(env),
        json={"gmail": "dup@x.com", "password": "p", "adspower_profile_id": "p1"},
    )
    r = env["client"].post(
        "/api/admin/accounts/register",
        headers=_hdr(env),
        json={"gmail": "dup@x.com", "password": "p2", "adspower_profile_id": "p2"},
    )
    assert r.status_code == 409


def test_register_duplicate_profile_id_409(env):
    env["client"].post(
        "/api/admin/accounts/register",
        headers=_hdr(env),
        json={"gmail": "a@x.com", "password": "p", "adspower_profile_id": "same"},
    )
    r = env["client"].post(
        "/api/admin/accounts/register",
        headers=_hdr(env),
        json={"gmail": "b@x.com", "password": "p", "adspower_profile_id": "same"},
    )
    assert r.status_code == 409
