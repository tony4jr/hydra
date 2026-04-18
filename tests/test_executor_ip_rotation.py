from datetime import datetime, timedelta, timezone


def test_reschedule_on_ip_failure_increments_retry_and_delays(db_session, monkeypatch):
    from hydra.db.models import Task, Account
    from hydra.core.executor import reschedule_task_for_ip_failure

    acc = Account(gmail="exA@g.com", password="x", status="active")
    db_session.add(acc)
    db_session.flush()

    task = Task(task_type="comment", status="running",
                account_id=acc.id, retry_count=0, payload="{}")
    db_session.add(task)
    db_session.commit()

    from hydra.core.config import settings
    monkeypatch.setattr(settings, "ip_rotation_reschedule_min", 1)
    monkeypatch.setattr(settings, "ip_rotation_reschedule_max", 2)
    monkeypatch.setattr(settings, "ip_rotation_task_retry_max", 5)

    reschedule_task_for_ip_failure(db_session, task)

    db_session.refresh(task)
    assert task.status == "pending"
    assert task.retry_count == 1
    assert task.error_message == "ip_rotation_failed"
    assert task.scheduled_at is not None

    # SQLite strips tzinfo on read — normalise to UTC for comparison
    scheduled = task.scheduled_at
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    now_utc = datetime.now(timezone.utc)
    delta = scheduled - now_utc
    # allow ±30s tolerance for test jitter
    assert timedelta(seconds=30) <= delta <= timedelta(minutes=2, seconds=30)


def test_reschedule_gives_up_after_max(db_session, monkeypatch):
    from hydra.db.models import Task, Account
    from hydra.core.executor import reschedule_task_for_ip_failure

    acc = Account(gmail="exB@g.com", password="x", status="active")
    db_session.add(acc)
    db_session.flush()

    task = Task(task_type="comment", status="running",
                account_id=acc.id, retry_count=4, payload="{}")
    db_session.add(task)
    db_session.commit()

    from hydra.core.config import settings
    monkeypatch.setattr(settings, "ip_rotation_task_retry_max", 5)

    import hydra.infra.telegram as telegram
    sent = []
    monkeypatch.setattr(telegram, "warning", lambda msg: sent.append(msg))

    reschedule_task_for_ip_failure(db_session, task)

    db_session.refresh(task)
    assert task.status == "failed"
    assert task.retry_count == 5
    assert any("5회 누적" in m for m in sent)


def test_reschedule_endpoint_calls_helper(monkeypatch):
    """POST /api/tasks/{id}/reschedule-ip-failure triggers the helper."""
    import pytest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from fastapi.testclient import TestClient
    from hydra.db.models import Base, Task, Account
    from hydra.web.app import app as fastapi_app
    from hydra.db.session import get_db
    from hydra.core.config import settings

    monkeypatch.setattr(settings, "ip_rotation_reschedule_min", 1)
    monkeypatch.setattr(settings, "ip_rotation_reschedule_max", 2)
    monkeypatch.setattr(settings, "ip_rotation_task_retry_max", 5)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_db

    setup_db = TestSession()
    acc = Account(gmail="e2e@g.com", password="x", status="active")
    setup_db.add(acc)
    setup_db.flush()
    task = Task(task_type="comment", status="running",
                account_id=acc.id, retry_count=0, payload="{}")
    setup_db.add(task)
    setup_db.commit()
    task_id = task.id
    setup_db.close()

    client = TestClient(fastapi_app)
    resp = client.post(f"/api/tasks/{task_id}/reschedule-ip-failure", json={"reason": "ip_rotation_failed"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "pending"
    assert data["retry_count"] == 1

    fastapi_app.dependency_overrides.clear()
    engine.dispose()
