"""T14/T15 — 태그/FP 회전 어드민 엔드포인트."""
import json
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import Account, Base, Worker, WorkerCommand


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
    for i in range(3):
        db.add(Account(
            gmail=f"u{i}@x.com", password="enc",
            adspower_profile_id=f"k1{i}", status="active",
        ))
    db.add(Worker(name="w1", status="online"))
    db.commit(); db.close()

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {"client": client, "admin_jwt": admin_jwt, "Session": TestSession}
    engine.dispose()


def _h(env): return {"Authorization": f"Bearer {env['admin_jwt']}"}


def test_tag_add_and_query(env):
    # 계정 1, 2 에 'brand:탈모' 태그
    env["client"].post(
        "/api/admin/adspower/accounts/tag",
        headers=_h(env),
        json={"account_ids": [1, 2], "tag": "brand:탈모", "action": "add"},
    )
    r = env["client"].get(
        "/api/admin/adspower/accounts/by-tag/brand:탈모",
        headers=_h(env),
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert all("brand:탈모" in i["tags"] for i in items)


def test_tag_remove(env):
    env["client"].post("/api/admin/adspower/accounts/tag", headers=_h(env),
                       json={"account_ids": [1], "tag": "brand:탈모", "action": "add"})
    env["client"].post("/api/admin/adspower/accounts/tag", headers=_h(env),
                       json={"account_ids": [1], "tag": "brand:탈모", "action": "remove"})
    r = env["client"].get("/api/admin/adspower/accounts/by-tag/brand:탈모", headers=_h(env))
    assert r.json() == []


def test_fp_rotation_dry_run(env):
    r = env["client"].post(
        "/api/admin/adspower/fingerprint-rotation",
        headers=_h(env),
        json={"days_since_last": 30, "max_per_run": 5, "dry_run": True},
    )
    body = r.json()
    assert body["dry_run"] is True
    assert body["candidates"] >= 1
    assert body["scheduled"] == 0  # dry_run 이므로 발행 안 함

    db = env["Session"]()
    assert db.query(WorkerCommand).count() == 0
    db.close()


def test_fp_rotation_actual_dispatches_commands(env):
    r = env["client"].post(
        "/api/admin/adspower/fingerprint-rotation",
        headers=_h(env),
        json={"days_since_last": 30, "max_per_run": 2, "dry_run": False},
    )
    body = r.json()
    assert body["scheduled"] == 2
    db = env["Session"]()
    cmds = db.query(WorkerCommand).all()
    assert len(cmds) == 2
    assert all(c.command == "refresh_fingerprint" for c in cmds)
    assert all(json.loads(c.payload).get("profile_ids") for c in cmds)
    db.close()


def test_fp_rotation_no_online_worker_409(env):
    # 워커 offline 으로 변경
    db = env["Session"]()
    w = db.query(Worker).first()
    w.status = "offline"
    db.commit(); db.close()

    r = env["client"].post(
        "/api/admin/adspower/fingerprint-rotation",
        headers=_h(env),
        json={"days_since_last": 30, "max_per_run": 1, "dry_run": False},
    )
    assert r.status_code == 409


def test_admin_endpoints_require_auth(env):
    assert env["client"].post("/api/admin/adspower/accounts/tag", json={
        "account_ids": [1], "tag": "x", "action": "add",
    }).status_code == 401
    assert env["client"].post("/api/admin/adspower/fingerprint-rotation", json={
        "days_since_last": 30,
    }).status_code == 401
