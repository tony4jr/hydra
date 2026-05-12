"""PR-C: phase reporter + worker_sessions + zombie COALESCE 테스트.

scope:
- TaskProgress / SessionHeartbeat Pydantic 검증
- WorkerProgress / WorkerSession 모델 CRUD
- zombie_cleanup COALESCE: last_progress_at 우선, fallback started_at
- WorkerSession progress reporter 통합 (phase emit → reporter 호출)
"""
from __future__ import annotations

from datetime import datetime, UTC, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from hydra.protocol import (
    AccountSnapshot, PHASE_NAMES, SessionHeartbeat,
    TaskEnvelope, TaskProgress, WorkerConfig,
)


# ───── Pydantic 모델 ─────


def test_task_progress_minimal():
    p = TaskProgress(
        session_uuid="abc-123",
        task_id=42,
        attempt_no=0,
        sequence_no=1,
        phase="ip_rotate",
    )
    assert p.session_uuid == "abc-123"
    assert p.is_phase_change is False  # default


def test_task_progress_phase_change():
    p = TaskProgress(
        session_uuid="abc-123",
        task_id=42,
        attempt_no=0,
        sequence_no=2,
        phase="cdp_connect",
        message="connecting",
        is_phase_change=True,
    )
    assert p.is_phase_change is True
    assert p.message == "connecting"


def test_phase_names_complete():
    expected = {"session_start", "ip_rotate", "adspower_open", "cdp_connect",
                "video_goto", "compose", "type", "submit", "wait", "session_end"}
    assert set(PHASE_NAMES) == expected


def test_session_heartbeat_construct():
    hb = SessionHeartbeat(session_uuid="s-1", worker_id=8, account_id=42)
    assert hb.worker_id == 8
    assert hb.status == "active"  # default


# ───── WorkerSession progress emitter ─────


@pytest.mark.asyncio
async def test_worker_session_emits_phases_on_start():
    """WorkerSession.start() 호출하면 progress_reporter 가 여러 번 호출됨 (phase 변경)."""
    from worker.session import WorkerSession

    calls = []

    def reporter(**kw):
        calls.append(kw["phase"])

    with patch("worker.session.ensure_safe_ip_via_server",
               new=AsyncMock(return_value=1)) as mock_ensure, \
         patch("worker.session.BrowserSession") as BS:
        instance = MagicMock()
        instance.start = AsyncMock()
        instance.goto = AsyncMock()
        instance.page = MagicMock()
        BS.return_value = instance

        snap = AccountSnapshot(id=42, gmail="a@b.c", encrypted_password="ENC",
                                adspower_profile_id="p1")
        sess = WorkerSession(
            profile_id="p1", account_id=42,
            account_snapshot=snap, worker_config=WorkerConfig(adb_device_id="DEV"),
            progress_reporter=reporter,
            server_client=MagicMock(),  # PR-D: server endpoint 호출 mock
        )
        ok = await sess.start()
        assert ok
        # session_start → ip_rotate → adspower_open → video_goto → wait
        assert calls[0] == "session_start"
        assert "ip_rotate" in calls
        assert "adspower_open" in calls
        assert "video_goto" in calls
        assert calls[-1] == "wait"


@pytest.mark.asyncio
async def test_worker_session_uuid_unique():
    from worker.session import WorkerSession
    sessions = [
        WorkerSession(profile_id="p", account_id=i, account_snapshot=AccountSnapshot(
            id=i, gmail=f"{i}@x.com", encrypted_password="E", adspower_profile_id="p",
        ))
        for i in range(5)
    ]
    uuids = {s.session_uuid for s in sessions}
    assert len(uuids) == 5  # 모두 다름


@pytest.mark.asyncio
async def test_emit_phase_increments_sequence():
    from worker.session import WorkerSession
    snap = AccountSnapshot(id=1, gmail="a@b.c", encrypted_password="E", adspower_profile_id="p")
    sess = WorkerSession(profile_id="p", account_id=1, account_snapshot=snap)
    sess._emit_phase("ip_rotate")
    sess._emit_phase("adspower_open")
    sess._emit_phase("wait", is_change=False)  # heartbeat, sequence 증가 안 함
    sess._emit_phase("compose")
    assert sess.sequence_no == 3
    assert sess.current_phase == "compose"


# ───── zombie_cleanup COALESCE ─────


@pytest.fixture
def db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    from hydra.db.models import Base

    db_path = tmp_path / "z.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(_ds, "engine", engine)
    monkeypatch.setattr(_ds, "SessionLocal", Session)
    s = Session()
    yield s
    s.close()


