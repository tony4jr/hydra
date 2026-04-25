"""T9 비상정지 — 모든 워커 일괄 paused + stop_all_browsers fan-out."""
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, Worker, WorkerCommand


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
        db.add(Worker(name=f"w{i}", status="online",
                      token_hash=hash_password(f"t{i}")))
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


def test_emergency_stop_pauses_server_and_all_workers(env):
    r = env["client"].post(
        "/api/admin/emergency-stop",
        headers={"Authorization": f"Bearer {env['admin_jwt']}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["paused"] is True
    assert body["emergency"] is True
    assert body["workers_notified"] == 3

    # 모든 워커 paused + paused_reason set
    db = env["Session"]()
    workers = db.query(Worker).all()
    for w in workers:
        assert w.status == "paused"
        assert w.paused_reason == "emergency-stop"

    # 워커마다 stop_all_browsers 명령 1개 생성
    cmds = db.query(WorkerCommand).all()
    assert len(cmds) == 3
    assert all(c.command == "stop_all_browsers" for c in cmds)
    assert all(c.status == "pending" for c in cmds)
    db.close()


def test_emergency_stop_requires_admin(env):
    r = env["client"].post("/api/admin/emergency-stop")
    assert r.status_code == 401
