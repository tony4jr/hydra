"""PR-A B++: 추가 회귀 가드 — Codex 검토 7개 지적 반영.

scope:
- #1 WorkerConfig random guard (worker/session.py)
- #2 envelope 누수 — pydantic ValidationError print 시 secret 안 노출
- #3 envelope-based 그룹핑 (flat vs envelope 불일치 차단)
- #4 worker.account_snapshot.AccountSnapshot.from_payload 가 envelope shape 도 읽음
- #5 ensure_safe_ip_from_snapshot fail-closed
- #7 v2/fetch worker.status='paused' 가드 + NULLS LAST + role pre-filter
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch

from hydra.protocol import AccountSnapshot, TaskEnvelope, WorkerConfig
from worker.account_snapshot import AccountSnapshot as WorkerAccountSnapshot


# ───────────────────── #1 WorkerConfig random guard ─────────────────────


def test_worker_session_handles_tiny_max_session_minutes():
    """max_session_minutes < 20 이어도 random.randint 가 크래시 안 함."""
    from worker.session import WorkerSession

    wc = WorkerConfig(max_session_minutes=5, max_tasks_per_session=1)
    snap = AccountSnapshot(
        id=1, gmail="a@b.c", encrypted_password="ENC", adspower_profile_id="p1"
    )
    # 생성자가 ValueError 안 던져야 함
    sess = WorkerSession(
        profile_id="p1", account_id=1, account_snapshot=snap, worker_config=wc,
    )
    # 하한 20분이 유지됨
    assert sess.max_session_minutes >= 20
    assert sess.max_tasks_per_session >= 3


def test_worker_session_uses_larger_max_when_envelope_says_so():
    from worker.session import WorkerSession

    wc = WorkerConfig(max_session_minutes=60, max_tasks_per_session=12)
    snap = AccountSnapshot(
        id=1, gmail="a@b.c", encrypted_password="ENC", adspower_profile_id="p1"
    )
    sess = WorkerSession(
        profile_id="p1", account_id=1, account_snapshot=snap, worker_config=wc,
    )
    assert 20 <= sess.max_session_minutes <= 60
    assert 3 <= sess.max_tasks_per_session <= 12


# ───────────────────── #2 envelope 누수 차단 ─────────────────────


def test_envelope_parse_failure_does_not_leak_input_in_message(capsys):
    """Pydantic ValidationError 메시지에 input data 가 들어가더라도
    워커 print 가 그 raw 메시지를 노출하지 않는다 (type name 만)."""
    from worker.app import _envelope_from_task

    bad_task = {
        "envelope": {
            "task_id": "not-an-int",  # int 기대 → ValidationError
            "task_type": "comment",
            "account": {
                "id": 1,
                "gmail": "a@b.c",
                "encrypted_password": "SUPER_SECRET_CIPHER_TEXT",
            },
        }
    }
    # 두 경로 다 실패 → None
    result = _envelope_from_task(bad_task)
    # envelope 실패 후 legacy 도 없음 → None
    assert result is None
    captured = capsys.readouterr()
    # 핵심: secret 가 print 에 안 들어감
    assert "SUPER_SECRET_CIPHER_TEXT" not in captured.out
    assert "SUPER_SECRET_CIPHER_TEXT" not in captured.err


# ───────────────────── #3 envelope-based 그룹핑 ─────────────────────


def test_grouping_uses_envelope_not_flat_fields():
    """flat adspower_profile_id 가 envelope.account.adspower_profile_id 와
    다를 때, envelope 이 canonical 이어야 한다."""
    from worker.app import _envelope_from_task

    env = TaskEnvelope(
        task_id=1,
        task_type="comment",
        account=AccountSnapshot(
            id=100,
            gmail="alice@example.com",
            encrypted_password="ENC",
            adspower_profile_id="canonical_profile",
        ),
    )
    task = {
        "id": 1,
        "task_type": "comment",
        "adspower_profile_id": "stale_flat_profile",  # legacy 가 다른 값
        "account_id": 999,                             # legacy 가 다른 id
        "envelope": env.model_dump(mode="json"),
    }
    parsed = _envelope_from_task(task)
    assert parsed is not None
    # envelope 이 우선
    assert parsed.account.id == 100
    assert parsed.account.adspower_profile_id == "canonical_profile"


# ───────────────────── #4 executor account_snapshot envelope 호환 ─────────────────────


def test_worker_account_snapshot_reads_envelope_shape():
    """envelope 가 있으면 envelope.account 를 우선 사용."""
    # crypto.decrypt 가 실패하지 않도록 평문 모의
    with patch("worker.account_snapshot.crypto.decrypt", side_effect=lambda x: f"DEC:{x}"):
        payload = {
            "envelope": {
                "task_id": 1,
                "task_type": "onboarding_verify",
                "account": {
                    "id": 42,
                    "gmail": "from-envelope@example.com",
                    "encrypted_password": "ENC_PWD",
                    "adspower_profile_id": "prof_env",
                },
            },
            # legacy shape 도 있지만 무시되어야 함
            "account_snapshot": {
                "id": 999,
                "gmail": "from-legacy@example.com",
                "encrypted_password": "ENC_PWD_LEGACY",
                "adspower_profile_id": "prof_legacy",
            },
        }
        snap = WorkerAccountSnapshot.from_payload(payload)
        assert snap.gmail == "from-envelope@example.com"
        assert snap.adspower_profile_id == "prof_env"
        assert snap.password == "DEC:ENC_PWD"


def test_worker_account_snapshot_falls_back_to_legacy_shape():
    """envelope 없으면 legacy account_snapshot 사용."""
    with patch("worker.account_snapshot.crypto.decrypt", side_effect=lambda x: f"DEC:{x}"):
        payload = {
            "account_snapshot": {
                "id": 7,
                "gmail": "legacy@example.com",
                "encrypted_password": "ENC",
                "adspower_profile_id": "prof_legacy",
            },
        }
        snap = WorkerAccountSnapshot.from_payload(payload)
        assert snap.gmail == "legacy@example.com"
        assert snap.adspower_profile_id == "prof_legacy"


# ───────────────────── #5 ensure_safe_ip_from_snapshot fail-closed ─────────────────────


@pytest.mark.asyncio
async def test_ensure_safe_ip_from_snapshot_raises_when_no_adb_device():
    """ADB 디바이스 미설정 시 silent skip 대신 IPRotationFailed 발생."""
    from hydra.infra.ip import ensure_safe_ip_from_snapshot
    from hydra.infra.ip_errors import IPRotationFailed

    with patch("hydra.infra.ip.settings") as s:
        s.adb_device_id = None
        s.ip_rotation_cooldown_minutes = 30
        with pytest.raises(IPRotationFailed) as ei:
            await ensure_safe_ip_from_snapshot(
                db=None, account_id=42, adb_device_id=None,
            )
        assert "no_adb_device_configured" in str(ei.value)


# ───────────────────── #7 v2/fetch 가드 ─────────────────────


def test_fetch_returns_empty_when_worker_is_paused():
    """worker.status='paused' 면 v2/fetch 가 빈 리스트 반환 (legacy parity)."""
    # 라우트 본체를 직접 호출 — DB/auth 모킹.
    from hydra.web.routes.tasks_api import fetch_tasks
    from unittest.mock import MagicMock

    fake_worker = MagicMock()
    fake_worker.status = "paused"
    fake_worker.allow_preparation = True
    fake_worker.allow_campaign = True
    result = fetch_tasks(worker=fake_worker)
    assert result == {"tasks": []}


def test_fetch_returns_empty_when_worker_role_blocks_all_types():
    """allow_preparation/allow_campaign 양쪽 False 면 SQL 안 때리고 즉시 빈 응답."""
    from hydra.web.routes.tasks_api import fetch_tasks
    from unittest.mock import MagicMock

    fake_worker = MagicMock()
    fake_worker.status = "online"
    fake_worker.allow_preparation = False
    fake_worker.allow_campaign = False
    result = fetch_tasks(worker=fake_worker)
    assert result == {"tasks": []}


def test_fetch_sql_nulls_last_in_order_by():
    """SQL string 에 NULLS LAST 가 들어있고 NULLS FIRST 는 없음."""
    from hydra.web.routes.tasks_api import _FETCH_SQL_PG, _FETCH_SQL_SQLITE

    pg_text = str(_FETCH_SQL_PG)
    sqlite_text = str(_FETCH_SQL_SQLITE)
    assert "NULLS LAST" in pg_text
    assert "NULLS FIRST" not in pg_text
    # SQLite: explicit CASE WHEN scheduled_at IS NULL THEN 1 ELSE 0
    assert "scheduled_at IS NULL THEN 1" in sqlite_text


def test_fetch_sql_has_role_prefilter():
    """SQL 에 allow_prep / allow_camp 바인딩이 들어있다."""
    from hydra.web.routes.tasks_api import _FETCH_SQL_PG, _FETCH_SQL_SQLITE

    for q in (str(_FETCH_SQL_PG), str(_FETCH_SQL_SQLITE)):
        assert ":allow_prep" in q
        assert ":allow_camp" in q
