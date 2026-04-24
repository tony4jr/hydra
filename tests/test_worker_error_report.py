"""워커 에러 리포팅 — POST /api/workers/report-error + admin listing."""
from datetime import UTC, datetime, timedelta
import json

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import Base, Worker, WorkerError
from hydra.core.auth import hash_password


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

    # 워커 하나 생성 + 토큰
    db = TestSession()
    raw_token = "worker-raw-token-abc123"
    w = Worker(name="test-worker", status="offline", token_hash=hash_password(raw_token))
    db.add(w)
    db.commit()
    db.refresh(w)
    worker_id = w.id
    db.close()

    from hydra.web.app import app
    client = TestClient(app)

    now = datetime.now(UTC)
    admin_token = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )

    yield {
        "client": client,
        "worker_token": raw_token,
        "worker_id": worker_id,
        "admin_token": admin_token,
        "session": TestSession,
    }
    engine.dispose()


def _worker_hdr(env):
    return {"X-Worker-Token": env["worker_token"]}


def _admin_hdr(env):
    return {"Authorization": f"Bearer {env['admin_token']}"}


def test_report_requires_worker_token(env):
    r = env["client"].post("/api/workers/report-error", json={"kind": "other", "message": "x"})
    assert r.status_code == 401


def test_report_saves_error_and_admin_can_list(env):
    r = env["client"].post(
        "/api/workers/report-error",
        headers=_worker_hdr(env),
        json={
            "kind": "heartbeat_fail",
            "message": "getaddrinfo failed",
            "traceback": "Traceback (most recent call last)...",
            "context": {"attempt": 3, "url": "https://hydra-prod.duckdns.org"},
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "deduped": False}

    # 어드민으로 조회
    r2 = env["client"].get("/api/admin/workers/errors", headers=_admin_hdr(env))
    assert r2.status_code == 200
    items = r2.json()
    assert len(items) == 1
    assert items[0]["kind"] == "heartbeat_fail"
    assert items[0]["message"] == "getaddrinfo failed"
    assert items[0]["worker_name"] == "test-worker"
    assert items[0]["context"] == {"attempt": 3, "url": "https://hydra-prod.duckdns.org"}


def test_report_dedupes_within_window(env):
    payload = {"kind": "heartbeat_fail", "message": "same error"}
    r1 = env["client"].post("/api/workers/report-error", headers=_worker_hdr(env), json=payload)
    r2 = env["client"].post("/api/workers/report-error", headers=_worker_hdr(env), json=payload)

    assert r1.json() == {"ok": True, "deduped": False}
    assert r2.json() == {"ok": True, "deduped": True}

    # DB 에 1건만 있어야
    db = env["session"]()
    count = db.query(WorkerError).count()
    db.close()
    assert count == 1


def test_report_different_messages_both_saved(env):
    env["client"].post("/api/workers/report-error", headers=_worker_hdr(env),
                       json={"kind": "heartbeat_fail", "message": "err A"})
    env["client"].post("/api/workers/report-error", headers=_worker_hdr(env),
                       json={"kind": "heartbeat_fail", "message": "err B"})

    db = env["session"]()
    count = db.query(WorkerError).count()
    db.close()
    assert count == 2


def test_admin_list_filters_by_kind(env):
    env["client"].post("/api/workers/report-error", headers=_worker_hdr(env),
                       json={"kind": "heartbeat_fail", "message": "hb"})
    env["client"].post("/api/workers/report-error", headers=_worker_hdr(env),
                       json={"kind": "task_fail", "message": "task"})

    r = env["client"].get(
        "/api/admin/workers/errors?kind=task_fail",
        headers=_admin_hdr(env),
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["kind"] == "task_fail"


def test_admin_list_requires_admin_auth(env):
    r = env["client"].get("/api/admin/workers/errors")
    assert r.status_code == 401


def test_unknown_kind_coerced_to_other(env):
    env["client"].post("/api/workers/report-error", headers=_worker_hdr(env),
                       json={"kind": "random-garbage", "message": "x"})
    db = env["session"]()
    saved = db.query(WorkerError).first()
    db.close()
    assert saved.kind == "other"
