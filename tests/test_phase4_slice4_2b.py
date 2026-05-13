"""Phase 4 Slice 4.2b — output chunks + admin polling + worker reader.

Coverage:
  1. terminal_chunks schema + (session_id, stream, seq) UNIQUE
  2. POST /workers/terminal/{id}/chunks
     - 3중 검증
     - stream 화이트리스트 (stdout/stderr)
     - chunk byte_size 64KB 상한
     - session total 10MB 초과 시 force close + 400
     - seq stream 별 monotonic
  3. GET /admin/terminal/{id}/chunks?after_id=N
     - id 순서 (global)
     - total_bytes / session_status 메타
  4. _stream_reader_loop (worker side):
     - 64KB 모이면 flush
     - 100ms 지나면 flush (작은 chunk)
     - EOF 시 buf flush 후 종료
     - stop_event set → 종료
"""
from __future__ import annotations

import hashlib
import io
import threading
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, TerminalChunk, TerminalSession, Worker


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


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
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")
    monkeypatch.setenv("ENROLLMENT_SECRET", "x" * 32)
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")

    db = TS()
    dtoken = "d-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    d = Worker(
        name="desk-1", token_hash=hash_password(dtoken),
        token_sha256=_sha(dtoken), token_prefix=dtoken[:8],
        role="desktop_worker",
    )
    db.add(d); db.commit(); db.refresh(d)
    atoken = "a-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    a = Worker(
        name="agent-1", token_hash=hash_password(atoken),
        token_sha256=_sha(atoken), token_prefix=atoken[:8],
        role="admin_agent", parent_worker_id=d.id,
    )
    db.add(a); db.commit(); db.refresh(a)
    aid = a.id
    db.close()

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {
        "client": client, "Session": TS, "engine": engine,
        "agent_id": aid, "agent_token": atoken, "desktop_token": dtoken,
        "admin_jwt": admin_jwt,
    }
    engine.dispose()


def _admin(env):
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


def _open_active(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/terminal/open",
        headers=_admin(env), json={"shell": "powershell"},
    )
    s = r.json()
    h = {
        "X-Worker-Token": env["agent_token"],
        "X-Terminal-Session-Token": s["session_token"],
    }
    env["client"].post(f"/api/workers/terminal/{s['session_id']}/active", headers=h)
    return s["session_id"], s["session_token"], h


# ───────── 1. schema ─────────

