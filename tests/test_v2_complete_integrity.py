"""PR-2: v2 complete 결과 무결성 + ActionLog 생성."""
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.enrollment import generate_enrollment_token
from hydra.core.orchestrator import on_task_fail
from hydra.db.models import Account, ActionLog, Base, Task


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

    etoken = generate_enrollment_token("pc-integrity", ttl_hours=1)
    enr = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": etoken, "hostname": "pc-integrity"},
    ).json()

    db = TestSession()
    acc = Account(
        gmail="integrity@x.com",
        adspower_profile_id="profile-integrity",
        password="x",
        status="active",
    )
    db.add(acc)
    db.flush()
    account_id = acc.id
    db.commit()
    db.close()

    yield {
        "client": client,
        "session": TestSession,
        "worker_id": enr["worker_id"],
        "headers": {"X-Worker-Token": enr["worker_token"]},
        "account_id": account_id,
    }
    engine.dispose()


def _running_task(env: dict, task_type: str, payload: dict | None = None) -> int:
    db = env["session"]()
    task = Task(
        account_id=env["account_id"],
        worker_id=env["worker_id"],
        task_type=task_type,
        status="running",
        priority="normal",
        payload=json.dumps(payload or {}, ensure_ascii=False),
        started_at=datetime.now(UTC),
    )
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()
    return task_id


def test_complete_comment_with_empty_comment_id_fails_without_action_log(env):
    task_id = _running_task(env, "comment", {"video_id": "vid-1", "text": "hello"})

    resp = env["client"].post(
        "/api/tasks/v2/complete",
        headers=env["headers"],
        json={"task_id": task_id, "result": json.dumps({"comment_id": ""})},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": True,
        "status": "failed",
        "error": "comment_id_missing_unknown_outcome",
    }

    db = env["session"]()
    task = db.get(Task, task_id)
    assert task.status == "failed"
    assert task.error_message == "comment_id_missing_unknown_outcome"
    assert db.query(ActionLog).count() == 0
    db.close()


def test_complete_reply_with_empty_reply_id_fails(env):
    task_id = _running_task(env, "reply", {"video_id": "vid-1", "text": "reply"})

    resp = env["client"].post(
        "/api/tasks/v2/complete",
        headers=env["headers"],
        json={"task_id": task_id, "result": json.dumps({"reply_id": ""})},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"

    db = env["session"]()
    task = db.get(Task, task_id)
    assert task.status == "failed"
    assert task.error_message == "reply_id_missing"
    assert db.query(ActionLog).count() == 0
    db.close()


def test_complete_comment_with_valid_comment_id_records_action_log(env):
    task_id = _running_task(env, "comment", {"video_id": "vid-1", "text": "hello"})

    resp = env["client"].post(
        "/api/tasks/v2/complete",
        headers=env["headers"],
        json={"task_id": task_id, "result": json.dumps({"comment_id": "Ugxy123"})},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    db = env["session"]()
    task = db.get(Task, task_id)
    assert task.status == "done"
    actions = db.query(ActionLog).all()
    assert len(actions) == 1
    assert actions[0].action_type == "comment"
    assert actions[0].youtube_comment_id == "Ugxy123"
    assert actions[0].video_id == "vid-1"
    db.close()


def test_complete_done_task_is_idempotent_without_duplicate_action_log(env):
    task_id = _running_task(env, "comment", {"video_id": "vid-1", "text": "hello"})
    body = {"task_id": task_id, "result": json.dumps({"comment_id": "Ugxy123"})}

    first = env["client"].post(
        "/api/tasks/v2/complete",
        headers=env["headers"],
        json=body,
    )
    second = env["client"].post(
        "/api/tasks/v2/complete",
        headers=env["headers"],
        json=body,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    db = env["session"]()
    task = db.get(Task, task_id)
    assert task.status == "done"
    assert db.query(ActionLog).count() == 1
    db.close()


def test_complete_like_false_fails_without_action_log(env):
    task_id = _running_task(env, "like", {"video_id": "vid-1"})

    resp = env["client"].post(
        "/api/tasks/v2/complete",
        headers=env["headers"],
        json={"task_id": task_id, "result": json.dumps({"liked": False})},
    )

    assert resp.status_code == 200
    assert resp.json()["error"] == "like_not_confirmed"

    db = env["session"]()
    task = db.get(Task, task_id)
    assert task.status == "failed"
    assert task.error_message == "like_not_confirmed"
    assert db.query(ActionLog).count() == 0
    db.close()


def test_complete_subscribe_false_fails_without_action_log(env):
    task_id = _running_task(env, "subscribe", {"video_id": "vid-1"})

    resp = env["client"].post(
        "/api/tasks/v2/complete",
        headers=env["headers"],
        json={"task_id": task_id, "result": json.dumps({"subscribed": False})},
    )

    assert resp.status_code == 200
    assert resp.json()["error"] == "subscribe_not_confirmed"

    db = env["session"]()
    task = db.get(Task, task_id)
    assert task.status == "failed"
    assert task.error_message == "subscribe_not_confirmed"
    assert db.query(ActionLog).count() == 0
    db.close()


def test_complete_preserves_explicit_pre_submit_error_and_retries(env):
    task_id = _running_task(env, "comment", {"video_id": "vid-1", "text": ""})

    resp = env["client"].post(
        "/api/tasks/v2/complete",
        headers=env["headers"],
        json={"task_id": task_id, "result": json.dumps({"error": "no_text"})},
    )

    assert resp.status_code == 200
    assert resp.json()["error"] == "no_text"

    db = env["session"]()
    task = db.get(Task, task_id)
    assert task.status == "failed"
    assert task.error_message == "no_text"
    retry = db.query(Task).filter_by(status="pending", task_type="comment").one()
    assert retry.retry_count == 1
    assert db.query(ActionLog).count() == 0
    db.close()


def test_unknown_outcome_pattern_does_not_retry_or_suspend_account(env):
    db = env["session"]()
    task = Task(
        account_id=env["account_id"],
        task_type="comment",
        status="failed",
        error_message="comment_id_missing_unknown_outcome",
        retry_count=0,
        max_retries=3,
    )
    db.add(task)
    db.commit()

    on_task_fail(task.id, db)

    account = db.get(Account, env["account_id"])
    assert account.status == "active"
    assert db.query(Task).filter_by(status="pending").count() == 0
    db.close()
