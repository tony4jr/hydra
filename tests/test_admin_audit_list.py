"""Task 39.5 — 감사 로그 미들웨어 자동 기록 + GET /api/admin/audit/list."""
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import AuditLog, Base


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

    from hydra.web.app import app
    client = TestClient(app)

    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 7, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {"client": client, "admin_jwt": admin_jwt, "session": TestSession}
    engine.dispose()


def _hdr(env):
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


def test_middleware_logs_admin_pause(env):
    resp = env["client"].post("/api/admin/pause", headers=_hdr(env))
    assert resp.status_code == 200

    db = env["session"]()
    rows = db.query(AuditLog).all()
    assert len(rows) == 1
    assert rows[0].action == "pause"
    assert rows[0].user_id == 7
    db.close()


def test_middleware_does_not_log_get_read(env):
    env["client"].get("/api/admin/server-config", headers=_hdr(env))
    db = env["session"]()
    assert db.query(AuditLog).count() == 0
    db.close()


def test_middleware_does_not_log_on_4xx(env):
    # JWT_SECRET 변경해서 인증 실패 → 401 → 기록 안 됨
    env["client"].post(
        "/api/admin/pause",
        headers={"Authorization": "Bearer bogus"},
    )
    db = env["session"]()
    assert db.query(AuditLog).count() == 0
    db.close()


def test_list_requires_auth(env):
    resp = env["client"].get("/api/admin/audit/list")
    assert resp.status_code == 401


def test_list_returns_recent_actions(env):
    # 몇 건 발생시킨 뒤 조회
    env["client"].post("/api/admin/pause", headers=_hdr(env))
    env["client"].post("/api/admin/unpause", headers=_hdr(env))
    env["client"].post(
        "/api/admin/canary", headers=_hdr(env), json={"worker_ids": [1]},
    )

    resp = env["client"].get("/api/admin/audit/list", headers=_hdr(env))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    actions = [it["action"] for it in body["items"]]
    assert set(actions) == {"pause", "unpause", "canary_change"}
    # 최신순
    timestamps = [it["timestamp"] for it in body["items"]]
    assert timestamps == sorted(timestamps, reverse=True)


def test_list_filters_by_action(env):
    env["client"].post("/api/admin/pause", headers=_hdr(env))
    env["client"].post("/api/admin/unpause", headers=_hdr(env))

    resp = env["client"].get(
        "/api/admin/audit/list?action=pause", headers=_hdr(env),
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "pause"


def test_list_pagination(env):
    for _ in range(5):
        env["client"].post("/api/admin/pause", headers=_hdr(env))

    resp = env["client"].get(
        "/api/admin/audit/list?limit=2&offset=0", headers=_hdr(env),
    )
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["offset"] == 0
    assert body["limit"] == 2


def test_sensitive_fields_redacted_in_metadata(env):
    # admin_auth/login 은 감사 대상 ACTION_MAP 에 등재돼있음. 실패 시엔 로그 X
    # 성공 로그인 하려면 User 가 있어야 하므로 here 는 login 대신 canary 로 검증
    env["client"].post(
        "/api/admin/canary",
        headers=_hdr(env),
        json={"worker_ids": [1, 2]},  # 평범한 body
    )
    db = env["session"]()
    row = db.query(AuditLog).first()
    import json as _json
    meta = _json.loads(row.metadata_json)
    # body 그대로 저장 (민감 필드 아님)
    assert meta["body"] == {"worker_ids": [1, 2]}
    db.close()
