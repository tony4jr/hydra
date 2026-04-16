from hydra.db.models import Worker, Task, Preset, ProfileLock, Account


def test_create_worker(db_session):
    worker = Worker(name="PC-1", token_hash="abc123", status="online")
    db_session.add(worker)
    db_session.commit()
    assert worker.id is not None
    assert worker.name == "PC-1"


def test_create_task(db_session):
    worker = Worker(name="PC-1", token_hash="abc123")
    db_session.add(worker)
    db_session.commit()
    task = Task(
        worker_id=worker.id,
        task_type="comment",
        priority="normal",
        status="pending",
        payload='{"text": "test comment"}',
    )
    db_session.add(task)
    db_session.commit()
    assert task.id is not None
    assert task.worker.name == "PC-1"


def test_create_preset(db_session):
    preset = Preset(
        name="시나리오 A",
        code="A",
        is_system=True,
        steps='[{"step_number": 1, "role": "seed", "type": "comment"}]',
    )
    db_session.add(preset)
    db_session.commit()
    assert preset.id is not None
    assert preset.is_system is True


def test_profile_lock(db_session):
    account = Account(gmail="test@gmail.com", password="pass")
    worker = Worker(name="PC-1", token_hash="abc123")
    db_session.add_all([account, worker])
    db_session.commit()
    lock = ProfileLock(
        account_id=account.id,
        worker_id=worker.id,
        adspower_profile_id="profile_001",
    )
    db_session.add(lock)
    db_session.commit()
    assert lock.released_at is None