# ───── endpoint 소유권 검증 (PR-C v2 — Codex 검토) ─────


def test_progress_rejects_unclaimed_task(db, monkeypatch):
    """task_id 가 있지만 worker_id IS NULL 이면 409 (claim 안 됨)."""
    from fastapi.testclient import TestClient
    from hydra.web.app import app as fastapi_app
    from hydra.db.models import Task, Worker
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db.bind))

    w = Worker(name="pc-x", token_sha256="t" * 64, status="online", allow_campaign=True)
    db.add(w); db.flush()
    t = Task(task_type="comment", status="pending")  # worker_id IS NULL
    db.add(t); db.commit()

    # mock worker_auth
    from hydra.web.routes import tasks_api
    monkeypatch.setattr(
        tasks_api, "worker_auth", lambda: w
    )

    # 직접 호출 (FastAPI Dependency wiring 우회) — 의도된 가드만 검증.
    from fastapi import HTTPException
    from hydra.protocol import TaskProgress
    p = TaskProgress(
        session_uuid="s-1", task_id=t.id, attempt_no=0, sequence_no=1, phase="ip_rotate",
    )
    try:
        tasks_api.report_progress(p, worker=w)
        assert False, "should raise"
    except HTTPException as e:
        assert e.status_code == 409
        assert "task_not_claimed" in (e.detail or "")


def test_session_heartbeat_ignores_body_worker_id(db, monkeypatch):
    """body 의 worker_id 값 무시. 서버는 auth worker.id 만 사용 (PR-C v2)."""
    from hydra.web.routes import tasks_api
    from hydra.db.models import Worker, WorkerSession as WS
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db.bind))

    w = Worker(name="pc-x", token_sha256="t" * 64, status="online", allow_campaign=True)
    db.add(w); db.commit()

    from hydra.protocol import SessionHeartbeat
    hb = SessionHeartbeat(
        session_uuid="s-new",
        worker_id=-1,           # 워커가 잘못된 placeholder 보내도
        account_id=42,
        status="active",
    )
    result = tasks_api.session_heartbeat(hb, worker=w)
    assert result["ok"]
    # auth worker.id 로 저장됨 (-1 이 아니라 w.id)
    sess = db.query(WS).filter(WS.session_uuid == "s-new").first()
    assert sess is not None
    assert sess.worker_id == w.id


def test_zombie_cleanup_uses_last_progress_when_present(db, monkeypatch):
    """last_progress_at 이 있으면 그 기준으로 stale 감지 (started_at 무관)."""
    from hydra.db.models import Task
    from hydra.core.zombie_cleanup import find_and_reset_zombies
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", db.bind.dialect.__class__)  # no-op
    # SessionLocal 직접 패치
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db.bind))

    now = datetime.now(UTC).replace(tzinfo=None)
    # 1) started 한참 전(40분 전), progress 는 fresh(1분 전) → stale 아님
    fresh = Task(
        task_type="comment", status="running",
        started_at=now - timedelta(minutes=40),
        last_progress_at=now - timedelta(minutes=1),
    )
    # 2) started 1분 전, progress 40분 전 → stale (보고 멈춤)
    stale_by_progress = Task(
        task_type="comment", status="running",
        started_at=now - timedelta(minutes=1),
        last_progress_at=now - timedelta(minutes=40),
    )
    # 3) started 40분 전, progress NULL (구버전) → stale (fallback started_at)
    stale_legacy = Task(
        task_type="comment", status="running",
        started_at=now - timedelta(minutes=40),
        last_progress_at=None,
    )
    # 4) started 1분 전, progress NULL → fresh
    fresh_legacy = Task(
        task_type="comment", status="running",
        started_at=now - timedelta(minutes=1),
        last_progress_at=None,
    )
    db.add_all([fresh, stale_by_progress, stale_legacy, fresh_legacy])
    db.commit()
    ids = {fresh.id, stale_by_progress.id, stale_legacy.id, fresh_legacy.id}

    n = find_and_reset_zombies(stale_minutes=30)
    db.expire_all()
    assert n == 2  # stale_by_progress + stale_legacy

    fresh = db.get(Task, fresh.id)
    stale_by_progress = db.get(Task, stale_by_progress.id)
    stale_legacy = db.get(Task, stale_legacy.id)
    fresh_legacy = db.get(Task, fresh_legacy.id)
    assert fresh.status == "running"
    assert stale_by_progress.status == "pending"
    assert stale_legacy.status == "pending"
    assert fresh_legacy.status == "running"
