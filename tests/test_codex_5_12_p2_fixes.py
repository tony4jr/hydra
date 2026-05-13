"""Codex 5/12 review 의 P2 세 가지:

  1. preflight AdsPower health check 에 Authorization 헤더 추가
  2. /ip-log/end 가 IpLog.worker_id 로 소유권 검증
  3. worker client retry backoff 단축 (1/2/4/8 → 0.5/1/2/4)
"""
from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Account, Base, IpLog, Task, Worker


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ───────── P2.1 — preflight Authorization header ─────────

def test_preflight_adspower_ping_adds_bearer_when_key_present(monkeypatch):
    monkeypatch.setenv("ADSPOWER_API_KEY", "  test-key-123\r\n")

    captured_headers = {}

    class FakeResponse:
        def read(self):
            import json as _json
            return _json.dumps({"code": 0}).encode()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None

    def fake_urlopen(req, timeout=None):
        # capture all headers
        for h in req.header_items():
            captured_headers[h[0]] = h[1]
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    from worker.preflight import adspower_ping
    result = adspower_ping(timeout_sec=2)
    assert result["ok"] is True
    # urllib 의 header capitalize 차이 — case-insensitive 비교
    auth = captured_headers.get("Authorization") or captured_headers.get("authorization")
    assert auth is not None
    # 정규화 적용 — trailing \r\n 제거 + bare key
    assert auth == "Bearer test-key-123"


def test_preflight_adspower_ping_no_auth_when_key_empty(monkeypatch):
    monkeypatch.delenv("ADSPOWER_API_KEY", raising=False)

    captured_headers = {}
    class FakeResponse:
        def read(self):
            import json as _json
            return _json.dumps({"code": 0}).encode()
        def __enter__(self): return self
        def __exit__(self, *args): return None

    def fake_urlopen(req, timeout=None):
        for h in req.header_items():
            captured_headers[h[0]] = h[1]
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    from worker.preflight import adspower_ping
    adspower_ping(timeout_sec=2)
    # ADSPOWER_API_KEY 없으면 Authorization 헤더 안 들어감
    assert "Authorization" not in captured_headers
    assert "authorization" not in captured_headers


# ───────── P2.2 — /ip-log/end ownership verification ─────────

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
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")

    db = TestSession()
    tok_a = "worker-token-A-xxxxxxxxxxxxxxxxxxxxxx"
    tok_b = "worker-token-B-xxxxxxxxxxxxxxxxxxxxxx"
    w_a = Worker(
        name="worker-a",
        token_hash=hash_password(tok_a),
        token_prefix=tok_a[:8],
        token_sha256=_sha(tok_a),
    )
    w_b = Worker(
        name="worker-b",
        token_hash=hash_password(tok_b),
        token_prefix=tok_b[:8],
        token_sha256=_sha(tok_b),
    )
    db.add_all([w_a, w_b]); db.commit(); db.refresh(w_a); db.refresh(w_b)
    acc = Account(gmail="test@example.com", password="ENC", status="active")
    db.add(acc); db.commit(); db.refresh(acc)
    a_id, b_id, acc_id = w_a.id, w_b.id, acc.id
    # ip-log/start 의 task ownership guard 통과용 running task.
    t = Task(
        account_id=acc_id, task_type="like", status="running", worker_id=a_id,
    )
    db.add(t); db.commit()
    db.close()

    from hydra.web.app import app
    client = TestClient(app)
    yield {
        "client": client, "Session": TestSession,
        "tok_a": tok_a, "tok_b": tok_b,
        "worker_a_id": a_id, "worker_b_id": b_id,
        "account_id": acc_id,
    }
    engine.dispose()


def _hdr(token: str) -> dict:
    return {"X-Worker-Token": token}


def test_iplog_start_records_worker_id(env):
    r = env["client"].post(
        "/api/workers/ip-log/start",
        headers=_hdr(env["tok_a"]),
        json={"account_id": env["account_id"], "ip_address": "1.2.3.4", "device_id": "dev1"},
    )
    assert r.status_code == 200
    log_id = r.json()["log_id"]
    db = env["Session"]()
    try:
        rec = db.get(IpLog, log_id)
        assert rec.worker_id == env["worker_a_id"]
    finally:
        db.close()


def test_iplog_end_rejects_different_worker(env):
    """worker A 가 만든 IpLog 를 worker B 가 닫으려 하면 403."""
    r = env["client"].post(
        "/api/workers/ip-log/start",
        headers=_hdr(env["tok_a"]),
        json={"account_id": env["account_id"], "ip_address": "1.2.3.4", "device_id": "dev1"},
    )
    log_id = r.json()["log_id"]
    end_r = env["client"].post(
        "/api/workers/ip-log/end",
        headers=_hdr(env["tok_b"]),  # 다른 worker
        json={"log_id": log_id},
    )
    assert end_r.status_code == 403
    assert "not owned" in end_r.text.lower()


def test_iplog_end_accepts_same_worker(env):
    r = env["client"].post(
        "/api/workers/ip-log/start",
        headers=_hdr(env["tok_a"]),
        json={"account_id": env["account_id"], "ip_address": "1.2.3.4", "device_id": "dev1"},
    )
    log_id = r.json()["log_id"]
    end_r = env["client"].post(
        "/api/workers/ip-log/end",
        headers=_hdr(env["tok_a"]),
        json={"log_id": log_id},
    )
    assert end_r.status_code == 200


