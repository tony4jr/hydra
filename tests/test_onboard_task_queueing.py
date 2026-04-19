"""handle_create_profile_result 가 onboard 태스크 자동 큐잉 하는지 검증."""
import json
import pytest


def test_create_profile_result_auto_queues_onboard(db_session):
    from hydra.db.models import Account, Task
    from hydra.api.tasks import handle_create_profile_result
    from hydra.core import crypto

    acc = Account(
        gmail="ob1@g.com",
        password=crypto.encrypt("pass123"),
        status="registered",
        recovery_email="rec@911panel.us",
        persona=json.dumps({"age": 24, "name": "테스트", "interests": ["축구"]}),
    )
    db_session.add(acc)
    db_session.flush()

    task = Task(
        account_id=acc.id, task_type="create_profile", status="pending",
        payload=json.dumps({
            "account_id": acc.id,
            "device_hint": "windows_heavy",
            "fingerprint_payload": {"timezone": "Asia/Seoul"},
        }),
    )
    db_session.add(task)
    db_session.commit()

    handle_create_profile_result(
        db_session, task, {"profile_id": "newP"}, worker_id=1,
    )

    # account linked
    db_session.refresh(acc)
    assert acc.adspower_profile_id == "newP"

    # onboard task queued with decrypted password and persona
    onboard = db_session.query(Task).filter_by(task_type="onboard").one()
    assert onboard.account_id == acc.id
    assert onboard.status == "pending"
    payload = json.loads(onboard.payload)
    assert payload["email"] == "ob1@g.com"
    assert payload["password"] == "pass123"  # decrypted
    assert payload["recovery_email"] == "rec@911panel.us"
    assert payload["persona"]["name"] == "테스트"


def test_enqueue_onboard_deduplicates(db_session):
    from hydra.db.models import Account, Task
    from hydra.api.tasks import enqueue_onboard_task
    from hydra.core import crypto

    acc = Account(
        gmail="ob2@g.com",
        password=crypto.encrypt("pw"),
        status="profile_set",
        adspower_profile_id="k123",
        persona=json.dumps({"age": 25}),
    )
    db_session.add(acc)
    db_session.commit()

    enqueue_onboard_task(db_session, acc)
    enqueue_onboard_task(db_session, acc)  # should not duplicate

    tasks = db_session.query(Task).filter_by(task_type="onboard", account_id=acc.id).all()
    assert len(tasks) == 1
