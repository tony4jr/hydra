"""Slice 3.1 — WorkerCommand.target_role + dispatch routing.

Coverage:
  1. WorkerCommand 모델에 target_role 컬럼 존재 (nullable)
  2. admin POST /command 가 admin-only 명령을 desktop_worker 에 발행하면
     paired admin_agent 로 auto-route + target_role="admin_agent" 저장
  3. paired admin_agent 없으면 409
  4. admin-only 명령을 직접 admin_agent 에 발행 → 그대로 + target_role 박힘
  5. 일반 명령 (run_diag 등) 은 target_role 정책 없음 → 발행 worker.role 가 그대로
  6. heartbeat lease: target_role 와 worker.role 가 mismatch 면 failed +
     "role_mismatch:..." error_message, 재배달 안 함
  7. backward compat: target_role IS NULL 인 명령은 role 체크 안 함
  8. CommandRequest.target_role override 가 mismatch 면 400
  9. migration c1d2e3wcmdtr 가 SQLite batch 에서 깨끗하게 적용

spec: docs/WORKER_ADMIN_AGENT_TASK_0_0.md Phase 3 — worker_id 잘못 발행해도
자동 routing + heartbeat mismatch 시 fail-closed.
"""
from __future__ import annotations

import hashlib
import json
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
    desktop_token = "wtok-desktop-xxxxxxxxxxxxxxxxxxxxxxxxxx"
    agent_token = "wtok-agent-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    desktop = Worker(
        name="desktop-1",
        token_hash=hash_password(desktop_token),
        token_prefix=desktop_token[:8],
        token_sha256=_sha(desktop_token),
        role="desktop_worker",
        allow_campaign=True,
        allowed_task_types='["*"]',
    )
    db.add(desktop); db.commit(); db.refresh(desktop)
    agent = Worker(
        name="agent-1",
        token_hash=hash_password(agent_token),
        token_prefix=agent_token[:8],
        token_sha256=_sha(agent_token),
        role="admin_agent",
        parent_worker_id=desktop.id,
        allow_campaign=True,
        allowed_task_types='["*"]',
    )
    db.add(agent); db.commit(); db.refresh(agent)
    # 두 번째 desktop (paired agent 없음 → 409 시나리오)
    orphan_token = "wtok-orphan-xxxxxxxxxxxxxxxxxxxxxxxxxxx"
    orphan = Worker(
        name="orphan-desktop",
        token_hash=hash_password(orphan_token),
        token_prefix=orphan_token[:8],
        token_sha256=_sha(orphan_token),
        role="desktop_worker",
        allow_campaign=True,
        allowed_task_types='["*"]',
    )
    db.add(orphan); db.commit(); db.refresh(orphan)
    desktop_id, agent_id, orphan_id = desktop.id, agent.id, orphan.id
    db.close()

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {
        "client": client, "Session": TestSession,
        "desktop_token": desktop_token, "desktop_id": desktop_id,
        "agent_token": agent_token, "agent_id": agent_id,
        "orphan_token": orphan_token, "orphan_id": orphan_id,
        "admin_jwt": admin_jwt,
    }
    engine.dispose()


def _admin(env) -> dict:
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


# ───────── 1. 모델 컬럼 ─────────

def test_worker_command_has_target_role_column():
    assert "target_role" in WorkerCommand.__table__.columns
    col = WorkerCommand.__table__.columns["target_role"]
    assert col.nullable is True


# ───────── 2. admin-only 명령 → desktop_id 발행 → paired agent 로 auto-route ─────────

def test_admin_only_command_on_desktop_auto_routes_to_paired_agent(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['desktop_id']}/command",
        headers=_admin(env),
        json={"command": "agent_update_now"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["worker_id"] == env["agent_id"]
    assert body["target_role"] == "admin_agent"
    assert body["requested_worker_id"] == env["desktop_id"]


# ───────── 3. paired agent 없으면 409 ─────────

def test_admin_only_command_without_paired_agent_409(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['orphan_id']}/command",
        headers=_admin(env),
        json={"command": "agent_update_now"},
    )
    assert r.status_code == 409
    assert "no paired admin_agent" in r.json()["detail"]


# ───────── 4. admin-only 명령 → admin_agent 직발행 ─────────

