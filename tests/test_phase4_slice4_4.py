"""Phase 4 Slice 4.4 — inactivity timeout + retention + max lifetime + close tree kill.

Coverage:
  1. inactivity_timeout_batch: status=active + last_activity > 15분 → timeout + close command
  2. max_lifetime_batch: opened_at > 4시간 → timeout (active/closing/pending 모두)
  3. retention_cleanup_batch: 7일 지난 closed/timeout/failed 세션의 chunks/inputs 삭제
  4. close_session 의 tree kill fallback (graceful timeout 후 _kill_process_tree)
  5. shutdown_all 의 tree kill fallback
  6. scheduler intervals 에 3개 batch task 등록
  7. worker/requirements.txt 에 psutil 추가
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import (
    Base, TerminalChunk, TerminalInput, TerminalSession, Worker, WorkerCommand,
)


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture(autouse=True)
def _clear_registry():
    from worker import agent_terminal as _term
    _term.clear_registry_for_testing()
    yield
    _term.clear_registry_for_testing()


@pytest.fixture
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TS)

    db = TS()
    workers = []
    for i in range(3):
        tok = f"t-{i}-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        w = Worker(
            name=f"agent-{i}", token_hash=hash_password(tok),
            token_sha256=_sha(tok), token_prefix=tok[:8],
            role="admin_agent",
        )
        db.add(w); db.commit(); db.refresh(w)
        workers.append(w.id)
    db.close()
    yield {"Session": TS, "worker_ids": workers}
    engine.dispose()


# ───────── 1. inactivity_timeout_batch ─────────

def test_inactivity_timeout_marks_idle_active(env):
    from hydra.web.routes.terminal import inactivity_timeout_batch
    db = env["Session"]()
    # idle 20분 (>15분) → timeout
    ts_old = TerminalSession(
        worker_id=env["worker_ids"][0],
        opened_at=datetime.now(UTC) - timedelta(hours=1),
        last_activity_at=datetime.now(UTC) - timedelta(minutes=20),
        status="active", shell="powershell", session_token="tok-old",
    )
    # idle 5분 (<15분) → 유지
    ts_fresh = TerminalSession(
        worker_id=env["worker_ids"][1],
        opened_at=datetime.now(UTC) - timedelta(minutes=10),
        last_activity_at=datetime.now(UTC) - timedelta(minutes=5),
        status="active", shell="powershell", session_token="tok-fresh",
    )
    db.add_all([ts_old, ts_fresh]); db.commit()
    n = inactivity_timeout_batch(db)
    db.commit()
    assert n == 1
    db.refresh(ts_old); db.refresh(ts_fresh)
    assert ts_old.status == "timeout"
    assert ts_fresh.status == "active"
    # close command 발행됨
    cmd = db.query(WorkerCommand).filter_by(command="terminal_close").first()
    assert cmd is not None
    assert cmd.target_role == "admin_agent"
    db.close()


# ───────── 2. max_lifetime_batch ─────────

def test_max_lifetime_caps_long_sessions(env):
    from hydra.web.routes.terminal import max_lifetime_batch
    db = env["Session"]()
    # opened 5시간 전 (4시간 초과) → timeout
    ts_old = TerminalSession(
        worker_id=env["worker_ids"][0],
        opened_at=datetime.now(UTC) - timedelta(hours=5),
        last_activity_at=datetime.now(UTC),  # 활성이지만 너무 오래됨
        status="active", shell="powershell", session_token="tok-long",
    )
    # opened 1시간 전 → 유지
    ts_fresh = TerminalSession(
        worker_id=env["worker_ids"][1],
        opened_at=datetime.now(UTC) - timedelta(hours=1),
        last_activity_at=datetime.now(UTC),
        status="active", shell="powershell", session_token="tok-short",
    )
    db.add_all([ts_old, ts_fresh]); db.commit()
    n = max_lifetime_batch(db)
    db.commit()
    assert n == 1
    db.refresh(ts_old); db.refresh(ts_fresh)
    assert ts_old.status == "timeout"
    assert ts_fresh.status == "active"
    db.close()


# ───────── 3. retention_cleanup_batch ─────────

def test_retention_cleanup_drops_old_chunks_and_inputs(env):
    from hydra.web.routes.terminal import retention_cleanup_batch
    db = env["Session"]()
    # 8일 전 closed
    ts_old = TerminalSession(
        worker_id=env["worker_ids"][0],
        opened_at=datetime.now(UTC) - timedelta(days=8),
        last_activity_at=datetime.now(UTC) - timedelta(days=8),
        closed_at=datetime.now(UTC) - timedelta(days=8),
        status="closed", shell="powershell", session_token="tok-8d",
    )
    # 1일 전 closed
    ts_recent = TerminalSession(
        worker_id=env["worker_ids"][1],
        opened_at=datetime.now(UTC) - timedelta(days=1),
        last_activity_at=datetime.now(UTC) - timedelta(days=1),
        closed_at=datetime.now(UTC) - timedelta(days=1),
        status="closed", shell="powershell", session_token="tok-1d",
    )
    db.add_all([ts_old, ts_recent]); db.commit()
    db.refresh(ts_old); db.refresh(ts_recent)
    # chunks
    for sid in (ts_old.id, ts_recent.id):
        db.add(TerminalChunk(
            session_id=sid, stream="stdout", seq=1, data="x", byte_size=1,
            produced_at=datetime.now(UTC),
        ))
        db.add(TerminalInput(
            session_id=sid, seq=1, data="cmd", byte_size=3,
            produced_at=datetime.now(UTC),
        ))
    db.commit()

    r = retention_cleanup_batch(db)
    db.commit()
    assert r["sessions"] == 1
    assert r["chunks"] == 1
    assert r["inputs"] == 1
    # ts_old 의 chunk/input 삭제, ts_recent 는 유지
    assert db.query(TerminalChunk).filter_by(session_id=ts_old.id).count() == 0
    assert db.query(TerminalChunk).filter_by(session_id=ts_recent.id).count() == 1
    db.close()


# ───────── 4. close_session tree kill fallback ─────────

def test_close_session_falls_back_to_tree_kill_on_timeout(monkeypatch):
    """graceful terminate 가 timeout 되면 _kill_process_tree 호출."""
    import subprocess as _sp
    from worker import agent_terminal as _term
    proc = MagicMock(); proc.pid = 5555
    proc.poll.return_value = None
    proc.terminate = MagicMock()
    # 첫 wait → TimeoutExpired → kill tree fallback
    proc.wait.side_effect = _sp.TimeoutExpired(cmd="x", timeout=5)
    _term._REGISTRY[42] = {
        "proc": proc, "session_token": "t-42", "shell": "powershell",
        "input_stop": MagicMock(),
    }
    client = MagicMock(); client.headers = {}
    resp = MagicMock(); resp.status_code = 200
    client._request.return_value = resp

    with patch.object(_term, "_kill_process_tree") as mkill:
        _term.close_session(client, 42, "t-42")
    mkill.assert_called_once_with(proc)


# ───────── 5. shutdown_all tree kill fallback ─────────

def test_shutdown_all_falls_back_to_tree_kill(monkeypatch):
    import subprocess as _sp
    from worker import agent_terminal as _term
    proc = MagicMock(); proc.pid = 6666
    proc.poll.return_value = None
    proc.wait.side_effect = _sp.TimeoutExpired(cmd="x", timeout=3)
    _term._REGISTRY[1] = {
        "proc": proc, "session_token": "t-1", "shell": "powershell",
        "input_stop": MagicMock(),
    }
    with patch.object(_term, "_kill_process_tree") as mkill:
        n = _term.shutdown_all()
    assert n == 1
    mkill.assert_called_once_with(proc)


# ───────── 6. scheduler intervals ─────────

def test_scheduler_has_terminal_batch_intervals():
    from hydra.services.background import BackgroundScheduler
    s = BackgroundScheduler()
    for key in (
        "terminal_inactivity_batch",
        "terminal_max_lifetime_batch",
        "terminal_retention_cleanup",
    ):
        assert key in s.intervals
    # 합리적 간격
    assert s.intervals["terminal_inactivity_batch"] == 60
    assert s.intervals["terminal_max_lifetime_batch"] == 300
    assert s.intervals["terminal_retention_cleanup"] == 3600


# ───────── 7. worker/requirements.txt psutil ─────────

def test_worker_requirements_includes_psutil():
    repo = Path(__file__).resolve().parents[1]
    req = (repo / "worker" / "requirements.txt").read_text(encoding="utf-8")
    assert "psutil" in req
