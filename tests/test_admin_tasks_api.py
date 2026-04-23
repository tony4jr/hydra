"""Task M2.1-3/4: /api/admin/tasks/{stats,recent}."""
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


# -- stats --
def test_stats_requires_auth(env):
    r = env["client"].get("/api/admin/tasks/stats")
    assert r.status_code == 401


def test_stats_returns_empty_counts_when_no_tasks(env):
    r = env["client"].get("/api/admin/tasks/stats", headers=_hdr(env))
    assert r.status_code == 200
    body = r.json()
    assert body["pending"] == 0
    assert body["running"] == 0
    assert body["done"] == 0
    assert body["failed"] == 0
    assert body["by_type"] == {}


def test_stats_aggregates_by_status_and_type(env):
    db = env["session"]()
    acc = Account(gmail="a@x.com", password="x", adspower_profile_id="p1",
                  status="active")
    db.add(acc); db.flush()
    db.add_all([
        Task(account_id=acc.id, task_type="warmup", status="pending"),
        Task(account_id=acc.id, task_type="warmup", status="pending"),
        Task(account_id=acc.id, task_type="warmup", status="done"),
        Task(account_id=acc.id, task_type="comment", status="running"),
        Task(account_id=acc.id, task_type="comment", status="failed"),
    ])
    db.commit()
    db.close()

    r = env["client"].get("/api/admin/tasks/stats", headers=_hdr(env))
    body = r.json()
    assert body["pending"] == 2
    assert body["running"] == 1
    assert body["done"] == 1
    assert body["failed"] == 1
    assert body["by_type"]["warmup"] == {
        "pending": 2, "running": 0, "done": 1, "failed": 0,
    }
    assert body["by_type"]["comment"] == {
        "pending": 0, "running": 1, "done": 0, "failed": 1,
    }


# -- recent --
def test_recent_requires_auth(env):
    r = env["client"].get("/api/admin/tasks/recent")
    assert r.status_code == 401


def test_recent_returns_latest_first_with_account_and_worker(env):
    db = env["session"]()
    w = Worker(name="w1", token_hash="h")
    acc = Account(gmail="u@x.com", password="x", adspower_profile_id="p1",
                  status="active")
    db.add_all([w, acc]); db.flush()
    db.add_all([
        Task(account_id=acc.id, worker_id=w.id, task_type="warmup", status="done"),
        Task(account_id=acc.id, worker_id=w.id, task_type="comment", status="pending"),
    ])
    db.commit()
    db.close()

    r = env["client"].get("/api/admin/tasks/recent?limit=10", headers=_hdr(env))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    assert items[0]["id"] > items[1]["id"]
    row = items[0]
    assert row["task_type"] == "comment"
    assert row["status"] == "pending"
    assert row["account_gmail"] == "u@x.com"
    assert row["worker_name"] == "w1"


def test_recent_limit_enforced(env):
    db = env["session"]()
    acc = Account(gmail="u@x.com", password="x", adspower_profile_id="p1",
                  status="active")
    db.add(acc); db.flush()
    for i in range(25):
        db.add(Task(account_id=acc.id, task_type="warmup", status="pending"))
    db.commit()
    db.close()

    r = env["client"].get("/api/admin/tasks/recent?limit=5", headers=_hdr(env))
    assert len(r.json()["items"]) == 5