def test_admin_only_command_direct_to_admin_agent(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['agent_id']}/command",
        headers=_admin(env),
        json={"command": "desktop_cutover_status"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["worker_id"] == env["agent_id"]
    assert body["target_role"] == "admin_agent"
    assert body["requested_worker_id"] is None


# ───────── 5. 일반 명령은 target_role NULL (Codex follow-up) ─────────

def test_generic_command_target_role_null(env):
    """일반 명령 (정책 없음, override 없음) → target_role=NULL.
    Codex Slice 3.1 review: 일반 명령에 worker.role 박으면 후속 role 변경
    시 mismatch fail. 일반 명령은 NULL 박아 role 변경에 면역.
    """
    r = env["client"].post(
        f"/api/admin/workers/{env['desktop_id']}/command",
        headers=_admin(env),
        json={"command": "run_diag"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["worker_id"] == env["desktop_id"]
    assert body["target_role"] is None


def test_generic_command_with_explicit_override(env):
    """일반 명령이라도 override 명시하면 그 값 박힘 (단 worker.role 일치)."""
    r = env["client"].post(
        f"/api/admin/workers/{env['desktop_id']}/command",
        headers=_admin(env),
        json={"command": "run_diag", "target_role": "desktop_worker"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["target_role"] == "desktop_worker"


# ───────── 6. heartbeat lease: target_role mismatch → failed + role_mismatch ─────────

def test_heartbeat_lease_role_mismatch_fails(env):
    """target_role='admin_agent' 박힌 명령을 어쩌다 desktop_worker 가 lease
    하려는 경우 (예: role 가 후속 변경됨). failed + role_mismatch error,
    재배달 안 함.
    """
    db = env["Session"]()
    # admin_agent 에 cutover 명령 박음
    cmd = WorkerCommand(
        worker_id=env["agent_id"],
        command="desktop_cutover_status",
        status="pending",
        issued_at=datetime.now(UTC),
        target_role="admin_agent",
    )
    db.add(cmd); db.commit(); db.refresh(cmd)
    cmd_id = cmd.id
    # agent.role 을 desktop_worker 로 강제 변경 (invariant 깨진 상황 simulate)
    agent = db.get(Worker, env["agent_id"])
    agent.role = "desktop_worker"
    db.commit(); db.close()

    r = env["client"].post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": env["agent_token"]},
        json={
            "version": "test", "os_type": "linux",
            "cpu_percent": 0.0, "mem_used_mb": 0, "disk_free_gb": 0.0,
            "adb_devices": [], "adspower_version": "",
            "playwright_browsers_ok": True,
        },
    )
    assert r.status_code == 200, r.text
    # 명령은 pending_commands 에서 빠짐 + DB 에서 failed + role_mismatch
    pending_ids = [c["id"] for c in r.json().get("pending_commands", [])]
    assert cmd_id not in pending_ids

    db = env["Session"]()
    c = db.get(WorkerCommand, cmd_id)
    assert c.status == "failed"
    assert "role_mismatch" in (c.error_message or "")
    assert "target=admin_agent" in c.error_message
    assert "actual=desktop_worker" in c.error_message
    db.close()


# ───────── 7. backward compat: target_role IS NULL 이면 체크 skip ─────────

def test_heartbeat_lease_target_role_null_backward_compat(env):
    db = env["Session"]()
    cmd = WorkerCommand(
        worker_id=env["desktop_id"],
        command="run_diag",
        status="pending",
        issued_at=datetime.now(UTC),
        target_role=None,  # 명시적 NULL
    )
    db.add(cmd); db.commit(); db.refresh(cmd)
    cmd_id = cmd.id
    db.close()

    r = env["client"].post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": env["desktop_token"]},
        json={
            "version": "test", "os_type": "linux",
            "cpu_percent": 0.0, "mem_used_mb": 0, "disk_free_gb": 0.0,
            "adb_devices": [], "adspower_version": "",
            "playwright_browsers_ok": True,
        },
    )
    assert r.status_code == 200
    pending_ids = [c["id"] for c in r.json().get("pending_commands", [])]
    assert cmd_id in pending_ids


# ───────── 8. override mismatch → 400 ─────────

def test_target_role_override_mismatch_400(env):
    """운영자가 desktop_worker 명령에 target_role='admin_agent' 박았는데
    실제 결정된 worker.role 이 desktop_worker 면 400.
    """
    r = env["client"].post(
        f"/api/admin/workers/{env['desktop_id']}/command",
        headers=_admin(env),
        json={"command": "run_diag", "target_role": "admin_agent"},
    )
    assert r.status_code == 400


def test_target_role_override_invalid_value_400(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['desktop_id']}/command",
        headers=_admin(env),
        json={"command": "run_diag", "target_role": "weird_role"},
    )
    assert r.status_code == 400


# ───────── 9. Codex follow-up: ambiguous paired admin_agent → 409 ─────────

def test_admin_only_command_with_ambiguous_paired_admin_agents_409(env):
    """Slice 3.1 defensive code: paired admin_agent 가 2개 이상이면 409 ambiguous.

    Slice 3.2 follow-up 이후 DB partial unique index 가 1:1 강제하므로 이
    상태 자체가 발생 불가능 — 두 번째 admin_agent insert 가 IntegrityError.
    Slice 3.1 의 ambiguous 분기는 방어 코드로 보존되지만 reachable 하지 않음.
    """
    from sqlalchemy.exc import IntegrityError
    db = env["Session"]()
    extra_token = "wtok-agent2-xxxxxxxxxxxxxxxxxxxxxxxxxx"
    extra = Worker(
        name="agent-2",
        token_hash=hash_password(extra_token),
        token_prefix=extra_token[:8],
        token_sha256=_sha(extra_token),
        role="admin_agent",
        parent_worker_id=env["desktop_id"],
    )
    db.add(extra)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback(); db.close()


# ───────── 10. Codex follow-up: /shell 도 _resolve_command_target 거침 ─────────

def test_shell_endpoint_uses_resolve_target(env):
    """/shell convenience endpoint 도 _resolve_command_target 거쳐서
    target_role=NULL 박힘 (shell_exec 는 _CMD_REQUIRED_ROLE 에 없음).
    Codex review: 발행 경로 parity 필수.
    """
    r = env["client"].post(
        f"/api/admin/workers/{env['desktop_id']}/shell",
        headers=_admin(env),
        json={"script": "echo hi", "shell": "powershell", "timeout_sec": 5},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["command"] == "shell_exec"
    assert body["target_role"] is None
    assert body["worker_id"] == env["desktop_id"]


def test_shell_endpoint_404_when_worker_missing(env):
    """/shell 도 _resolve_command_target 에서 worker not found → 404."""
    r = env["client"].post(
        "/api/admin/workers/999999/shell",
        headers=_admin(env),
        json={"script": "echo hi"},
    )
    assert r.status_code == 404


# ───────── 11. migration regression ─────────

def test_migration_c1d2e3wcmdtr_upgrades_clean_on_sqlite_batch(tmp_path, monkeypatch):
    """alembic c1d2e3wcmdtr 가 SQLite batch_alter_table 모드에서 깨지지 않는지.

    head 까지 가면 후속 migration 가 빈 db 와 충돌하므로 target 명시.
    """
    import sqlite3
    from pathlib import Path
    from alembic.config import Config
    from alembic import command as _alembic_cmd
    from hydra.core.config import settings

    db_path = tmp_path / "hydra_test_3_1.db"
    db_url = f"sqlite:///{db_path}"

    # 직전 head (b1c2d3iplogsn) 까지 적용된 상태를 가정. worker_commands 가
    # 존재해야 c1d2e3wcmdtr 의 batch_alter_table 이 의미 있음. 빈 db 에서
    # 전체 upgrade 는 다른 migration (accounts 등) 의 회귀로 깨질 수 있어
    # 직접 stub schema + alembic_version 으로 분리 테스트.
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
        INSERT INTO alembic_version VALUES ('b1c2d3iplogsn');
        CREATE TABLE worker_commands (
            id INTEGER PRIMARY KEY,
            worker_id INTEGER NOT NULL,
            command VARCHAR(64) NOT NULL,
            payload TEXT,
            status VARCHAR(16) NOT NULL,
            issued_by INTEGER,
            issued_at DATETIME NOT NULL,
            delivered_at DATETIME,
            completed_at DATETIME,
            result TEXT,
            error_message TEXT,
            lease_expires_at DATETIME,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            started_at DATETIME
        );
    """)
    conn.commit()
    conn.close()

    monkeypatch.setattr(settings, "db_url", db_url)
    repo_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    _alembic_cmd.upgrade(cfg, "c1d2e3wcmdtr")

    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(worker_commands)").fetchall()}
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(worker_commands)").fetchall()}
    conn.close()
    assert "target_role" in cols
    assert "idx_wcmd_target_role" in indexes
