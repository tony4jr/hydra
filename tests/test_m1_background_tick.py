"""Task M1-8: background scheduler 가 orchestrator.sweep + campaign_stub.scan 호출."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import Account, Base, Task


@pytest.fixture
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)
    monkeypatch.setenv("M1_TEST_VIDEO_ID", "dQw4w9WgXcQ")
    yield TestSession
    engine.dispose()


def test_tick_sweeps_and_scans(env):
    from hydra.services.background import m1_tick

    s = env()
    stuck = Account(
        gmail="stuck@x.com", password="x", adspower_profile_id="p1",
        status="warmup", warmup_day=2,
    )
    active = Account(
        gmail="act@x.com", password="x", adspower_profile_id="p2",
        status="active", warmup_day=4,
    )
    s.add_all([stuck, active])
    s.commit()
    stuck_id = stuck.id
    active_id = active.id
    s.close()

    result = m1_tick()
    assert result["swept"] == 1
    assert result["scanned"] == 1

    s = env()
    assert s.query(Task).filter_by(
        account_id=stuck_id, task_type="warmup", status="pending",
    ).count() == 1
    assert s.query(Task).filter_by(
        account_id=active_id, task_type="comment",
    ).count() == 1
    assert s.query(Task).filter_by(
        account_id=active_id, task_type="like",
    ).count() == 1
    s.close()
