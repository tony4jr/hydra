"""Slice 1 — Worker Admin Agent redesign tests.

Coverage:
  1. shell_exec 발행 + /shell convenience endpoint
  2. heartbeat lease 획득 + expired lease redelivery
  3. worker-side shell_exec 결과 shape / timeout / truncation
  4. HYDRA_DISABLE_TASK_REGISTER=1 → task_register skip
  5. HYDRA_UPDATE_OWNER=agent → self-update 거부

spec: docs/WORKER_ADMIN_AGENT_TASK_0_0.md (Slice 1).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

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

    raw_token = "worker-token-slice1-xxxxxxxxxxxxxxxxxxx"
    db = TestSession()
    w = Worker(
        name="slice1-worker",
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


def _admin(env) -> dict:
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


def _worker(env) -> dict:
    return {"X-Worker-Token": env["worker_token"]}


def _hb_body() -> dict:
    return {
        "version": "test", "os_type": "linux",
        "cpu_percent": 0.0, "mem_used_mb": 0, "disk_free_gb": 0.0,
        "adb_devices": [], "adspower_version": "", "playwright_browsers_ok": True,
    }


# ───────── 1. shell_exec 발행 + /shell convenience endpoint ─────────

def test_admin_shell_exec_via_command_endpoint(env):
    """generic /command 엔드포인트로 shell_exec 발행 가능."""
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "shell_exec", "payload": {"shell": "sh", "script": "echo hi", "timeout_sec": 5}},
    )
    assert r.status_code == 200, r.text
    cmd = r.json()
    assert cmd["command"] == "shell_exec"
    assert cmd["status"] == "pending"
    assert cmd["payload"]["script"] == "echo hi"


def test_admin_shell_convenience_endpoint(env):
    """/shell endpoint 가 내부적으로 WorkerCommand(shell_exec) 만든다."""
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"shell": "sh", "script": "echo conv", "timeout_sec": 10},
    )
    assert r.status_code == 200, r.text
    cmd = r.json()
    assert cmd["command"] == "shell_exec"
    assert cmd["payload"]["script"] == "echo conv"
    assert cmd["payload"]["shell"] == "sh"
    assert cmd["payload"]["timeout_sec"] == 10


def test_admin_shell_rejects_oversized_script(env):
    """script 8000 자 초과는 400."""
    big = "a" * 8001
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"script": big, "timeout_sec": 5},
    )
    assert r.status_code == 400


def test_admin_shell_rejects_bad_shell(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"shell": "bash", "script": "echo x"},
    )
    assert r.status_code == 400


def test_admin_shell_rejects_bad_timeout(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"script": "echo x", "timeout_sec": 9999},
    )
    assert r.status_code == 400


# ───────── follow-up: generic /command shell_exec validation parity ─────────

def test_generic_command_shell_exec_rejects_missing_script(env):
    """generic /command 로 shell_exec 보내도 /shell 과 같은 가드. payload 누락 → 400."""
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "shell_exec"},  # payload 없음
    )
    assert r.status_code == 400
    assert "script" in r.text.lower()


def test_generic_command_shell_exec_rejects_empty_script(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "shell_exec", "payload": {"script": ""}},
    )
    assert r.status_code == 400


def test_generic_command_shell_exec_rejects_oversized_script(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "shell_exec", "payload": {"script": "a" * 8001}},
    )
    assert r.status_code == 400


def test_generic_command_shell_exec_rejects_bad_shell(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "shell_exec", "payload": {"script": "echo x", "shell": "bash"}},
    )
    assert r.status_code == 400


def test_generic_command_shell_exec_rejects_bad_timeout(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "shell_exec", "payload": {"script": "echo x", "timeout_sec": 9999}},
    )
    assert r.status_code == 400


def test_generic_command_shell_exec_normalizes_payload(env):
    """valid shell_exec payload 는 generic 경로도 통과 + 기본값 채워서 정규화."""
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "shell_exec", "payload": {"script": "echo norm"}},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["command"] == "shell_exec"
    # default shell + timeout 채워졌는지
    assert out["payload"]["shell"] == "powershell"
    assert out["payload"]["timeout_sec"] == 30
    assert out["payload"]["script"] == "echo norm"

    # DB 에 저장된 payload 도 normalized JSON 인지 확인
    db = env["Session"]()
    try:
        c = db.get(WorkerCommand, out["id"])
        assert c.command == "shell_exec"
        stored = json.loads(c.payload)
        assert stored == {"shell": "powershell", "script": "echo norm", "timeout_sec": 30}
    finally:
        db.close()


# ───────── 2. heartbeat lease + expired lease redelivery ─────────

def test_heartbeat_picks_up_command_with_lease(env):
    """heartbeat 응답에 command 가 포함되고 status=leased + lease_expires_at 박힌다."""
    # admin 이 shell_exec 발행
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"shell": "sh", "script": "echo lease", "timeout_sec": 5},
    )
    assert r.status_code == 200
    cmd_id = r.json()["id"]

    # 워커 heartbeat
    hb = env["client"].post(
        "/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body(),
    )
    assert hb.status_code == 200
    pending = hb.json()["pending_commands"]
    assert len(pending) == 1
    assert pending[0]["id"] == cmd_id
    assert pending[0]["command"] == "shell_exec"

    # DB 검증
    db = env["Session"]()
    try:
        c = db.get(WorkerCommand, cmd_id)
        assert c.status == "leased"
        assert c.lease_expires_at is not None
        assert c.attempt_count == 1
        assert c.delivered_at is not None
    finally:
        db.close()


def test_heartbeat_does_not_redeliver_while_lease_valid(env):
    """lease 유효 (아직 만료 안 됨) 동안 다음 heartbeat 는 같은 command 안 가져옴."""
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"script": "echo a"},
    )
    cmd_id = r.json()["id"]

    hb1 = env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())
    assert len(hb1.json()["pending_commands"]) == 1

    hb2 = env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())
    # lease 가 아직 살아있으므로 재배달 안 함
    assert all(c["id"] != cmd_id for c in hb2.json()["pending_commands"])


def test_heartbeat_redelivers_expired_lease(env):
    """lease_expires_at 가 과거이면 다음 heartbeat 에서 재배달 + attempt_count 증가."""
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"script": "echo retry"},
    )
    cmd_id = r.json()["id"]

    # 1차 heartbeat — lease 획득
    env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())

    # lease 강제 만료
    db = env["Session"]()
    try:
        c = db.get(WorkerCommand, cmd_id)
        c.lease_expires_at = datetime.now(UTC) - timedelta(seconds=10)
        db.commit()
    finally:
        db.close()

    # 2차 heartbeat — 재배달
    hb2 = env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())
    pending = hb2.json()["pending_commands"]
    ids = [p["id"] for p in pending]
    assert cmd_id in ids

    db = env["Session"]()
    try:
        c = db.get(WorkerCommand, cmd_id)
        assert c.status == "leased"
        assert c.attempt_count == 2
        assert c.lease_expires_at > datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    finally:
        db.close()


def test_heartbeat_marks_failed_after_attempt_max(env):
    """ATTEMPT_MAX 회 연속 lease 만료 → 4번째 heartbeat 에서 failed 처리.

    Slice 1 follow-up #2 — 무한 재전달 방지.
    """
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"script": "echo attempt"},
    )
    cmd_id = r.json()["id"]

    for cycle in range(3):
        # heartbeat → lease 획득 (attempt_count 가 1,2,3 순서로 증가)
        hb = env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())
        ids = [c["id"] for c in hb.json()["pending_commands"]]
        assert cmd_id in ids, f"cycle {cycle} expected delivery"

        # lease 강제 만료 — worker 가 ack 못 하고 죽었다 가정
        db = env["Session"]()
        try:
            c = db.get(WorkerCommand, cmd_id)
            c.lease_expires_at = datetime.now(UTC) - timedelta(seconds=10)
            db.commit()
        finally:
            db.close()

    # 4번째 heartbeat — attempt_count 가 4 가 되어 ATTEMPT_MAX(3) 초과 → failed
    hb_final = env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())
    ids = [c["id"] for c in hb_final.json()["pending_commands"]]
    assert cmd_id not in ids, "must not redeliver beyond ATTEMPT_MAX"

    db = env["Session"]()
    try:
        c = db.get(WorkerCommand, cmd_id)
        assert c.status == "failed"
        assert c.lease_expires_at is None
        assert "attempt_limit_exceeded" in (c.error_message or "")
    finally:
        db.close()


def test_heartbeat_non_redeliverable_command_fails_on_expiry(env):
    """restart/update_now 같이 ack 직후 self-exit 하는 명령은 만료시 재배달 금지 → failed."""
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "restart"},
    )
    cmd_id = r.json()["id"]

    # 1차 heartbeat — lease 획득
    hb1 = env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())
    assert any(c["id"] == cmd_id for c in hb1.json()["pending_commands"])

    # lease 강제 만료 (워커가 ack 못 하고 죽었다고 가정)
    db = env["Session"]()
    try:
        c = db.get(WorkerCommand, cmd_id)
        c.lease_expires_at = datetime.now(UTC) - timedelta(seconds=10)
        db.commit()
    finally:
        db.close()

    # 2차 heartbeat — non-redeliverable 이라 재배달 안 되고 failed 박힘
    hb2 = env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())
    assert all(c["id"] != cmd_id for c in hb2.json()["pending_commands"])

    db = env["Session"]()
    try:
        c = db.get(WorkerCommand, cmd_id)
        assert c.status == "failed"
        assert c.lease_expires_at is None
        assert "non_redeliverable" in (c.error_message or "")
    finally:
        db.close()


def test_shell_exec_lease_uses_timeout_plus_buffer(env):
    """shell_exec lease_sec = timeout_sec + 30 (min 60, max 300). 일반 명령은 60."""
    # timeout=120 → expected lease ~ 150s
    r_big = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"script": "echo long", "timeout_sec": 120},
    )
    big_id = r_big.json()["id"]

    # timeout=5 → min 60 적용 → 60s
    r_small = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"script": "echo short", "timeout_sec": 5},
    )
    small_id = r_small.json()["id"]

    # 일반 command (timeout 무관) → 60s
    r_norm = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/command",
        headers=_admin(env),
        json={"command": "screenshot_now"},
    )
    norm_id = r_norm.json()["id"]

    before = datetime.now(UTC)
    env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())

    db = env["Session"]()
    try:
        big = db.get(WorkerCommand, big_id)
        small = db.get(WorkerCommand, small_id)
        norm = db.get(WorkerCommand, norm_id)
        # lease 길이 검증 — SQLite 의 naive datetime 비교용으로 timezone strip
        before_naive = before.replace(tzinfo=None)
        big_lease_dur = (big.lease_expires_at - before_naive).total_seconds()
        small_lease_dur = (small.lease_expires_at - before_naive).total_seconds()
        norm_lease_dur = (norm.lease_expires_at - before_naive).total_seconds()
        # timeout 120 → 150s. 약간 tolerance.
        assert 145 < big_lease_dur < 156, f"big lease {big_lease_dur}"
        # timeout 5 → max(60, 35) = 60s
        assert 55 < small_lease_dur < 65, f"small lease {small_lease_dur}"
        # 일반 명령 → 60s
        assert 55 < norm_lease_dur < 65, f"norm lease {norm_lease_dur}"
    finally:
        db.close()


def test_sqlite_dialect_skips_for_update_lock(env, monkeypatch):
    """SQLite 환경에서 with_for_update 안 호출 (테스트 호환 fallback)."""
    # SQLite 의 SQLAlchemy with_for_update 는 무시되지만, 명시적으로 dialect 분기 검증.
    # 우리 코드는 dialect_name == "postgresql" 일 때만 with_for_update(skip_locked=True).
    # 즉 sqlite 환경에선 with_for_update 가 query 에 안 박혀야 함.

    # 실제 SQL 검증은 어려우므로, heartbeat 가 SQLite 에서 그대로 동작하는지 확인.
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"script": "echo sqlite"},
    )
    cmd_id = r.json()["id"]

    hb = env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())
    assert hb.status_code == 200
    ids = [c["id"] for c in hb.json()["pending_commands"]]
    assert cmd_id in ids


def test_ack_clears_lease_and_sets_final_state(env):
    r = env["client"].post(
        f"/api/admin/workers/{env['worker_id']}/shell",
        headers=_admin(env),
        json={"script": "echo done"},
    )
    cmd_id = r.json()["id"]
    env["client"].post("/api/workers/heartbeat/v2", headers=_worker(env), json=_hb_body())

    # ack done
    ack = env["client"].post(
        f"/api/workers/command/{cmd_id}/ack",
        headers=_worker(env),
        json={"status": "done", "result": '{"exit_code":0,"stdout":"done\\n","stderr":"","truncated":false,"duration_ms":3,"shell":"sh"}'},
    )
    assert ack.status_code == 200

    db = env["Session"]()
    try:
        c = db.get(WorkerCommand, cmd_id)
        assert c.status == "done"
        assert c.completed_at is not None
        assert c.lease_expires_at is None
        # started_at 도 채워져 있어야 함
        assert c.started_at is not None
    finally:
        db.close()


# ───────── 3. worker-side shell_exec 결과 shape / timeout / truncation ─────────

def test_run_shell_exec_returns_expected_schema():
    """sh fallback 으로 echo 실행 → JSON schema 검증."""
    from worker.commands import _run_shell_exec
    result_json = _run_shell_exec(shell="sh", script="echo hello", timeout_sec=5)
    obj = json.loads(result_json)
    assert obj["exit_code"] == 0
    assert obj["stdout"].strip() == "hello"
    assert obj["stderr"] == ""
    assert obj["truncated"] is False
    assert "duration_ms" in obj
    assert obj["shell"] == "sh"


def test_run_shell_exec_captures_stderr_and_nonzero_exit():
    from worker.commands import _run_shell_exec
    obj = json.loads(_run_shell_exec(
        shell="sh", script="echo err 1>&2; exit 7", timeout_sec=5,
    ))
    assert obj["exit_code"] == 7
    assert "err" in obj["stderr"]


def test_run_shell_exec_timeout():
    """script 가 timeout 초과 → exit_code=-1 + error=timeout."""
    from worker.commands import _run_shell_exec
    obj = json.loads(_run_shell_exec(shell="sh", script="sleep 5", timeout_sec=1))
    assert obj["exit_code"] == -1
    assert obj["error"] == "timeout"


def test_run_shell_exec_truncates_large_stdout():
    from worker.commands import _run_shell_exec, SHELL_OUTPUT_CAP_BYTES
    # 100KB output
    n_bytes = SHELL_OUTPUT_CAP_BYTES + 4096
    obj = json.loads(_run_shell_exec(
        shell="sh",
        script=f"head -c {n_bytes} /dev/urandom | base64 | head -c {n_bytes}",
        timeout_sec=10,
    ))
    assert obj["exit_code"] == 0
    assert obj["truncated"] is True
    assert len(obj["stdout"].encode("utf-8", errors="replace")) <= SHELL_OUTPUT_CAP_BYTES + 4  # decode slack


def test_run_shell_exec_script_length_guard():
    from worker.commands import _run_shell_exec, SHELL_MAX_SCRIPT_LEN
    obj = json.loads(_run_shell_exec(
        shell="sh", script="a" * (SHELL_MAX_SCRIPT_LEN + 1), timeout_sec=5,
    ))
    assert obj["exit_code"] == -2
    assert "script length" in obj["error"]


def test_run_shell_exec_timeout_guard():
    from worker.commands import _run_shell_exec
    obj = json.loads(_run_shell_exec(shell="sh", script="echo x", timeout_sec=9999))
    assert obj["exit_code"] == -3


def test_run_shell_exec_unsupported_shell():
    from worker.commands import _run_shell_exec
    obj = json.loads(_run_shell_exec(shell="bash", script="echo x", timeout_sec=5))
    assert obj["exit_code"] == -4


# ───────── 4. HYDRA_DISABLE_TASK_REGISTER → skip ─────────

def test_task_register_disable_flag(monkeypatch, capsys):
    monkeypatch.setenv("HYDRA_DISABLE_TASK_REGISTER", "1")
    monkeypatch.setattr(sys, "platform", "win32")  # Windows 환경 흉내
    called = {"subprocess_run": 0}

    def _spy(*a, **kw):
        called["subprocess_run"] += 1
        raise AssertionError("subprocess should not run when flag set")

    monkeypatch.setattr("worker.task_register.subprocess.run", _spy)

    from worker.task_register import ensure_registered
    ensure_registered()  # should be no-op
    out = capsys.readouterr().out
    assert called["subprocess_run"] == 0
    assert "HYDRA_DISABLE_TASK_REGISTER" in out


def test_task_register_runs_when_flag_absent(monkeypatch):
    monkeypatch.delenv("HYDRA_DISABLE_TASK_REGISTER", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")  # 비 Windows 라 또 no-op (early return)
    from worker.task_register import ensure_registered
    ensure_registered()  # no-op without raising


# ───────── 5. HYDRA_UPDATE_OWNER → self-update 거부 ─────────

def test_perform_update_blocked_when_owner_not_self(monkeypatch, tmp_path):
    monkeypatch.setenv("HYDRA_UPDATE_OWNER", "agent")
    from worker.updater import perform_update
    with pytest.raises(RuntimeError, match="self-update disabled"):
        perform_update(repo_dir=str(tmp_path))


def test_perform_update_proceeds_with_default_owner(monkeypatch, tmp_path):
    """기본 HYDRA_UPDATE_OWNER 미설정 → owner=self → gate 통과해서 git 호출 시도.

    실제 git 호출은 차단하고 첫 subprocess.check_call 에서 인터셉트.
    """
    monkeypatch.delenv("HYDRA_UPDATE_OWNER", raising=False)
    calls = []

    def _spy(argv, *a, **kw):
        calls.append(argv)
        raise RuntimeError("intercepted")

    monkeypatch.setattr("worker.updater.subprocess.check_call", _spy)
    monkeypatch.setattr("worker.updater.subprocess.check_output", _spy)

    from worker.updater import perform_update
    # gate 는 통과해야 → 첫 subprocess 호출 도달 → intercepted RuntimeError → sys.exit(1)
    with pytest.raises(SystemExit) as exc_info:
        perform_update(repo_dir=str(tmp_path))
    assert exc_info.value.code == 1
    # 첫 호출이 git fetch 였어야
    assert calls and calls[0][0] == "git" and "fetch" in calls[0]
