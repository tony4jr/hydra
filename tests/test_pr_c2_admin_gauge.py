"""PR-C2: admin phase gauge endpoint 테스트."""
from __future__ import annotations

from datetime import datetime, UTC, timedelta

import pytest


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    from hydra.db.models import Base

    db_path = tmp_path / "g.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(_ds, "engine", engine)
    monkeypatch.setattr(_ds, "SessionLocal", Session)
    s = Session()
    yield s
    s.close()


def test_phase_gauge_returns_running_tasks(db_session, monkeypatch):
    from hydra.db.models import Task, Worker, Account
    from hydra.web.routes import admin_phase_gauge as ag

    a = Account(gmail="a@b.c", password="E", status="active")
    w = Worker(name="pc-1", status="online", allow_campaign=True)
    db_session.add_all([a, w])
    db_session.flush()

    now = datetime.now(UTC).replace(tzinfo=None)
    running = Task(
        task_type="comment", status="running",
        worker_id=w.id, account_id=a.id,
        started_at=now - timedelta(minutes=5),
        last_progress_at=now - timedelta(seconds=15),
        last_phase="ip_rotate",
        session_uuid="s-1",
    )
    pending = Task(task_type="comment", status="pending")
    done = Task(task_type="comment", status="done", completed_at=now)
    db_session.add_all([running, pending, done])
    db_session.commit()

    # admin_session 의존성 우회
    result = ag.phase_gauge(_session={}, db=db_session)
    items = result["tasks"]
    assert len(items) == 1
    item = items[0]
    assert item["status"] == "running"
    assert item["last_phase"] == "ip_rotate"
    assert item["session_uuid"] == "s-1"
    assert item["phase_timeout_sec"] == 45  # ip_rotate default
    # last_progress_age 약 15s → phase_progress_pct ~33%
    assert 30 < (item["phase_progress_pct"] or 0) < 40


def test_phase_gauge_sessions(db_session):
    from hydra.db.models import Worker, WorkerSession as WS
    from hydra.web.routes import admin_phase_gauge as ag

    w = Worker(name="pc-1", status="online", allow_campaign=True)
    db_session.add(w); db_session.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    active = WS(
        session_uuid="s-active", worker_id=w.id, account_id=1,
        started_at=now - timedelta(minutes=5),
        last_heartbeat_at=now - timedelta(seconds=10),
        status="active",
    )
    stale = WS(
        session_uuid="s-stale", worker_id=w.id, account_id=2,
        started_at=now - timedelta(minutes=60),
        last_heartbeat_at=now - timedelta(minutes=45),  # > 30분 cutoff
        status="active",
    )
    ended = WS(
        session_uuid="s-ended", worker_id=w.id, account_id=3,
        started_at=now - timedelta(minutes=10),
        last_heartbeat_at=now - timedelta(seconds=20),
        ended_at=now - timedelta(seconds=10),
        status="ended",
    )
    db_session.add_all([active, stale, ended]); db_session.commit()

    result = ag.active_sessions(_session={}, db=db_session)
    sess = result["sessions"]
    uuids = {s["session_uuid"] for s in sess}
    assert "s-active" in uuids
    assert "s-stale" not in uuids
    assert "s-ended" not in uuids


def test_phase_gauge_recent_history(db_session):
    from hydra.db.models import WorkerProgress
    from hydra.web.routes import admin_phase_gauge as ag

    now = datetime.now(UTC).replace(tzinfo=None)
    db_session.add_all([
        WorkerProgress(session_uuid="s-x", task_id=1, sequence_no=1,
                       phase="ip_rotate", occurred_at=now - timedelta(seconds=20)),
        WorkerProgress(session_uuid="s-x", task_id=1, sequence_no=2,
                       phase="adspower_open", occurred_at=now - timedelta(seconds=15)),
        WorkerProgress(session_uuid="s-x", task_id=1, sequence_no=3,
                       phase="video_goto", occurred_at=now - timedelta(seconds=5)),
        WorkerProgress(session_uuid="s-y", task_id=2, sequence_no=1,
                       phase="compose", occurred_at=now - timedelta(seconds=1)),
    ])
    db_session.commit()

    # 전체 최근 — DESC
    all_events = ag.recent_phase_history(_session={}, db=db_session, limit=10, session_uuid=None)
    assert all_events["events"][0]["phase"] == "compose"  # 가장 최근

    # 특정 session — ASC sequence
    sx = ag.recent_phase_history(_session={}, db=db_session, limit=10, session_uuid="s-x")
    phases = [e["phase"] for e in sx["events"]]
    assert phases == ["ip_rotate", "adspower_open", "video_goto"]
