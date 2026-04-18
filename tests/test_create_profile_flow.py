import json
import pytest


def test_full_flow_from_persona_to_linked_profile(db_session):
    """Account with persona → auto_queue → Worker 'executes' (mocked) →
    handle_create_profile_result → account linked with history."""
    from hydra.db.models import Account, Task, AccountProfileHistory
    from hydra.web.routes.accounts import auto_queue_create_profile_tasks
    from hydra.api.tasks import handle_create_profile_result

    a = Account(gmail="flow1@g.com", password="x", status="registered",
                persona=json.dumps({
                    "device_hint": "windows_heavy",
                    "name": "이준호", "age": 21,
                    "region": "광주", "occupation": "대학생",
                }))
    db_session.add(a)
    db_session.commit()

    n = auto_queue_create_profile_tasks(db_session, [a])
    assert n == 1
    task = db_session.query(Task).filter_by(task_type="create_profile").one()

    result = {
        "profile_id": "simulated123",
        "account_id": a.id,
        "device_hint": "windows_heavy",
    }
    task.status = "done"
    task.result = json.dumps(result)
    task.worker_id = 7

    handle_create_profile_result(db_session, task, result, worker_id=7)

    db_session.refresh(a)
    assert a.adspower_profile_id == "simulated123"
    assert a.status == "profile_set"

    hist = db_session.query(AccountProfileHistory).filter_by(account_id=a.id).one()
    assert hist.worker_id == 7
    assert hist.device_hint == "windows_heavy"
    snap = json.loads(hist.fingerprint_snapshot)
    assert snap["timezone"] == "Asia/Seoul"


def test_duplicate_creation_does_not_overwrite(db_session):
    """Two workers race both creating profiles → second gets retired."""
    from hydra.db.models import Account, Task
    from hydra.api.tasks import handle_create_profile_result

    a = Account(gmail="flow2@g.com", password="x", status="registered",
                persona=json.dumps({"device_hint": "windows_heavy"}))
    db_session.add(a)
    db_session.commit()

    task1 = Task(account_id=a.id, task_type="create_profile", status="done",
                 payload=json.dumps({"account_id": a.id,
                                     "device_hint": "windows_heavy",
                                     "fingerprint_payload": {}}))
    db_session.add(task1)
    db_session.commit()
    handle_create_profile_result(db_session, task1, {"profile_id": "first"}, worker_id=1)

    task2 = Task(account_id=a.id, task_type="create_profile", status="done",
                 payload=json.dumps({"account_id": a.id,
                                     "device_hint": "windows_heavy",
                                     "fingerprint_payload": {}}))
    db_session.add(task2)
    db_session.commit()
    handle_create_profile_result(db_session, task2, {"profile_id": "second"}, worker_id=2)

    db_session.refresh(a)
    assert a.adspower_profile_id == "first"

    retire = db_session.query(Task).filter_by(task_type="retire_profile").one()
    payload = json.loads(retire.payload)
    assert payload["profile_id"] == "second"
    assert payload["reason"] == "duplicate_creation"
