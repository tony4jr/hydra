"""parent comment_id → child payload enrichment."""
from datetime import UTC, datetime, timedelta
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hydra.core.orchestrator import on_task_complete
from hydra.db.models import Account, Base, Task


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = S()
    yield s
    s.close()
    engine.dispose()


def _account(session):
    acc = Account(
        gmail="a@x.com",
        password="x",
        adspower_profile_id="p1",
        status="active",
    )
    session.add(acc)
    session.flush()
    return acc


def test_comment_done_enriches_child_target_payload(session):
    acc = _account(session)
    parent = Task(
        campaign_id=10,
        account_id=acc.id,
        task_type="comment",
        status="done",
        result=json.dumps({"comment_id": "Ug_PARENT"}),
    )
    session.add(parent)
    session.flush()
    child = Task(
        campaign_id=10,
        account_id=acc.id,
        task_type="reply",
        status="pending",
        parent_task_id=parent.id,
        payload=json.dumps({"video_id": "v1", "text": "reply"}),
    )
    session.add(child)
    session.flush()

    before = datetime.now(UTC)
    on_task_complete(parent.id, session)
    after = datetime.now(UTC)

    payload = json.loads(child.payload)
    assert payload["target_comment_id"] == "Ug_PARENT"
    assert payload["target_selector"] == "Ug_PARENT"
    assert child.scheduled_at >= before + timedelta(minutes=5)
    assert child.scheduled_at <= after + timedelta(minutes=30)


def test_reply_done_uses_reply_id_for_like_boost_child(session):
    acc = _account(session)
    parent = Task(
        campaign_id=20,
        account_id=acc.id,
        task_type="reply",
        status="done",
        result=json.dumps({"reply_id": "Ug_REPLY"}),
    )
    session.add(parent)
    session.flush()
    child = Task(
        campaign_id=20,
        task_type="like_boost",
        status="pending",
        parent_task_id=parent.id,
        payload=json.dumps({"video_id": "v1"}),
    )
    session.add(child)
    session.flush()

    on_task_complete(parent.id, session)

    payload = json.loads(child.payload)
    assert payload["target_comment_id"] == "Ug_REPLY"
    assert payload["target_selector"] == "Ug_REPLY"


def test_parent_done_without_comment_id_fails_children(session):
    acc = _account(session)
    parent = Task(
        campaign_id=30,
        account_id=acc.id,
        task_type="comment",
        status="done",
        result=json.dumps({"action": "comment", "ok": True}),
    )
    session.add(parent)
    session.flush()
    child = Task(
        campaign_id=30,
        account_id=acc.id,
        task_type="reply",
        status="pending",
        parent_task_id=parent.id,
        payload=json.dumps({"video_id": "v1"}),
    )
    session.add(child)
    session.flush()

    on_task_complete(parent.id, session)

    assert child.status == "failed"
    assert child.error_message == "parent_comment_id_missing"
    assert child.completed_at is not None


def test_enrichment_recalculates_scheduled_at(session):
    acc = _account(session)
    old_schedule = datetime.now(UTC) + timedelta(days=1)
    parent = Task(
        campaign_id=40,
        account_id=acc.id,
        task_type="comment",
        status="done",
        result=json.dumps({"youtube_comment_id": "Ug_YT"}),
    )
    session.add(parent)
    session.flush()
    child = Task(
        campaign_id=40,
        task_type="like_boost",
        status="pending",
        parent_task_id=parent.id,
        payload=json.dumps({"video_id": "v1"}),
        scheduled_at=old_schedule,
    )
    session.add(child)
    session.flush()

    on_task_complete(parent.id, session)

    assert child.scheduled_at != old_schedule
    assert child.scheduled_at < old_schedule