def test_terminal_chunks_unique(env):
    db = env["Session"]()
    ts = TerminalSession(
        worker_id=env["agent_id"],
        opened_at=datetime.now(UTC), last_activity_at=datetime.now(UTC),
        status="active", shell="powershell", session_token="tok-c",
    )
    db.add(ts); db.commit(); db.refresh(ts)
    db.add(TerminalChunk(
        session_id=ts.id, stream="stdout", seq=1, data="a", byte_size=1,
        produced_at=datetime.now(UTC),
    ))
    db.commit()
    db.add(TerminalChunk(
        session_id=ts.id, stream="stdout", seq=1, data="b", byte_size=1,
        produced_at=datetime.now(UTC),
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # 다른 stream 은 같은 seq 허용
    db.add(TerminalChunk(
        session_id=ts.id, stream="stderr", seq=1, data="c", byte_size=1,
        produced_at=datetime.now(UTC),
    ))
    db.commit()
    db.close()


# ───────── 2. worker POST /chunks ─────────

def test_worker_post_chunks_assigns_seq_monotonic(env):
    sid, _, h = _open_active(env)
    r = env["client"].post(
        f"/api/workers/terminal/{sid}/chunks", headers=h,
        json={"chunks": [
            {"stream": "stdout", "data": "a", "byte_size": 1},
            {"stream": "stdout", "data": "b", "byte_size": 1},
            {"stream": "stderr", "data": "X", "byte_size": 1},
        ]},
    )
    assert r.status_code == 200
    assert r.json()["accepted"] == 3
    db = env["Session"]()
    rows = db.query(TerminalChunk).filter_by(session_id=sid).order_by(TerminalChunk.id).all()
    streams = [(r.stream, r.seq) for r in rows]
    assert streams == [("stdout", 1), ("stdout", 2), ("stderr", 1)]
    db.close()


def test_worker_post_chunks_rejects_invalid_stream(env):
    sid, _, h = _open_active(env)
    r = env["client"].post(
        f"/api/workers/terminal/{sid}/chunks", headers=h,
        json={"chunks": [{"stream": "stdin", "data": "x", "byte_size": 1}]},
    )
    assert r.status_code == 400


def test_worker_post_chunks_rejects_oversize_chunk(env):
    """Codex 4.2b blocker 3 fix: server 가 byte_size worker 주장 무시 +
    실제 data 길이로 검증. 65KB data 면 byte_size 1 로 주장해도 400.
    """
    sid, _, h = _open_active(env)
    big_data = "x" * (65 * 1024)  # 64KB 초과 실제 데이터
    r = env["client"].post(
        f"/api/workers/terminal/{sid}/chunks", headers=h,
        json={"chunks": [{"stream": "stdout", "data": big_data, "byte_size": 1}]},
    )
    assert r.status_code == 400
    assert "exceeds" in r.text.lower()


def test_worker_post_chunks_session_total_limit_force_closes(env):
    """session total 10MB 초과 시 status=closing + 400."""
    sid, _, h = _open_active(env)
    # 미리 큰 양 insert
    db = env["Session"]()
    db.add(TerminalChunk(
        session_id=sid, stream="stdout", seq=1, data="x",
        byte_size=10 * 1024 * 1024 - 100,  # 거의 10MB
        produced_at=datetime.now(UTC),
    ))
    db.commit(); db.close()
    # incoming 300 bytes 실제 data → 한도 초과 (server 가 byte_size 재계산)
    r = env["client"].post(
        f"/api/workers/terminal/{sid}/chunks", headers=h,
        json={"chunks": [{"stream": "stdout", "data": "y" * 300, "byte_size": 300}]},
    )
    assert r.status_code == 400
    assert "output_size_exceeded" in r.text
    # session status=closing
    db = env["Session"]()
    ts = db.get(TerminalSession, sid)
    assert ts.status == "closing"
    db.close()


def test_worker_post_chunks_token_check(env):
    sid, _, _ = _open_active(env)
    h_bad = {
        "X-Worker-Token": env["agent_token"],
        "X-Terminal-Session-Token": "bogus",
    }
    r = env["client"].post(
        f"/api/workers/terminal/{sid}/chunks", headers=h_bad,
        json={"chunks": [{"stream": "stdout", "data": "a", "byte_size": 1}]},
    )
    assert r.status_code == 403


# ───────── 3. admin GET /chunks ─────────

def test_admin_get_chunks_after_id(env):
    sid, _, h = _open_active(env)
    env["client"].post(
        f"/api/workers/terminal/{sid}/chunks", headers=h,
        json={"chunks": [
            {"stream": "stdout", "data": "a", "byte_size": 1},
            {"stream": "stdout", "data": "b", "byte_size": 1},
        ]},
    )
    r = env["client"].get(
        f"/api/admin/terminal/{sid}/chunks?after_id=0",
        headers=_admin(env),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["chunks"]) == 2
    assert body["total_bytes"] == 2
    assert body["session_status"] == "active"
    first_id = body["chunks"][0]["id"]
    # after_id 필터
    r2 = env["client"].get(
        f"/api/admin/terminal/{sid}/chunks?after_id={first_id}",
        headers=_admin(env),
    )
    assert len(r2.json()["chunks"]) == 1


def test_admin_get_chunks_404(env):
    r = env["client"].get(
        "/api/admin/terminal/999999/chunks?after_id=0",
        headers=_admin(env),
    )
    assert r.status_code == 404


# ───────── 4. _stream_reader_loop ─────────

class _FakeStream:
    """1 byte 단위 read 지원. 끝나면 b'' 반환 (EOF)."""
    def __init__(self, data: bytes):
        self._buf = bytearray(data)
    def read(self, n: int):
        if not self._buf:
            return b""
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


def test_stream_reader_flushes_small_output_on_eof(monkeypatch):
    """작은 출력도 EOF (또는 timer) 시 flush. persistent shell race fix."""
    from worker import agent_terminal as _term
    client = MagicMock(); client.headers = {}
    resp = MagicMock(); resp.status_code = 200
    client._request.return_value = resp

    stream = _FakeStream(b"hi\n")
    stop_event = threading.Event()
    monkeypatch.setattr(_term, "CHUNK_FLUSH_INTERVAL_SEC", 60.0)  # timer 안 발동
    _term._stream_reader_loop(client, 1, "tok", "stdout", stream, stop_event)
    calls = [c for c in client._request.call_args_list if "/chunks" in c.args[1]]
    assert len(calls) >= 1
    body = calls[-1].kwargs["json"]
    assert body["chunks"][0]["data"] == "hi\n"


def test_stream_reader_size_flush(monkeypatch):
    """64KB 모이면 즉시 flush (timer 무관)."""
    from worker import agent_terminal as _term
    client = MagicMock(); client.headers = {}
    resp = MagicMock(); resp.status_code = 200
    client._request.return_value = resp

    stream = _FakeStream(b"a" * _term.CHUNK_FLUSH_BYTES)
    stop_event = threading.Event()
    monkeypatch.setattr(_term, "CHUNK_FLUSH_INTERVAL_SEC", 60.0)
    _term._stream_reader_loop(client, 1, "tok", "stdout", stream, stop_event)
    calls = [c for c in client._request.call_args_list if "/chunks" in c.args[1]]
    assert len(calls) >= 1


def test_stream_reader_force_kill_on_size_400(monkeypatch):
    """server 400 (size exceeded) → proc.terminate 호출."""
    from worker import agent_terminal as _term
    client = MagicMock(); client.headers = {}
    resp = MagicMock(); resp.status_code = 400
    client._request.return_value = resp

    proc = MagicMock()
    proc.wait.return_value = 0

    stream = _FakeStream(b"x" * _term.CHUNK_FLUSH_BYTES)
    stop_event = threading.Event()
    monkeypatch.setattr(_term, "CHUNK_FLUSH_INTERVAL_SEC", 60.0)
    _term._stream_reader_loop(client, 1, "tok", "stdout", stream, stop_event, proc)
    # 400 응답 → terminate 호출
    proc.terminate.assert_called()


def test_stream_reader_utf8_incremental_decoder(monkeypatch):
    """chunk 경계에서 멀티바이트 (한글) 잘려도 안전 decode.
    한글 '가' = 3 bytes (EA B0 80). 첫 byte 만 들어와도 decoder 가 hold.
    """
    from worker import agent_terminal as _term
    client = MagicMock(); client.headers = {}
    resp = MagicMock(); resp.status_code = 200
    client._request.return_value = resp

    # '가\n' = E1 B0 80 0A (실제 EA B0 80 0A)
    data = "가\n".encode("utf-8")
    stream = _FakeStream(data)
    stop_event = threading.Event()
    monkeypatch.setattr(_term, "CHUNK_FLUSH_INTERVAL_SEC", 60.0)
    _term._stream_reader_loop(client, 1, "tok", "stdout", stream, stop_event)
    calls = [c for c in client._request.call_args_list if "/chunks" in c.args[1]]
    # 모든 chunks 의 data 합친 게 "가\n" 와 일치 (잘려도 incremental decode 가 hold + final 처리)
    combined = "".join(c.kwargs["json"]["chunks"][0]["data"] for c in calls)
    assert combined == "가\n"


def test_stream_reader_exits_on_stop_event(monkeypatch):
    from worker import agent_terminal as _term
    client = MagicMock(); client.headers = {}
    stop_event = threading.Event()
    stop_event.set()
    stream = _FakeStream(b"x" * 100)
    _term._stream_reader_loop(client, 1, "tok", "stdout", stream, stop_event)
    # stop 직후 read 안 함 (while 첫 iter 에서 종료). final drain 만 호출되며 buf 비어있어 POST 도 없음
    calls = [c for c in client._request.call_args_list if "/chunks" in c.args[1]]
    assert len(calls) == 0


def test_stream_reader_constants():
    from worker.agent_terminal import CHUNK_FLUSH_BYTES, CHUNK_FLUSH_INTERVAL_SEC
    assert CHUNK_FLUSH_BYTES == 64 * 1024
    assert CHUNK_FLUSH_INTERVAL_SEC == 0.1
