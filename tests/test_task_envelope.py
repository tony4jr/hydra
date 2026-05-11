"""PR-A: TaskEnvelope protocol — unit tests.

Tests scope:
1. AccountSnapshot / WorkerConfig / TaskEnvelope construct + serialize.
2. Schema version present.
3. Transitional v2/fetch response carries BOTH legacy flat fields AND envelope.
4. redact_for_logging masks all SECRET_FIELDS, recursively, in dict/list/Model.
5. Envelope-from-task fallback path (worker side) survives legacy responses.
"""
from __future__ import annotations

import pytest

from hydra.protocol import (
    AccountSnapshot,
    TaskEnvelope,
    WorkerConfig,
    redact_for_logging,
)
from hydra.protocol.task_envelope import SCHEMA_VERSION, SECRET_FIELDS


def _make_snapshot(**overrides) -> AccountSnapshot:
    defaults = dict(
        id=42,
        gmail="alice@example.com",
        encrypted_password="ENC:xyz",
        recovery_email="alice.recovery@example.com",
        adspower_profile_id="prof_abc",
        persona='{"speed_multiplier": 1.1, "typing_style": "typist"}',
        encrypted_totp_secret="ENC:totp",
        status="active",
        ipp_flagged=False,
        youtube_channel_id="UCxxx",
    )
    defaults.update(overrides)
    return AccountSnapshot(**defaults)


# ───────────────────── model basics ─────────────────────


def test_account_snapshot_roundtrip():
    snap = _make_snapshot()
    dumped = snap.model_dump()
    restored = AccountSnapshot.model_validate(dumped)
    assert restored == snap


def test_worker_config_defaults_are_sane():
    wc = WorkerConfig()
    assert wc.ip_cooldown_minutes >= 1
    assert wc.max_session_minutes >= 5
    assert wc.max_tasks_per_session >= 1


def test_task_envelope_minimal_construct():
    snap = _make_snapshot()
    env = TaskEnvelope(task_id=1, task_type="comment", account=snap)
    assert env.schema_version == SCHEMA_VERSION
    assert env.priority == "normal"  # default
    assert env.instructions == []   # PR-A: empty


def test_envelope_carries_worker_config():
    snap = _make_snapshot()
    wc = WorkerConfig(adb_device_id="DEV123", ip_cooldown_minutes=15)
    env = TaskEnvelope(task_id=2, task_type="like_boost", account=snap, worker_config=wc)
    assert env.worker_config.adb_device_id == "DEV123"
    assert env.worker_config.ip_cooldown_minutes == 15


# ───────────────────── redaction ─────────────────────


def test_redact_masks_password_in_dict():
    out = redact_for_logging({"gmail": "a@b.c", "encrypted_password": "secret"})
    assert out["gmail"] == "a@b.c"
    assert out["encrypted_password"] == "***REDACTED***"


def test_redact_recurses_into_nested_dict():
    out = redact_for_logging({"account": {"encrypted_password": "x", "id": 5}, "msg": "hi"})
    assert out["account"]["encrypted_password"] == "***REDACTED***"
    assert out["account"]["id"] == 5
    assert out["msg"] == "hi"


def test_redact_recurses_into_list():
    out = redact_for_logging([{"encrypted_password": "p1"}, {"totp_secret": "t1", "ok": True}])
    assert out[0]["encrypted_password"] == "***REDACTED***"
    assert out[1]["totp_secret"] == "***REDACTED***"
    assert out[1]["ok"] is True


def test_redact_handles_pydantic_model():
    snap = _make_snapshot()
    out = redact_for_logging(snap)
    assert out["encrypted_password"] == "***REDACTED***"
    assert out["encrypted_totp_secret"] == "***REDACTED***"
    assert out["gmail"] == "alice@example.com"


def test_redact_covers_all_known_secret_fields():
    # Build a dict with every secret name; redact should mask all of them.
    payload = {name: f"VAL_{name}" for name in SECRET_FIELDS}
    payload["public"] = "ok"
    out = redact_for_logging(payload)
    for name in SECRET_FIELDS:
        assert out[name] == "***REDACTED***", f"{name} not redacted"
    assert out["public"] == "ok"


