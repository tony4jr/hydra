"""Task 38 — /api/tasks/v2/{task_id}/result/account-created."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.enrollment import generate_enrollment_token
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
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-secret-12345")
    monkeypatch.setenv("SERVER_URL", "https://test.example.com")

    from hydra.web.app import app
    client = TestClient(app)

    # 워커 2대 enroll (소유권 검증용)
    e1 = generate_enrollment_token("w1", ttl_hours=1)
    w1 = client.post("/api/workers/enroll", json={"enrollment_token": e1, "hostname": "w1"}).json()
    e2 = generate_enrollment_token("w2", ttl_hours=1)
    w2 = client.post("/api/workers/enroll", json={"enrollment_token": e2, "hostname": "w2"}).json()

    db = TestSession()
    t_create = Task(
        task_type="create_account", status="running",
        priority="normal", worker_id=w1["worker_id"],
    )
    t_other = Task(
        task_type="comment", status="running",
        priority="normal", worker_id=w1["worker_id"],
    )
    db.add_all([t_create, t_other])
    db.commit()

    yield {
        "client": client,
        "session": TestSession,
        "w1_token": w1["worker_token"],
        "w2_token": w2["worker_token"],
        "task_id": t_create.id,
        "other_task_id": t_other.id,
    }
    engine.dispose()


def _body(**overrides) -> dict:
    default = {
        "gmail": "brandnew1@gmail.com",
        "encrypted_password": "enc:secret!23",
        "adspower_profile_id": "profile-new-001",
        "persona": {"name": "테스트", "age": 27},
        "recovery_email": "rec@example.com",
    }
    default.update(overrides)
    return default


def _path(env) -> str:
    return f"/api/tasks/v2/{env['task_id']}/result/account-created"


def test_successful_upload_creates_account_and_marks_task_done(env):
    resp = env["client"].post(
        _path(env),
        headers={"X-Worker-Token": env["w1_token"]},
        json=_body(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    new_id = body["account_id"]

    db = env["session"]()
    acc = db.get(Account, new_id)
    assert acc.gmail == "brandnew1@gmail.com"
    assert acc.adspower_profile_id == "profile-new-001"
    assert acc.password == "enc:secret!23"  # 서버는 암호화된 상태 그대로 저장

    t = db.get(Task, env["task_id"])
    assert t.status == "done"
    assert t.account_id == new_id
    assert t.completed_at is not None
    db.close()


def test_duplicate_gmail_returns_409(env):
    db = env["session"]()
    db.add(Account(gmail="dup@gmail.com", password="x", adspower_profile_id="other",
                   status="active"))
    db.commit()
    db.close()

    resp = env["client"].post(
        _path(env),
        headers={"X-Worker-Token": env["w1_token"]},
        json=_body(gmail="dup@gmail.com"),
    )
    assert resp.status_code == 409
    assert "gmail" in resp.json()["detail"]


def test_duplicate_adspower_profile_id_returns_409(env):
    db = env["session"]()
    db.add(Account(gmail="other@x.com", password="x", adspower_profile_id="dup-prof",
                   status="active"))
    db.commit()
    db.close()

    resp = env["client"].post(
        _path(env),
        headers={"X-Worker-Token": env["w1_token"]},
        json=_body(adspower_profile_id="dup-prof"),
    )
    assert resp.status_code == 409
    assert "adspower" in resp.json()["detail"]


def test_other_worker_cannot_submit(env):
    resp = env["client"].post(
        _path(env),
        headers={"X-Worker-Token": env["w2_token"]},  # 소유자 아님
        json=_body(),
    )
    assert resp.status_code == 403


def test_wrong_task_type_rejected(env):
    resp = env["client"].post(
        f"/api/tasks/v2/{env['other_task_id']}/result/account-created",
        headers={"X-Worker-Token": env["w1_token"]},
        json=_body(),
    )
    assert resp.status_code == 400


def test_missing_task_returns_404(env):
    resp = env["client"].post(
        "/api/tasks/v2/99999/result/account-created",
        headers={"X-Worker-Token": env["w1_token"]},
        json=_body(),
    )
    assert resp.status_code == 404


def test_missing_worker_token_returns_401(env):
    resp = env["client"].post(_path(env), json=_body())
    assert resp.status_code == 401