def test_delete_worker_clears_iplog_worker_id(env):
    """worker 삭제 시 IpLog.worker_id 가 NULL 처리되어 FK 위반 안 남.

    Codex 5/12 P2 follow-up — delete_worker 의 IpLog 처리 + FK ondelete
    SET NULL 안전망.
    """
    # 1. worker A 가 IpLog 만든 후
    r = env["client"].post(
        "/api/workers/ip-log/start",
        headers=_hdr(env["tok_a"]),
        json={"account_id": env["account_id"], "ip_address": "5.5.5.5", "device_id": "d1"},
    )
    assert r.status_code == 200
    log_id = r.json()["log_id"]

    # 2. admin 으로 worker A 삭제 — running task 가 없도록 미리 task 정리
    db = env["Session"]()
    try:
        from hydra.db.models import Task
        db.query(Task).filter(Task.worker_id == env["worker_a_id"]).update(
            {Task.status: "completed"}, synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()

    # admin JWT 만들기
    import jwt as _jwt
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    r = env["client"].delete(
        f"/api/admin/workers/{env['worker_a_id']}",
        headers={"Authorization": f"Bearer {admin_jwt}"},
    )
    assert r.status_code in (200, 204), r.text

    # 3. IpLog.worker_id 가 NULL 인지 확인
    db = env["Session"]()
    try:
        rec = db.get(IpLog, log_id)
        assert rec is not None  # IpLog 자체는 보존 (historical)
        assert rec.worker_id is None
    finally:
        db.close()


def test_iplog_fk_uses_set_null_ondelete():
    """model 의 FK 정의가 ondelete='SET NULL' 사용."""
    from hydra.db.models import IpLog
    col = IpLog.__table__.columns["worker_id"]
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    assert fks[0].ondelete == "SET NULL"


def test_delete_worker_clears_worker_log_tail(env):
    """worker 삭제 시 WorkerLogTail 도 함께 삭제 (Codex P2 post-review).

    WorkerLogTail.worker_id 는 nullable=False — 그대로 두면 FK 위반.
    단기 verbose 디버그 log 라 worker 와 함께 삭제가 자연스러움.
    """
    from hydra.db.models import WorkerLogTail
    from datetime import UTC, datetime, timedelta
    db = env["Session"]()
    try:
        log_entry = WorkerLogTail(
            worker_id=env["worker_a_id"],
            occurred_at=datetime.now(UTC),
            received_at=datetime.now(UTC),
            level="INFO",
            logger_name="test",
            message="hello",
        )
        db.add(log_entry); db.commit()
        # running task 는 미리 정리해서 delete_worker 통과시킴
        from hydra.db.models import Task
        db.query(Task).filter(Task.worker_id == env["worker_a_id"]).update(
            {Task.status: "completed"}, synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()

    import jwt as _jwt
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    r = env["client"].delete(
        f"/api/admin/workers/{env['worker_a_id']}",
        headers={"Authorization": f"Bearer {admin_jwt}"},
    )
    assert r.status_code in (200, 204), r.text

    db = env["Session"]()
    try:
        remaining = db.query(WorkerLogTail).filter(
            WorkerLogTail.worker_id == env["worker_a_id"]
        ).count()
        assert remaining == 0
    finally:
        db.close()


def test_iplog_end_soft_passes_legacy_null_worker(env):
    """worker_id 가 NULL 인 옛 row 는 (backfill 없음) soft pass."""
    db = env["Session"]()
    try:
        rec = IpLog(
            account_id=env["account_id"], ip_address="9.9.9.9", device_id="legacy",
            worker_id=None,  # explicit NULL — backfill 없는 옛 row simulation
        )
        db.add(rec); db.commit(); db.refresh(rec)
        log_id = rec.id
    finally:
        db.close()

    end_r = env["client"].post(
        "/api/workers/ip-log/end",
        headers=_hdr(env["tok_b"]),
        json={"log_id": log_id},
    )
    assert end_r.status_code == 200  # NULL → 호환 path


# ───────── P2.3 — retry backoff sequence shortened ─────────

def test_retry_backoff_uses_shortened_sequence(monkeypatch):
    """worker.client retry 가 1/2/4/8 → 0.5/1/2/4 시퀀스로 sleep.

    heartbeat tick blackhole 시 worst-case 합산을 줄여 reactivity 개선.
    """
    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "worker.client.time.sleep",
        lambda s: sleep_calls.append(s),
    )
    # 모든 retry path 실패 → 4 회 sleep 발생
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://unreachable.localhost:1")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt-test")

    import httpx
    from worker.client import ServerClient

    class FailHttp:
        def request(self, method, url, **kw):
            raise httpx.ConnectError("blackhole")
        def close(self): pass

    sc = ServerClient()
    # persistent + 4 fresh attempts 모두 실패 호출
    with patch("worker.client._mk_client", return_value=FailHttp()):
        with pytest.raises(httpx.ConnectError):
            sc._request("POST", "/x")

    # backoff 시퀀스 검증 (4 회) — 0.5, 1, 2, 4
    assert len(sleep_calls) == 4
    assert sleep_calls[0] == pytest.approx(0.5)
    assert sleep_calls[1] == pytest.approx(1.0)
    assert sleep_calls[2] == pytest.approx(2.0)
    assert sleep_calls[3] == pytest.approx(4.0)
