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


def test_auto_process_chain_assigns_persona_and_queues_tasks(db_session, monkeypatch):
    """`_auto_process_new_accounts` runs persona batch + queue tasks in one shot."""
    from hydra.db.models import Account, Task
    import hydra.db.session as db_session_mod
    import hydra.ai.agents.persona_agent as persona_mod

    a1 = Account(gmail="chain1@g.com", password="x", status="registered")
    a2 = Account(gmail="chain2@g.com", password="y", status="registered")
    db_session.add_all([a1, a2])
    db_session.commit()
    ids = [a1.id, a2.id]

    # SessionLocal used inside _auto_process_new_accounts must hand back our fixture
    monkeypatch.setattr(db_session_mod, "SessionLocal", lambda: db_session)

    # stub the Claude-backed batch so we stay offline
    def fake_batch(db, accounts):
        for i, acc in enumerate(accounts):
            acc.persona = json.dumps({
                "device_hint": "windows_heavy",
                "name": f"tester{i}",
                "age": 25,
                "region": "서울",
                "occupation": "회사원",
            })
        db.commit()
    monkeypatch.setattr(persona_mod, "batch_assign_personas", fake_batch)

    # keep fixture alive — _auto_process closes its db copy
    db_session.close = lambda: None  # noqa: E501

    from hydra.web.routes import accounts as accounts_mod
    accounts_mod._auto_process_new_accounts(ids)

    for acc_id in ids:
        acc = db_session.get(Account, acc_id)
        assert acc.persona is not None
        assert "windows_heavy" in acc.persona

    tasks = db_session.query(Task).filter_by(task_type="create_profile").all()
    assert len(tasks) == 2