def test_redact_passes_through_scalars():
    assert redact_for_logging("plain") == "plain"
    assert redact_for_logging(42) == 42
    assert redact_for_logging(None) is None


# ───────────────────── transitional response shape ─────────────────────


def test_v2_fetch_response_carries_envelope_and_legacy_fields():
    """v2/fetch builds a response with envelope + flat compatibility fields."""
    # Simulate server building the response (no FastAPI; just shape verification).
    snap = _make_snapshot()
    wc = WorkerConfig(adb_device_id="DEV123")
    envelope = TaskEnvelope(
        task_id=100,
        task_type="comment",
        priority="urgent",
        payload='{"video_id":"abc"}',
        account=snap,
        worker_config=wc,
    )
    envelope_dump = envelope.model_dump(mode="json")
    response = {"tasks": [{
        "id": 100,
        "account_id": snap.id,
        "adspower_profile_id": snap.adspower_profile_id,
        "task_type": "comment",
        "payload": '{"video_id":"abc"}',
        "priority": "urgent",
        "account_snapshot": envelope_dump["account"],
        "envelope": envelope_dump,
    }]}

    task_dict = response["tasks"][0]
    # Legacy clients keep working
    assert task_dict["id"] == 100
    assert task_dict["task_type"] == "comment"
    assert task_dict["account_snapshot"]["gmail"] == "alice@example.com"
    # New envelope-based clients
    parsed = TaskEnvelope.model_validate(task_dict["envelope"])
    assert parsed.task_id == 100
    assert parsed.account.id == snap.id
    assert parsed.worker_config.adb_device_id == "DEV123"


# ───────────────────── worker-side envelope-from-task fallback ─────────────────────


def _envelope_from_task(task: dict):
    """Mirror of worker/app.py:_envelope_from_task — kept here as reference impl
    so the test owns the contract (any change must update both)."""
    env = task.get("envelope")
    if env:
        return TaskEnvelope.model_validate(env)
    snap = task.get("account_snapshot")
    if not snap or task.get("id") is None or not task.get("task_type"):
        return None
    return TaskEnvelope(
        task_id=task["id"],
        task_type=task["task_type"],
        priority=task.get("priority") or "normal",
        payload=task.get("payload"),
        account=AccountSnapshot.model_validate(snap),
        worker_config=WorkerConfig(),
    )


def test_worker_parses_new_envelope_shape():
    snap = _make_snapshot()
    env = TaskEnvelope(task_id=7, task_type="like", account=snap)
    task = {"id": 7, "task_type": "like", "envelope": env.model_dump(mode="json")}
    parsed = _envelope_from_task(task)
    assert parsed is not None
    assert parsed.task_id == 7
    assert parsed.account.adspower_profile_id == "prof_abc"


def test_worker_falls_back_to_legacy_shape_when_envelope_missing():
    snap = _make_snapshot()
    task = {
        "id": 8,
        "task_type": "comment",
        "priority": "normal",
        "payload": None,
        "account_snapshot": snap.model_dump(),
    }
    parsed = _envelope_from_task(task)
    assert parsed is not None
    assert parsed.task_id == 8
    assert parsed.account.gmail == "alice@example.com"


def test_worker_returns_none_when_neither_envelope_nor_snapshot():
    parsed = _envelope_from_task({"id": 9, "task_type": "comment"})
    assert parsed is None


def test_worker_prefers_envelope_over_legacy_when_both_present():
    """Worker should trust envelope (canonical) when it exists; snapshot is fallback."""
    snap_in_envelope = _make_snapshot(id=100, gmail="from-envelope@x.com")
    snap_in_legacy = _make_snapshot(id=200, gmail="from-legacy@x.com")
    env = TaskEnvelope(task_id=10, task_type="like", account=snap_in_envelope)
    task = {
        "id": 10,
        "task_type": "like",
        "envelope": env.model_dump(mode="json"),
        "account_snapshot": snap_in_legacy.model_dump(),
    }
    parsed = _envelope_from_task(task)
    assert parsed.account.gmail == "from-envelope@x.com"
