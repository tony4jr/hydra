import io
import json
import pytest


def test_auto_queue_profile_tasks_after_persona(db_session):
    """Given accounts with personas, enqueue create_profile tasks for each."""
    from hydra.db.models import Account, Task
    from hydra.web.routes.accounts import auto_queue_create_profile_tasks

    a1 = Account(gmail="auto1@g.com", password="x", status="registered",
                 persona=json.dumps({"device_hint": "windows_heavy"}))
    a2 = Account(gmail="auto2@g.com", password="y", status="registered",
                 persona=json.dumps({"device_hint": "mac_heavy"}))
    db_session.add_all([a1, a2])
    db_session.commit()

    n = auto_queue_create_profile_tasks(db_session, [a1, a2])
    assert n == 2

    tasks = db_session.query(Task).filter_by(task_type="create_profile").all()
    assert len(tasks) == 2
    payload_a = json.loads(tasks[0].payload)
    assert "fingerprint_payload" in payload_a
    assert "device_hint" in payload_a
    assert payload_a["profile_name"].startswith("hydra_")


def test_auto_queue_skips_when_profile_exists(db_session):
    from hydra.db.models import Account, Task
    from hydra.web.routes.accounts import auto_queue_create_profile_tasks

    a = Account(gmail="auto3@g.com", password="x",
                adspower_profile_id="already", status="profile_set",
                persona=json.dumps({"device_hint": "windows_heavy"}))
    db_session.add(a)
    db_session.commit()

    n = auto_queue_create_profile_tasks(db_session, [a])
    assert n == 0
    assert db_session.query(Task).filter_by(task_type="create_profile").count() == 0


def test_auto_queue_skips_when_no_persona(db_session):
    from hydra.db.models import Account, Task
    from hydra.web.routes.accounts import auto_queue_create_profile_tasks

    a = Account(gmail="auto4@g.com", password="x", status="registered")
    db_session.add(a)
    db_session.commit()

    n = auto_queue_create_profile_tasks(db_session, [a])
    assert n == 0


def test_auto_queue_skips_when_persona_has_no_device_hint(db_session):
    from hydra.db.models import Account, Task
    from hydra.web.routes.accounts import auto_queue_create_profile_tasks

    a = Account(gmail="auto5@g.com", password="x", status="registered",
                persona=json.dumps({"name": "이준호"}))  # no device_hint
    db_session.add(a)
    db_session.commit()

    n = auto_queue_create_profile_tasks(db_session, [a])
    assert n == 0
