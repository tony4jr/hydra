"""PR-E: phase 별 timeout + retry policy 테스트."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra.protocol import AccountSnapshot, WorkerConfig
from hydra.protocol.phase_config import (
    DEFAULT_PHASES, PhaseTimeout, PhaseSpec, get_phase_spec,
)


# ───── 기본 spec ─────


def test_default_phases_all_required_phases():
    """필수 phase 들 다 spec 있음."""
    required = {"session_start", "ip_rotate", "adspower_open", "cdp_connect",
                "video_goto", "compose", "submit", "session_end"}
    assert required.issubset(set(DEFAULT_PHASES.keys()))


def test_get_phase_spec_returns_default():
    spec = get_phase_spec("ip_rotate")
    assert spec.timeout_sec == 45
    assert spec.policy == "reschedule"


def test_get_phase_spec_unknown_returns_safe_default():
    spec = get_phase_spec("does_not_exist")
    assert spec.timeout_sec == 60
    assert spec.policy == "reschedule"


def test_get_phase_spec_env_override(monkeypatch):
    monkeypatch.setenv("HYDRA_PHASE_TIMEOUT_IP_ROTATE", "120")
    monkeypatch.setenv("HYDRA_PHASE_POLICY_IP_ROTATE", "fail")
    spec = get_phase_spec("ip_rotate")
    assert spec.timeout_sec == 120
    assert spec.policy == "fail"


def test_get_phase_spec_env_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("HYDRA_PHASE_TIMEOUT_IP_ROTATE", "not-a-number")
    monkeypatch.setenv("HYDRA_PHASE_POLICY_IP_ROTATE", "invalid-policy")
    spec = get_phase_spec("ip_rotate")
    # invalid → default 유지
    assert spec.timeout_sec == 45
    assert spec.policy == "reschedule"


# ───── PhaseTimeout 예외 ─────


def test_phase_timeout_message():
    pt = PhaseTimeout("ip_rotate", 47.3, 45, "reschedule")
    msg = pt.to_error_message()
    assert "phase_timeout" in msg
    assert "ip_rotate" in msg
    assert "47" in msg
    assert "45" in msg


def test_phase_timeout_attributes():
    pt = PhaseTimeout("submit", 31.5, 30, "unknown")
    assert pt.phase == "submit"
    assert pt.threshold_sec == 30
    assert pt.policy == "unknown"


# ───── WorkerSession.run_phase ─────


def _snap() -> AccountSnapshot:
    return AccountSnapshot(id=1, gmail="a@b.c", encrypted_password="E", adspower_profile_id="p")


@pytest.mark.asyncio
async def test_run_phase_succeeds_within_timeout():
    """timeout 안에 끝나면 정상 return."""
    from worker.session import WorkerSession

    async def quick():
        await asyncio.sleep(0.01)
        return "done"

    sess = WorkerSession(profile_id="p", account_id=1, account_snapshot=_snap())
    result = await sess.run_phase("ip_rotate", quick())
    assert result == "done"
    assert sess.current_phase == "ip_rotate"


@pytest.mark.asyncio
async def test_run_phase_raises_on_timeout(monkeypatch):
    """timeout 시 PhaseTimeout 발생."""
    from worker.session import WorkerSession

    # phase timeout 짧게 (테스트용)
    monkeypatch.setenv("HYDRA_PHASE_TIMEOUT_IP_ROTATE", "1")

    async def slow():
        await asyncio.sleep(5)  # timeout 보다 김
        return "should_not_reach"

    sess = WorkerSession(profile_id="p", account_id=1, account_snapshot=_snap())
    with pytest.raises(PhaseTimeout) as ei:
        await sess.run_phase("ip_rotate", slow())
    assert ei.value.phase == "ip_rotate"
    assert ei.value.threshold_sec == 1


@pytest.mark.asyncio
async def test_run_phase_emits_phase_on_entry():
    """run_phase 진입 시 phase emit."""
    from worker.session import WorkerSession

    calls = []
    def reporter(**kw):
        calls.append(kw["phase"])

    async def ok():
        return "ok"

    sess = WorkerSession(profile_id="p", account_id=1, account_snapshot=_snap(),
                         progress_reporter=reporter)
    await sess.run_phase("compose", ok())
    assert "compose" in calls


# ───── orchestrator 통합: phase_timeout → worker-env error 분류 ─────


def test_phase_timeout_classified_as_worker_environment_error():
    """orchestrator._is_worker_environment_error 가 phase_timeout 메시지 인식."""
    from hydra.core.orchestrator import _is_worker_environment_error
    msg = "phase_timeout phase=ip_rotate elapsed=46s threshold=45s"
    assert _is_worker_environment_error(msg) is True


def test_envelope_missing_classified_as_worker_environment_error():
    """PR-A B++ 의 envelope_missing 도 worker-env."""
    from hydra.core.orchestrator import _is_worker_environment_error
    assert _is_worker_environment_error("envelope_missing") is True
