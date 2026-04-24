"""어드민 → 서버 → 워커 AdsPower 키 분배 파이프라인 테스트."""
import hashlib
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, Worker


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


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
    raw_token = "worker-token-xyz123-aaaaaaaaaaaaaaaaaa"
    w = Worker(
        name="win-1",
        status="offline",
        token_hash=hash_password(raw_token),
        token_sha256=_sha(raw_token),
    )
    db.add(w); db.commit(); db.refresh(w)
    worker_id = w.id
    db.close()

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {"client": client, "worker_token": raw_token, "worker_id": worker_id,
           "admin_jwt": admin_jwt, "Session": TestSession}
    engine.dispose()


def test_admin_sets_adspower_key_and_worker_gets_it_in_heartbeat(env):
    # 어드민이 키 설정
    r = env["client"].patch(
        f"/api/admin/workers/{env['worker_id']}",
        headers={"Authorization": f"Bearer {env['admin_jwt']}"},
        json={"adspower_api_key": "c58c38361c77d636a3174307f25cada3008992867e7dd9c6"},
    )
    assert r.status_code == 200

    # DB 에 암호화되어 저장됐는지
    db = env["Session"]()
    w = db.get(Worker, env["worker_id"])
    assert w.adspower_api_key_enc is not None
    assert w.adspower_api_key_enc != "c58c38361c77d636a3174307f25cada3008992867e7dd9c6"
    db.close()

    # 워커가 heartbeat 하면 응답에 평문으로 포함
    r2 = env["client"].post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": env["worker_token"]},
        json={"version": "v", "os_type": "windows"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["adspower_api_key"] == "c58c38361c77d636a3174307f25cada3008992867e7dd9c6"


def test_admin_can_remove_key_with_empty_string(env):
    # 설정
    env["client"].patch(
        f"/api/admin/workers/{env['worker_id']}",
        headers={"Authorization": f"Bearer {env['admin_jwt']}"},
        json={"adspower_api_key": "some-key"},
    )
    # 제거
    env["client"].patch(
        f"/api/admin/workers/{env['worker_id']}",
        headers={"Authorization": f"Bearer {env['admin_jwt']}"},
        json={"adspower_api_key": ""},
    )

    r = env["client"].post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": env["worker_token"]},
        json={"version": "v"},
    )
    assert r.json()["adspower_api_key"] is None


def test_heartbeat_returns_null_when_no_key_set(env):
    r = env["client"].post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": env["worker_token"]},
        json={"version": "v"},
    )
    assert r.status_code == 200
    assert r.json()["adspower_api_key"] is None
