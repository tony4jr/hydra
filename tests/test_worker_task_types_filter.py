"""Task 37 — Worker.allowed_task_types 필터 (pure + integration)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.enrollment import generate_enrollment_token
from hydra.db.models import Account, Base, Task
from hydra.web.routes.tasks_api import _is_task_allowed, _parse_allowed


# ── pure helpers ──

def test_parse_wildcard():
    assert _parse_allowed('["*"]') == ["*"]


def test_parse_specific_list():
    assert _parse_allowed('["create_account","comment"]') == ["create_account", "comment"]


def test_parse_empty_list():
    assert _parse_allowed("[]") == []


def test_parse_invalid_json_defaults_to_wildcard():
    assert _parse_allowed("not-json") == ["*"]
    assert _parse_allowed(None) == ["*"]
    assert _parse_allowed('{"not":"list"}') == ["*"]


def test_is_allowed_wildcard_accepts_any():
    assert _is_task_allowed("anything", ["*"])
    assert _is_task_allowed("new_task_type", ["*", "other"])


def test_is_allowed_specific_match():
    assert _is_task_allowed("comment", ["comment", "like"])
    assert not _is_task_allowed("comment", ["create_account"])


def test_is_allowed_empty_blocks_all():
    assert not _is_task_allowed("anything", [])


# ── integration: /api/tasks/v2/fetch with worker filter ──

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
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-secret-12345")
    monkeypatch.setenv("SERVER_URL", "https://test.example.com")

    from hydra.web.app import app
    client = TestClient(app)

    etoken = generate_enrollment_token("pc-filter", ttl_hours=1)
    enr = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": etoken, "hostname": "pc-filter"},
    ).json()

    db = TestSession()
    acc_c = Account(gmail="c@x.com", adspower_profile_id="p-c", password="x", status="active")
    acc_w = Account(gmail="w@x.com", adspower_profile_id="p-w", password="x", status="active")
    db.add_all([acc_c, acc_w])
    db.flush()
    db.add_all([
        Task(account_id=acc_c.id, task_type="comment", status="pending", priority="normal"),
        Task(account_id=acc_w.id, task_type="watch_video", status="pending", priority="normal"),
    ])
    db.commit()

    yield {
        "client": client,
        "worker_token": enr["worker_token"],
        "worker_id": enr["worker_id"],
        "session": TestSession,
    }
    engine.dispose()


def _set_allowed(session, worker_id, allowed_json):
    from hydra.db.models import Worker
    s = session()
    w = s.get(Worker, worker_id)
    w.allowed_task_types = allowed_json
    s.commit()
    s.close()


def test_wildcard_worker_picks_first_task(env):
    resp = env["client"].post(
        "/api/tasks/v2/fetch",
        headers={"X-Worker-Token": env["worker_token"]},
    )
    tasks = resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["task_type"] in ("comment", "watch_video")


def test_specialized_worker_only_gets_matching_type(env):
    _set_allowed(env["session"], env["worker_id"], '["watch_video"]')
    resp = env["client"].post(
        "/api/tasks/v2/fetch",
        headers={"X-Worker-Token": env["worker_token"]},
    )
    tasks = resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["task_type"] == "watch_video"


def test_empty_allowed_gets_nothing(env):
    _set_allowed(env["session"], env["worker_id"], "[]")
    resp = env["client"].post(
        "/api/tasks/v2/fetch",
        headers={"X-Worker-Token": env["worker_token"]},
    )
    assert resp.json() == {"tasks": []}
