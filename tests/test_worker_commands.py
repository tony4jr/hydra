"""T3 원격 명령 시스템 — 발행 → heartbeat 전달 → ack."""
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
from hydra.db.models import Base, Worker, WorkerCommand


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture
def env(monkeypatch, tmp_path):
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
    raw_token = "worker-token-cmd-xxxxxxxxxxxxxxxxxxx"
    w = Worker(
        name="cmd-worker",
        token_hash=hash_password(raw_token),
        token_prefix=raw_token[:8],
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
    yield {
        "client": client, "worker_token": raw_token, "worker_id": worker_id,
        "admin_jwt": admin_jwt, "Session": TestSession,
    }
    engine.dispose()


def _admin(env):
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


def _worker(env):
    return {"X-Worker-Token": env["worker_token"]}


def test_admin_issues_command_and_worker_receives_via_heartbeat(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "run_diag", "payload": {"script": "diag_adspower_profiles.py"}},
    )
    assert r.status_code == 200
    cmd = r.json()
    assert cmd["status"] == "pending"
    assert cmd["command"] == "run_diag"

    # 워커 heartbeat → pending_commands 포함
    hb = env["client"].post(
        "/api/workers/heartbeat/v2",
        headers=_worker(env),
        json={"version": "v", "os_type": "linux"},
    )
    assert hb.status_code == 200
    body = hb.json()
    assert len(body["pending_commands"]) == 1
    assert body["pending_commands"][0]["command"] == "run_diag"
    assert body["pending_commands"][0]["payload"] == {"script": "diag_adspower_profiles.py"}

    # 두 번째 heartbeat → 이미 delivered 됐으므로 비어있음
    hb2 = env["client"].post(
        "/api/workers/heartbeat/v2",
        headers=_worker(env),
        json={"version": "v"},
    )
    assert hb2.json()["pending_commands"] == []


def test_admin_unknown_command_rejected(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "rm_rf_slash", "payload": None},
    )
    assert r.status_code == 400


def test_worker_acks_command_marks_done(env):
    cmd_id = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "run_diag"},
    ).json()["id"]

    # heartbeat 로 pickup
    env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json={"version": "v"})

    # ack
    r = env["client"].post(
        f"/api/workers/command/{cmd_id}/ack",
        headers=_worker(env),
        json={"status": "done", "result": "spawned"},
    )
    assert r.status_code == 200

    # 어드민 list 에서 done 확인
    rs = env["client"].get(
        f"/api/admin/workers/{env['worker_id']}/commands",
        headers=_admin(env),
    )
    assert rs.json()[0]["status"] == "done"
    assert rs.json()[0]["result"] == "spawned"


def test_worker_cannot_ack_other_workers_command(env):
    cmd_id = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "run_diag"},
    ).json()["id"]

    # 다른 워커 토큰
    db = env["Session"]()
    other_raw = "other-worker-token-yyyyyyyyyyyyyyyyy"
    other = Worker(
        name="other", token_hash=hash_password(other_raw),
        token_prefix=other_raw[:8], token_sha256=_sha(other_raw),
    )
    db.add(other); db.commit(); db.close()

    r = env["client"].post(
        f"/api/workers/command/{cmd_id}/ack",
        headers={"X-Worker-Token": other_raw},
        json={"status": "done"},
    )
    assert r.status_code == 403


def test_admin_command_requires_admin_auth(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        json={"command": "restart"},
    )
    assert r.status_code == 401


def test_all_8_commands_accepted(env):
    commands = [
        "restart", "update_now", "run_diag", "retry_task",
        "screenshot_now", "stop_all_browsers", "refresh_fingerprint", "update_adspower_patch",
    ]
    for c in commands:
        r = env["client"].post(
            f"/api/admin/workers/{env['worker_id']}/command",
            headers=_admin(env),
            json={"command": c},
        )
        assert r.status_code == 200, f"{c}: {r.text}"
