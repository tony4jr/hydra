"""운영 긴급 가드: unenriched child dispatch + account churn 차단."""
from datetime import UTC, datetime, timedelta
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hydra.db.models import Account, Base, Task, Worker


@pytest.fixture
def task_api_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    from hydra.db import session as session_mod
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)

    db = TestSession()
    worker = Worker(
        name="pc-01",
        status="online",
        role="desktop_worker",
        allow_preparation=True,
        allow_campaign=True,
        allowed_task_types='["*"]',
    )
    account = Account(
        gmail="a@x.com",
        password="x",
        adspower_profile_id="profile-a",
        status="active",
    )
    db.add_all([worker, account])
    db.commit()

    yield TestSession, worker.id, account.id

    db.close()
    engine.dispose()


def _worker(TestSession, worker_id):
    db = TestSession()
    try:
        return db.get(Worker, worker_id)
    finally:
        db.close()


def test_fetch_excludes_unenriched_reply_child(task_api_env):
    from hydra.web.routes.tasks_api import fetch_tasks

    TestSession, worker_id, account_id = task_api_env
    db = TestSession()
    parent = Task(
        account_id=account_id,
        task_type="comment",
        status="running",
        result=None,
    )
    db.add(parent)
    db.flush()
    child = Task(
        account_id=account_id,
        task_type="reply",
        status="pending",
        parent_task_id=parent.id,
        payload=json.dumps({"video_id": "v1", "text": "reply"}),
    )
    db.add(child)
    db.commit()
    child_id = child.id
    db.close()

    assert fetch_tasks(worker=_worker(TestSession, worker_id)) == {"tasks": []}

    db = TestSession()
    child = db.get(Task, child_id)
    assert child.status == "pending"
    assert child.error_message is None
    db.close()


def test_fetch_marks_child_failed_when_parent_done_without_comment_id(task_api_env):
    from hydra.web.routes.tasks_api import fetch_tasks

    TestSession, worker_id, account_id = task_api_env
    db = TestSession()
    parent = Task(
        account_id=account_id,
        task_type="comment",
        status="done",
        result=json.dumps({"action": "comment", "ok": True}),
    )
    db.add(parent)
    db.flush()
    child = Task(
        account_id=account_id,
        task_type="like_boost",
        status="pending",
        parent_task_id=parent.id,
        payload=json.dumps({"video_id": "v1"}),
    )
    db.add(child)
    db.commit()
    child_id = child.id
    db.close()

    assert fetch_tasks(worker=_worker(TestSession, worker_id)) == {"tasks": []}

    db = TestSession()
    child = db.get(Task, child_id)
    assert child.status == "failed"
    assert child.error_message == "parent_comment_id_missing"
    assert child.completed_at is not None
    db.close()


@pytest.mark.asyncio
async def test_worker_reply_empty_target_fails_before_browser():
    from worker.executor import TaskExecutor

    executor = TaskExecutor()
    with pytest.raises(RuntimeError) as ei:
        await executor._handle_reply(
            {"id": 1, "task_type": "reply"},
            {"video_id": "v1", "text": "reply"},
            session=None,
        )

    assert json.loads(str(ei.value)) == {"action": "reply", "error": "no_target"}


@pytest.mark.asyncio
async def test_worker_like_boost_empty_target_fails_before_browser():
    from worker.executor import TaskExecutor

    executor = TaskExecutor()
    with pytest.raises(RuntimeError) as ei:
        await executor._handle_like_boost(
            {"id": 1, "task_type": "like_boost"},
            {"video_id": "v1"},
            session=None,
        )

    assert json.loads(str(ei.value)) == {"action": "like_boost", "error": "no_target"}


def test_auto_assign_account_skips_recently_active_account(task_api_env, monkeypatch):
    from hydra.core.config import settings
    from hydra.web.routes.tasks_api import _auto_assign_account

    monkeypatch.setattr(settings, "account_recent_cooldown_min", 15, raising=False)
    TestSession, _worker_id, account_id = task_api_env
    db = TestSession()
    recent = db.get(Account, account_id)
    older = Account(
        gmail="b@x.com",
        password="x",
        adspower_profile_id="profile-b",
        status="active",
    )
    db.add(older)
    db.flush()
    db.add(Task(
        account_id=recent.id,
        task_type="comment",
        status="done",
        completed_at=datetime.now(UTC) - timedelta(minutes=3),
    ))
    task = Task(task_type="comment", status="pending", payload="{}")
    db.add(task)
    db.commit()

    assert _auto_assign_account(db, task) is True
    assert task.account_id == older.id
    db.close()
