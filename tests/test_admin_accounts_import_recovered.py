"""M2.2 Stage 0 — POST /api/admin/accounts/import-recovered."""
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


def _payload(**overrides):
    base = {
        "gmail": "r1@x.com",
        "password": "secret",
        "adspower_profile_id": "k1xxx",
        "recovery_email": "r@x.com",
        "youtube_channel_id": "UCabc",
    }
    base.update(overrides)
    return base


def test_import_requires_auth(env):
    r = env["client"].post(
        "/api/admin/accounts/import-recovered",
        json={"accounts": [_payload()]},
    )
    assert r.status_code == 401


def test_import_creates_active_accounts_without_onboarding_task(env):
    r = env["client"].post(
        "/api/admin/accounts/import-recovered",
        headers=_hdr(env),
        json={"accounts": [_payload(gmail="a@x.com", adspower_profile_id="k1a")]},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["imported"]) == 1
    assert body["skipped"] == []

    db = env["session"]()
    acc = db.get(Account, body["imported"][0])
    assert acc.gmail == "a@x.com"
    assert acc.status == "active"
    assert acc.warmup_day == 4
    assert acc.onboard_completed_at is not None
    # 평문 비번 저장 금지 (암호화 확인)
    assert acc.password != "secret"
    # 온보딩 태스크 생성 X
    tasks = db.query(Task).filter_by(account_id=acc.id).all()
    assert len(tasks) == 0
    db.close()


def test_import_bulk_with_skip_on_duplicate(env):
    # 첫 번째 insert
    env["client"].post(
        "/api/admin/accounts/import-recovered",
        headers=_hdr(env),
        json={"accounts": [_payload(gmail="dup@x.com", adspower_profile_id="k1dup")]},
    )

    # 두 번째 bulk: dup gmail + dup profile + 새로운 것
    r = env["client"].post(
        "/api/admin/accounts/import-recovered",
        headers=_hdr(env),
        json={
            "accounts": [
                _payload(gmail="dup@x.com", adspower_profile_id="k1other"),
                _payload(gmail="new1@x.com", adspower_profile_id="k1dup"),
                _payload(gmail="new2@x.com", adspower_profile_id="k1new2"),
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["imported"]) == 1  # 오직 new2
    assert len(body["skipped"]) == 2
    reasons = sorted(s["reason"] for s in body["skipped"])
    assert reasons == ["gmail_exists", "profile_id_exists"]


def test_import_empty_list_ok(env):
    r = env["client"].post(
        "/api/admin/accounts/import-recovered",
        headers=_hdr(env),
        json={"accounts": []},
    )
    assert r.status_code == 200
    assert r.json() == {"imported": [], "skipped": []}
