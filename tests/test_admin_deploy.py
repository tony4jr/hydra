"""Task 25 — /api/admin/{deploy,pause,unpause,canary}."""
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core import server_config as scfg
from hydra.db.models import Base


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
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {"client": client, "admin_jwt": admin_jwt, "session": TestSession}
    engine.dispose()


def _hdr(env):
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


# ── 인증 ──

def test_all_endpoints_require_auth(env):
    for method, path, body in [
        ("POST", "/api/admin/deploy", None),
        ("POST", "/api/admin/pause", None),
        ("POST", "/api/admin/unpause", None),
        ("POST", "/api/admin/canary", {"worker_ids": [1]}),
    ]:
        resp = env["client"].request(method, path, json=body)
        assert resp.status_code == 401, f"{method} {path}"


# ── pause / unpause ──

def test_pause_sets_server_config(env):
    resp = env["client"].post("/api/admin/pause", headers=_hdr(env))
    assert resp.status_code == 200
    assert resp.json() == {"paused": True}
    assert scfg.is_paused() is True


def test_unpause_clears_server_config(env):
    scfg.set_paused(True)
    resp = env["client"].post("/api/admin/unpause", headers=_hdr(env))
    assert resp.status_code == 200
    assert resp.json() == {"paused": False}
    assert scfg.is_paused() is False


# ── canary ──

def test_canary_stores_worker_ids(env):
    resp = env["client"].post(
        "/api/admin/canary",
        headers=_hdr(env),
        json={"worker_ids": [1, 2, 3]},
    )
    assert resp.status_code == 200
    assert resp.json()["canary_worker_ids"] == [1, 2, 3]
    assert scfg.get_canary_worker_ids() == [1, 2, 3]


def test_canary_empty_list_clears(env):
    scfg.set_canary_worker_ids([7, 8])
    resp = env["client"].post(
        "/api/admin/canary", headers=_hdr(env), json={"worker_ids": []},
    )
    assert resp.status_code == 200
    assert scfg.get_canary_worker_ids() == []


# ── deploy (subprocess mocking) ──

def test_deploy_starts_subprocess(env, tmp_path, monkeypatch):
    # 실제 스크립트 대신 가짜 경로 — is_file() True 되도록 tmp 에 작성
    fake_script = tmp_path / "deploy.sh"
    fake_script.write_text("#!/bin/bash\necho ok\n")
    monkeypatch.setattr("hydra.web.routes.admin_deploy.DEPLOY_SCRIPT", fake_script)

    with patch("subprocess.Popen") as popen:
        popen.return_value.pid = 99999
        resp = env["client"].post("/api/admin/deploy", headers=_hdr(env))
    assert resp.status_code == 200
    body = resp.json()
    assert body["started"] is True
    assert body["pid"] == 99999
    popen.assert_called_once()
    # start_new_session=True 필수 (부모 죽어도 계속)
    kwargs = popen.call_args.kwargs
    assert kwargs.get("start_new_session") is True


def test_deploy_returns_500_if_script_missing(env, tmp_path, monkeypatch):
    missing = tmp_path / "no.sh"
    monkeypatch.setattr("hydra.web.routes.admin_deploy.DEPLOY_SCRIPT", missing)
    resp = env["client"].post("/api/admin/deploy", headers=_hdr(env))
    assert resp.status_code == 500
