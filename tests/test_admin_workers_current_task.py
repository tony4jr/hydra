"""Task M2.1-5: /api/admin/workers/ 응답에 current_task 포함."""
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import Account, Base, Task, Worker


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


def test_worker_list_current_task_null_when_idle(env):
    db = env["session"]()
    db.add(Worker(name="idle", token_hash="h"))
    db.commit()
    db.close()

    r = env["client"].get("/api/admin/workers/", headers=_hdr(env))
    assert r.status_code == 200
    body = r.json()
    assert body[0]["current_task"] is None


def test_worker_list_current_task_filled_when_running(env):
    db = env["session"]()
    w = Worker(name="busy", token_hash="h")
    acc = Account(gmail="u@x.com", password="x", adspower_profile_id="p",
                  status="warmup", warmup_day=1)
    db.add_all([w, acc]); db.flush()
    t = Task(account_id=acc.id, worker_id=w.id, task_type="warmup",
             status="running", started_at=datetime.now(UTC))
    db.add(t); db.commit()
    db.close()

    r = env["client"].get("/api/admin/workers/", headers=_hdr(env))
    body = r.json()
    found = next(w for w in body if w["name"] == "busy")
    assert found["current_task"] is not None
    assert found["current_task"]["task_type"] == "warmup"
    assert found["current_task"]["id"] > 0
