import json
import pytest


def test_complete_create_profile_success_links_and_records_history(db_session):
    from hydra.db.models import Account, Task, AccountProfileHistory
    from hydra.api.tasks import handle_create_profile_result

    acc = Account(gmail="cc1@g.com", password="x", status="registered")
    db_session.add(acc)
    db_session.flush()

    payload = {
        "account_id": acc.id,
        "profile_name": f"hydra_{acc.id}_a",
        "device_hint": "windows_heavy",
        "fingerprint_payload": {"timezone": "Asia/Seoul"},
    }
    task = Task(
        account_id=acc.id, task_type="create_profile",
        status="pending", payload=json.dumps(payload),
    )
    db_session.add(task)
    db_session.commit()

    result = {"profile_id": "new123", "account_id": acc.id,
              "device_hint": "windows_heavy"}
    handle_create_profile_result(db_session, task, result, worker_id=7)

    db_session.refresh(acc)
    assert acc.adspower_profile_id == "new123"
    assert acc.status == "profile_set"
    rows = db_session.query(AccountProfileHistory).filter_by(account_id=acc.id).all()
    assert len(rows) == 1
    assert rows[0].worker_id == 7
    assert rows[0].adspower_profile_id == "new123"


def test_complete_create_profile_duplicate_queues_retire_task(db_session):
    from hydra.db.models import Account, Task
    from hydra.api.tasks import handle_create_profile_result

    acc = Account(gmail="cc2@g.com", password="x",
                  adspower_profile_id="already_there", status="profile_set")
    db_session.add(acc)
    db_session.flush()

    task = Task(
        account_id=acc.id, task_type="create_profile", status="pending",
        payload=json.dumps({"account_id": acc.id, "device_hint": "windows_heavy"}),
    )
    db_session.add(task)
    db_session.commit()

    result = {"profile_id": "duplicate", "account_id": acc.id}
    handle_create_profile_result(db_session, task, result, worker_id=3)

    retire = db_session.query(Task).filter_by(task_type="retire_profile").first()
    assert retire is not None
    retire_payload = json.loads(retire.payload)
    assert retire_payload["profile_id"] == "duplicate"
    assert retire_payload["reason"] == "duplicate_creation"

    db_session.refresh(acc)
    assert acc.adspower_profile_id == "already_there"
