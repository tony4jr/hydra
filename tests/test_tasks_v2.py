"""Task 21 — /api/tasks/v2/{fetch,complete,fail} API."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.enrollment import generate_enrollment_token
from hydra.db.models import Account, Base, ProfileLock, Task, Worker


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

    # 워커 1대 enroll 해서 worker_token 획득
    etoken = generate_enrollment_token("pc-q", ttl_hours=1)
    enr = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": etoken, "hostname": "pc-q"},
    ).json()
    worker_token = enr["worker_token"]
    worker_id = enr["worker_id"]

    # 계정 + pending 태스크 1개 시드
    db = TestSession()
    acc = Account(
        gmail="a@x.com",
        adspower_profile_id="profile-1",
        password="x",
        status="active",
    )
    db.add(acc)
    db.flush()
    task = Task(
        account_id=acc.id,
        task_type="test_task",
        status="pending",
        priority="normal",
        payload="{}",
    )
    db.add(task)
    db.commit()

    yield {
        "client": client,
        "worker_token": worker_token,
        "worker_id": worker_id,
        "session": TestSession,
        "account_id": acc.id,
        "task_id": task.id,
    }
    engine.dispose()


def _hdr(token: str) -> dict:
    return {"X-Worker-Token": token}


def test_fetch_without_token_returns_401(env):
    resp = env["client"].post("/api/tasks/v2/fetch")
    assert resp.status_code == 401


def test_fetch_returns_pending_task_and_marks_running(env):
    resp = env["client"].post("/api/tasks/v2/fetch", headers=_hdr(env["worker_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["id"] == env["task_id"]
    assert body["tasks"][0]["adspower_profile_id"] == "profile-1"

    db = env["session"]()
    t = db.get(Task, env["task_id"])
    assert t.status == "running"
    assert t.worker_id == env["worker_id"]
    lock = db.query(ProfileLock).filter_by(task_id=env["task_id"]).first()
    assert lock is not None
    assert lock.released_at is None
    db.close()


def test_fetch_skips_tasks_on_locked_account(env):
    # 첫 번째 fetch → 락 획득
    env["client"].post("/api/tasks/v2/fetch", headers=_hdr(env["worker_token"]))

    # 동일 account 에 두 번째 pending 태스크 추가
    db = env["session"]()
    t2 = Task(account_id=env["account_id"], task_type="t2", status="pending", priority="normal")
    db.add(t2)
    db.commit()
    db.close()

    # 같은 워커로 다시 fetch — 같은 account 의 기존 락 때문에 빈 결과
    resp = env["client"].post("/api/tasks/v2/fetch", headers=_hdr(env["worker_token"]))
    assert resp.json() == {"tasks": []}


def test_complete_releases_lock(env):
    env["client"].post("/api/tasks/v2/fetch", headers=_hdr(env["worker_token"]))

    resp = env["client"].post(
        "/api/tasks/v2/complete",
        headers=_hdr(env["worker_token"]),
        json={"task_id": env["task_id"], "result": '{"ok":true}'},
    )
    assert resp.status_code == 200

    db = env["session"]()
    t = db.get(Task, env["task_id"])
    assert t.status == "done"
    lock = db.query(ProfileLock).filter_by(task_id=env["task_id"]).first()
    assert lock.released_at is not None
    db.close()


def test_fail_releases_lock_and_stores_error(env):
    env["client"].post("/api/tasks/v2/fetch", headers=_hdr(env["worker_token"]))

    resp = env["client"].post(
        "/api/tasks/v2/fail",
        headers=_hdr(env["worker_token"]),
        json={"task_id": env["task_id"], "error": "browser crashed"},
    )
    assert resp.status_code == 200

    db = env["session"]()
    t = db.get(Task, env["task_id"])
    assert t.status == "failed"
    assert t.error_message == "browser crashed"
    lock = db.query(ProfileLock).filter_by(task_id=env["task_id"]).first()
    assert lock.released_at is not None
    db.close()


def test_complete_on_other_workers_task_returns_403(env):
    env["client"].post("/api/tasks/v2/fetch", headers=_hdr(env["worker_token"]))

    # 다른 워커 enroll
    etoken2 = generate_enrollment_token("pc-other", ttl_hours=1)
    other = env["client"].post(
        "/api/workers/enroll",
        json={"enrollment_token": etoken2, "hostname": "pc-other"},
    ).json()

    resp = env["client"].post(
        "/api/tasks/v2/complete",
        headers=_hdr(other["worker_token"]),
        json={"task_id": env["task_id"]},
    )
    assert resp.status_code == 403


def test_fetch_returns_empty_when_no_pending(env):
    # 기존 pending 을 done 으로 바꿔 버림
    db = env["session"]()
    t = db.get(Task, env["task_id"])
    t.status = "done"
    db.commit()
    db.close()

    resp = env["client"].post("/api/tasks/v2/fetch", headers=_hdr(env["worker_token"]))
    assert resp.json() == {"tasks": []}


def test_complete_onboarding_auto_enqueues_warmup(env):
    """M1-7: complete 훅이 orchestrator 전이 유발."""
    from hydra.db.models import Account, Task

    # 기존 pending account 지우고 새 시나리오 셋업
    db = env["session"]()
    db.query(Task).delete()
    db.query(Account).delete()
    acc = Account(
        gmail="onb@x.com", password="x",
        adspower_profile_id="p-onb", status="registered",
    )
    db.add(acc); db.flush()
    db.add(Task(
        account_id=acc.id, task_type="onboarding_verify",
        status="pending", priority="normal",
    ))
    db.commit()
    acc_id = acc.id
    db.close()

    # 워커가 fetch 해서 running 으로 만들기
    fetch_resp = env["client"].post(
        "/api/tasks/v2/fetch",
        headers={"X-Worker-Token": env["worker_token"]},
    )
    fetched = fetch_resp.json()["tasks"][0]
    tid = fetched["id"]

    # complete 호출
    r = env["client"].post(
        "/api/tasks/v2/complete",
        headers={"X-Worker-Token": env["worker_token"]},
        json={"task_id": tid},
    )
    assert r.status_code == 200

    # orchestrator 훅 동작 확인
    db = env["session"]()
    acc = db.get(Account, acc_id)
    assert acc.status == "warmup"
    assert acc.warmup_day == 1
    warmup_task = db.query(Task).filter_by(
        account_id=acc_id, task_type="warmup", status="pending",
    ).first()
    assert warmup_task is not None
    db.close()
