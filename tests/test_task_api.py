import pytest
from datetime import UTC, datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from hydra.db.models import Account, Base, Task
from hydra.web.app import app
from hydra.db.session import get_db
from hydra.services.worker_service import register_worker


@pytest.fixture
def client_with_worker():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db

    db = TestSession()
    worker, token = register_worker(db, "PC-1")
    # Add an active account for auto-assignment
    account = Account(gmail="test@gmail.com", password="pass", status="active")
    db.add(account)
    db.flush()
    task = Task(
        task_type="comment",
        priority="normal",
        status="pending",
        payload='{"text":"test"}',
        scheduled_at=datetime.now(UTC),
    )
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    client = TestClient(app)
    yield client, token, task_id

    app.dependency_overrides.clear()
    engine.dispose()


def test_fetch_tasks(client_with_worker):
    client, token, _ = client_with_worker
    resp = client.post("/api/tasks/fetch", headers={"X-Worker-Token": token})
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 1
    assert tasks[0]["task_type"] == "comment"


def test_complete_task(client_with_worker):
    client, token, task_id = client_with_worker
    client.post("/api/tasks/fetch", headers={"X-Worker-Token": token})
    resp = client.post("/api/tasks/complete", json={"task_id": task_id, "result": "done"}, headers={"X-Worker-Token": token})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_fail_and_retry(client_with_worker):
    client, token, task_id = client_with_worker
    client.post("/api/tasks/fetch", headers={"X-Worker-Token": token})
    resp = client.post("/api/tasks/fail", json={"task_id": task_id, "error": "captcha detected"}, headers={"X-Worker-Token": token})
    assert resp.status_code == 200
    assert resp.json()["will_retry"] is True
