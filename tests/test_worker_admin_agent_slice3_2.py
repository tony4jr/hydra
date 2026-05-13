"""Slice 3.2 — enroll API role + role immutability + capabilities 정책.

Coverage:
  1. admin /enroll: role + parent_worker_id 인자
     - admin_agent + parent_worker_id 없으면 400
     - admin_agent + 존재하지 않는 parent_worker_id 400
     - admin_agent + parent_worker_id 가 admin_agent 이면 400
     - desktop_worker + parent_worker_id 있으면 400
     - 같은 desktop 에 admin_agent 이미 있으면 409 (1:1 강제)
  2. enrollment_token 에 role / parent_worker_id payload
  3. worker /enroll consume:
     - 새 worker: token 의 role / parent_worker_id 반영
     - 재enroll 동일 role/parent → OK (raw_token 재발급)
     - 재enroll 다른 role → 409 (immutable)
     - 재enroll 다른 parent → 409 (immutable)
     - admin_agent consume 시 parent 가 사라졌으면 409 (stale token)
     - 같은 desktop 의 두 번째 admin_agent enroll → 409 (1:1)
  4. heartbeat: role 무시 (immutable) — 이미 Slice 2.1 테스트에서 검증
  5. PATCH /role:
     - admin 변경 가능
     - 잘못된 role 400
     - 1:1 위반 시 409
     - 변경 시 pending/leased + target_role mismatch 즉시 fail

spec: docs/WORKER_ADMIN_AGENT_TASK_0_0.md Phase 3 — role immutable 확정.
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
from hydra.core.enrollment import generate_enrollment_token, verify_enrollment_token
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
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-secret-123456789")
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")
    monkeypatch.setenv("SERVER_URL", "https://test.example.com")

    db = TestSession()
    desktop_token = "wtok-desktop-xxxxxxxxxxxxxxxxxxxxxxxxxx"
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
    desktop_id = desktop.id
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
        "admin_jwt": admin_jwt,
    }
    engine.dispose()


def _admin(env) -> dict:
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


# ───────── 1. enrollment token role/parent payload ─────────

@pytest.fixture
def enroll_secret(monkeypatch):
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-secret-123456789")


def test_enrollment_token_carries_role_and_parent(enroll_secret):
    tok = generate_enrollment_token("agent-x", role="admin_agent", parent_worker_id=42)
    data = verify_enrollment_token(tok)
    assert data["worker_name"] == "agent-x"
    assert data["role"] == "admin_agent"
    assert data["parent_worker_id"] == 42


def test_enrollment_token_default_role_desktop_worker(enroll_secret):
    tok = generate_enrollment_token("desk-x")
    data = verify_enrollment_token(tok)
    assert data["role"] == "desktop_worker"
    assert "parent_worker_id" not in data


# ───────── 2. admin /enroll role validation ─────────

def test_admin_enroll_admin_agent_requires_parent(env):
    r = env["client"].post(
        "/api/admin/workers/enroll",
        headers=_admin(env),
        json={"worker_name": "agent-1", "role": "admin_agent"},
    )
    assert r.status_code == 400
    assert "parent_worker_id" in r.text


def test_admin_enroll_admin_agent_parent_must_exist(env):
    r = env["client"].post(
        "/api/admin/workers/enroll",
        headers=_admin(env),
        json={"worker_name": "agent-1", "role": "admin_agent", "parent_worker_id": 99999},
    )
    assert r.status_code == 400
    assert "not found" in r.text


def test_admin_enroll_admin_agent_parent_must_be_desktop(env):
    # 이미 admin_agent 만들고 그것을 parent 로 시도
    db = env["Session"]()
    a = Worker(
        name="agent-existing",
        token_hash=hash_password("xx-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        token_sha256=_sha("xx-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        token_prefix="xx-aaaaa",
        role="admin_agent",
        parent_worker_id=env["desktop_id"],
    )
    db.add(a); db.commit(); db.refresh(a)
    bad_parent = a.id
    db.close()

    r = env["client"].post(
        "/api/admin/workers/enroll",
        headers=_admin(env),
        json={
            "worker_name": "agent-new",
            "role": "admin_agent",
            "parent_worker_id": bad_parent,
        },
    )
    assert r.status_code == 400
    assert "must be desktop_worker" in r.text


def test_admin_enroll_desktop_worker_rejects_parent(env):
    r = env["client"].post(
        "/api/admin/workers/enroll",
        headers=_admin(env),
        json={"worker_name": "desk-2", "role": "desktop_worker", "parent_worker_id": env["desktop_id"]},
    )
    assert r.status_code == 400
    assert "must not set parent_worker_id" in r.text


def test_admin_enroll_admin_agent_1to1_enforced(env):
    # 첫 번째 admin_agent enroll (실제 worker 생성)
    db = env["Session"]()
    a = Worker(
        name="agent-1",
        token_hash=hash_password("xx-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),
        token_sha256=_sha("xx-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),
        token_prefix="xx-bbbbb",
        role="admin_agent",
        parent_worker_id=env["desktop_id"],
    )
    db.add(a); db.commit(); db.close()

    # 같은 desktop 에 두 번째 admin_agent 발급 시도 → 409
    r = env["client"].post(
        "/api/admin/workers/enroll",
        headers=_admin(env),
        json={
            "worker_name": "agent-2",
            "role": "admin_agent",
            "parent_worker_id": env["desktop_id"],
        },
    )
    assert r.status_code == 409
    assert "1:1" in r.text


def test_admin_enroll_response_includes_role(env):
    r = env["client"].post(
        "/api/admin/workers/enroll",
        headers=_admin(env),
        json={
            "worker_name": "agent-new",
            "role": "admin_agent",
            "parent_worker_id": env["desktop_id"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "admin_agent"
    assert body["parent_worker_id"] == env["desktop_id"]
    assert "enrollment_token" in body
    # 토큰에 role/parent 박힘
    data = verify_enrollment_token(body["enrollment_token"])
    assert data["role"] == "admin_agent"
    assert data["parent_worker_id"] == env["desktop_id"]


def test_admin_enroll_reenroll_role_immutable(env):
    # desktop-1 이미 desktop_worker — admin_agent 로 재발급 시도 → 409
    r = env["client"].post(
        "/api/admin/workers/enroll",
        headers=_admin(env),
        json={
            "worker_name": "desktop-1",
            "role": "admin_agent",
            "parent_worker_id": env["desktop_id"],
        },
    )
    # admin_agent + parent=self 가 먼저 desktop_worker check 통과해야 하는데,
    # 우리 logic 에서 role/parent validation 후 existing.role 검사. desktop-1
    # 자체가 parent 가 되면 parent.role == desktop_worker 라 validation 통과.
    # 그 후 existing.role != req.role → 409.
    assert r.status_code == 409
    assert "immutable" in r.text


# ───────── 3. worker /enroll consume ─────────

def _enroll_worker(env, name: str, role: str = "desktop_worker", parent_id: int | None = None):
    tok = generate_enrollment_token(name, role=role, parent_worker_id=parent_id)
    return env["client"].post(
        "/api/workers/enroll",
        json={"enrollment_token": tok, "hostname": "host-x"},
    )


def test_worker_enroll_consume_creates_with_role_and_parent(env):
    r = _enroll_worker(env, "agent-fresh", role="admin_agent", parent_id=env["desktop_id"])
    assert r.status_code == 200, r.text
    new_id = r.json()["worker_id"]
    db = env["Session"]()
    w = db.get(Worker, new_id)
    assert w.role == "admin_agent"
    assert w.parent_worker_id == env["desktop_id"]
    db.close()


def test_worker_enroll_reenroll_same_role_ok(env):
    r1 = _enroll_worker(env, "agent-A", role="admin_agent", parent_id=env["desktop_id"])
    assert r1.status_code == 200
    r2 = _enroll_worker(env, "agent-A", role="admin_agent", parent_id=env["desktop_id"])
    assert r2.status_code == 200
    # 같은 worker_id, 새 worker_token
    assert r2.json()["worker_id"] == r1.json()["worker_id"]
    assert r2.json()["worker_token"] != r1.json()["worker_token"]


def test_worker_enroll_reenroll_different_role_409(env):
    r1 = _enroll_worker(env, "agent-B", role="admin_agent", parent_id=env["desktop_id"])
    assert r1.status_code == 200
    r2 = _enroll_worker(env, "agent-B", role="desktop_worker")
    assert r2.status_code == 409
    assert "immutable" in r2.text


def test_worker_enroll_admin_agent_stale_token_parent_deleted(env):
    # admin_agent token 발급 → parent 삭제 → consume 시 409
    tok = generate_enrollment_token(
        "agent-stale", role="admin_agent", parent_worker_id=env["desktop_id"],
    )
    db = env["Session"]()
    db.query(Worker).filter(Worker.id == env["desktop_id"]).delete()
    db.commit(); db.close()

    r = env["client"].post(
        "/api/workers/enroll",
        json={"enrollment_token": tok, "hostname": "host-x"},
    )
    assert r.status_code == 409
    assert "consume" in r.text or "stale" in r.text or "re-enroll" in r.text


def test_worker_enroll_admin_agent_1to1_enforced_at_consume(env):
    # 첫 admin_agent 등록
    r1 = _enroll_worker(env, "agent-X", role="admin_agent", parent_id=env["desktop_id"])
    assert r1.status_code == 200
    # 두 번째 admin_agent (다른 name) 같은 parent → 409
    r2 = _enroll_worker(env, "agent-Y", role="admin_agent", parent_id=env["desktop_id"])
    assert r2.status_code == 409
    assert "1:1" in r2.text


def test_worker_enroll_legacy_token_without_role_defaults_desktop(env):
    """기존 발급된 옛 토큰 (role payload 없음) 호환 — desktop_worker 로 처리."""
    import jwt as _jwt_lib
    import os
    payload = {
        "worker_name": "legacy-1",
        "nonce": "xx",
        "type": "enrollment",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    tok = _jwt_lib.encode(payload, os.environ["ENROLLMENT_SECRET"], algorithm="HS256")
    r = env["client"].post(
        "/api/workers/enroll",
        json={"enrollment_token": tok, "hostname": "host-x"},
    )
    assert r.status_code == 200, r.text
    db = env["Session"]()
    w = db.query(Worker).filter_by(name="legacy-1").first()
    assert w.role == "desktop_worker"
    assert w.parent_worker_id is None
    db.close()


# ───────── 4. PATCH /role admin endpoint ─────────

def test_patch_role_changes_role(env):
    # desktop-1 을 desktop_worker → admin_agent 로 변경. parent 가 자기 자신이면
    # parent.role 검증 통과 못 함. 다른 desktop 만들어서 parent 로.
    db = env["Session"]()
    other_desk = Worker(
        name="desk-other",
        token_hash=hash_password("yy-cccccccccccccccccccccccccccccccccc"),
        token_sha256=_sha("yy-cccccccccccccccccccccccccccccccccc"),
        token_prefix="yy-ccccc",
        role="desktop_worker",
    )
    db.add(other_desk); db.commit(); db.refresh(other_desk)
    other_id = other_desk.id
    db.close()

    # desktop-1 (현재 desktop_worker) 을 admin_agent 로, parent=other_id
    r = env["client"].patch(
        f"/api/admin/workers/{env['desktop_id']}/role",
        headers=_admin(env),
        json={"role": "admin_agent", "parent_worker_id": other_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin_agent"
    assert r.json()["parent_worker_id"] == other_id


def test_patch_role_invalid_role_400(env):
    r = env["client"].patch(
        f"/api/admin/workers/{env['desktop_id']}/role",
        headers=_admin(env),
        json={"role": "weird"},
    )
    assert r.status_code == 400


def test_patch_role_1to1_violation_409(env):
    # desktop 에 admin_agent 이미 있음
    db = env["Session"]()
    other_desk = Worker(
        name="desk-other2",
        token_hash=hash_password("yy-dddddddddddddddddddddddddddddddddd"),
        token_sha256=_sha("yy-dddddddddddddddddddddddddddddddddd"),
        token_prefix="yy-ddddd",
        role="desktop_worker",
    )
    db.add(other_desk); db.commit(); db.refresh(other_desk)
    existing_agent = Worker(
        name="agent-existing",
        token_hash=hash_password("yy-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"),
        token_sha256=_sha("yy-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"),
        token_prefix="yy-eeeee",
        role="admin_agent",
        parent_worker_id=other_desk.id,
    )
    db.add(existing_agent); db.commit(); db.refresh(existing_agent)
    other_id = other_desk.id
    db.close()

    # desktop-1 을 admin_agent (parent=other_id) 로 PATCH → 409 (이미 admin_agent 있음)
    r = env["client"].patch(
        f"/api/admin/workers/{env['desktop_id']}/role",
        headers=_admin(env),
        json={"role": "admin_agent", "parent_worker_id": other_id},
    )
    assert r.status_code == 409


def test_patch_role_fails_pending_commands_with_mismatch_target_role(env):
    """PATCH /role 변경 시 pending/leased + target_role mismatch 인 command 즉시 fail."""
    db = env["Session"]()
    # 다른 desktop 만들어 parent 로
    other_desk = Worker(
        name="desk-z",
        token_hash=hash_password("zz-fffffffffffffffffffffffffffffffffff"),
        token_sha256=_sha("zz-fffffffffffffffffffffffffffffffffff"),
        token_prefix="zz-fffff",
        role="desktop_worker",
    )
    db.add(other_desk); db.commit(); db.refresh(other_desk)
    other_id = other_desk.id
    # desktop-1 에 target_role="desktop_worker" pending command (정상)
    keep_cmd = WorkerCommand(
        worker_id=env["desktop_id"],
        command="run_diag",
        status="pending",
        issued_at=datetime.now(UTC),
        target_role="desktop_worker",
    )
    # desktop-1 에 target_role="admin_agent" pending command (mismatch — PATCH 후 fail)
    fail_cmd = WorkerCommand(
        worker_id=env["desktop_id"],
        command="agent_update_now",
        status="pending",
        issued_at=datetime.now(UTC),
        target_role="admin_agent",
    )
    # target_role NULL — 정책 영향 안 받음
    null_cmd = WorkerCommand(
        worker_id=env["desktop_id"],
        command="ensure_schema",
        status="pending",
        issued_at=datetime.now(UTC),
        target_role=None,
    )
    db.add_all([keep_cmd, fail_cmd, null_cmd])
    db.commit()
    keep_id, fail_id, null_id = keep_cmd.id, fail_cmd.id, null_cmd.id
    db.close()

    # desktop-1 을 admin_agent 로 변경
    r = env["client"].patch(
        f"/api/admin/workers/{env['desktop_id']}/role",
        headers=_admin(env),
        json={"role": "admin_agent", "parent_worker_id": other_id},
    )
    assert r.status_code == 200, r.text

    db = env["Session"]()
    keep = db.get(WorkerCommand, keep_id)
    fail = db.get(WorkerCommand, fail_id)
    null = db.get(WorkerCommand, null_id)
    # keep_cmd target_role="desktop_worker", 새 role=admin_agent → mismatch → fail
    assert keep.status == "failed"
    assert "role_mismatch_after_role_change" in (keep.error_message or "")
    # fail_cmd target_role="admin_agent", 새 role=admin_agent → match → pending 유지
    assert fail.status == "pending"
    # null_cmd target_role NULL → 영향 없음
    assert null.status == "pending"
    db.close()


def test_patch_role_child_admin_agent_invariant_409(env):
    """desktop_worker A 에 admin_agent B 가 붙어있을 때 A → admin_agent 로
    PATCH 하면 B.parent.role 가 admin_agent 됨 (invariant violation). 거부.
    Codex Slice 3.2 review 권고.
    """
    db = env["Session"]()
    other_desk = Worker(
        name="desk-parent",
        token_hash=hash_password("zz-iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"),
        token_sha256=_sha("zz-iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"),
        token_prefix="zz-iiiii",
        role="desktop_worker",
    )
    db.add(other_desk); db.commit(); db.refresh(other_desk)
    other_id = other_desk.id
    # desktop-1 에 admin_agent (child) 붙임
    child = Worker(
        name="agent-child",
        token_hash=hash_password("zz-jjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjj"),
        token_sha256=_sha("zz-jjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjj"),
        token_prefix="zz-jjjjj",
        role="admin_agent",
        parent_worker_id=env["desktop_id"],
    )
    db.add(child); db.commit(); db.close()

    # desktop-1 (parent of admin_agent) → admin_agent 로 PATCH 시도 → 409
    r = env["client"].patch(
        f"/api/admin/workers/{env['desktop_id']}/role",
        headers=_admin(env),
        json={"role": "admin_agent", "parent_worker_id": other_id},
    )
    assert r.status_code == 409
    assert "child invariant" in r.text


def test_db_partial_unique_index_enforces_1to1(env):
    """1:1 강제가 DB partial unique index 로도 백업됨.
    앱 레벨 검사가 race 등으로 우회되어도 DB 가 IntegrityError 로 차단.
    """
    from sqlalchemy.exc import IntegrityError
    db = env["Session"]()
    # 첫 admin_agent 직접 insert
    a1 = Worker(
        name="agent-A",
        token_hash=hash_password("zz-kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk"),
        token_sha256=_sha("zz-kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk"),
        token_prefix="zz-kkkkk",
        role="admin_agent",
        parent_worker_id=env["desktop_id"],
    )
    db.add(a1); db.commit()
    # 두 번째 admin_agent 같은 parent 직접 insert — partial unique index 차단
    a2 = Worker(
        name="agent-B",
        token_hash=hash_password("zz-llllllllllllllllllllllllllllllllll"),
        token_sha256=_sha("zz-llllllllllllllllllllllllllllllllll"),
        token_prefix="zz-lllll",
        role="admin_agent",
        parent_worker_id=env["desktop_id"],
    )
    db.add(a2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback(); db.close()


def test_patch_role_noop_does_not_touch_commands(env):
    """같은 role/parent 로 PATCH 시 command 영향 없음."""
    db = env["Session"]()
    c = WorkerCommand(
        worker_id=env["desktop_id"],
        command="run_diag",
        status="pending",
        issued_at=datetime.now(UTC),
        target_role="admin_agent",  # mismatch (desktop-1 은 desktop_worker)
    )
    db.add(c); db.commit(); db.refresh(c)
    cid = c.id
    db.close()

    # 같은 role 로 PATCH (noop)
    r = env["client"].patch(
        f"/api/admin/workers/{env['desktop_id']}/role",
        headers=_admin(env),
        json={"role": "desktop_worker"},
    )
    assert r.status_code == 200

    db = env["Session"]()
    c = db.get(WorkerCommand, cid)
    # noop 이라 command 정리 안 됨 (이미 mismatch 였지만 PATCH 가 안 건드림)
    assert c.status == "pending"
    db.close()
