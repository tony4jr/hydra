import json
from datetime import datetime, timedelta


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
    delta = task.scheduled_at - datetime.utcnow()
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
