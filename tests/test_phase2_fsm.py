"""Phase 2 — LoginState FSM + SelectorRegistry + CircuitBreaker 검증."""
import time
import pytest

from worker.login_states import (
    LoginState, EXPECTED_TRANSITIONS, is_terminal, is_unexpected_transition,
)
from hydra.browser.selector_registry import SR, SelectorRegistry
from worker.circuit_breaker import ScreenStateCircuitBreaker


# ── LoginState ────────────────────────────────────────────────────────────

def test_login_state_values_match_screen_state_convention():
    """capture.py 의 screen_state 인자로 그대로 쓸 수 있어야 함 (snake_case)."""
    assert LoginState.EMAIL_INPUT.value == "email_input"
    assert LoginState.POST_PASSWORD_UNKNOWN.value == "post_password_unknown"
    assert LoginState.TWO_FACTOR == "two_factor"


def test_login_state_terminal_set():
    assert is_terminal(LoginState.LOGIN_SUCCESS)
    assert is_terminal(LoginState.LOGIN_FAILED)
    assert is_terminal(LoginState.POST_PASSWORD_UNKNOWN)
    assert not is_terminal(LoginState.EMAIL_INPUT)
    assert not is_terminal(LoginState.PASSWORD_INPUT)


def test_expected_transitions_email_to_password():
    """정상 흐름 EMAIL_INPUT → PASSWORD_INPUT 는 예상 안에."""
    assert LoginState.PASSWORD_INPUT in EXPECTED_TRANSITIONS[LoginState.EMAIL_INPUT]


def test_unexpected_transition_detection():
    """INIT 에서 바로 LOGIN_SUCCESS 는 예상 밖 (정상 흐름 우회)."""
    assert is_unexpected_transition(LoginState.INIT, LoginState.LOGIN_SUCCESS)
    # 정상 흐름은 unexpected 아님
    assert not is_unexpected_transition(LoginState.EMAIL_INPUT, LoginState.PASSWORD_INPUT)


def test_terminal_states_have_no_outgoing():
    """terminal state 는 EXPECTED_TRANSITIONS 가 비어있어야."""
    assert EXPECTED_TRANSITIONS[LoginState.LOGIN_SUCCESS] == set()
    assert EXPECTED_TRANSITIONS[LoginState.LOGIN_FAILED] == set()


# ── SelectorRegistry ──────────────────────────────────────────────────────

def test_sr_get_first_returns_string():
    sel = SR.get_first("login_email_input")
    assert sel == "input[type='email']"


def test_sr_get_first_with_format():
    sel = SR.get_first("login_account_chooser_by_email", email="foo@bar")
    assert "foo@bar" in sel


def test_sr_candidates_returns_list_for_fallback_chain():
    cands = SR.candidates("login_identifier_next")
    assert isinstance(cands, list)
    assert len(cands) >= 2  # 다중 fallback 존재
    assert "#identifierNext" in cands[0]


def test_sr_candidates_format_applied_to_all():
    """{cid} 치환이 list 전 항목에 적용."""
    cands = SR.candidates("yt_comment_thread_by_id", cid="UgyABC")
    assert len(cands) == 6  # 6단 OR pattern 보존
    for c in cands:
        assert "UgyABC" in c


def test_sr_singleton_register_runtime():
    """런타임 등록 가능 (hot patch)."""
    r = SelectorRegistry()
    r.register("test_key", "div.test")
    assert r.get_first("test_key") == "div.test"


# ── CircuitBreaker ────────────────────────────────────────────────────────

def test_breaker_closed_by_default():
    b = ScreenStateCircuitBreaker(threshold=3)
    assert b.is_open("foo") is False


def test_breaker_opens_at_threshold():
    b = ScreenStateCircuitBreaker(threshold=3, window_sec=60.0)
    for _ in range(3):
        b.record_failure("two_factor")
    assert b.is_open("two_factor") is True


def test_breaker_other_state_unaffected():
    b = ScreenStateCircuitBreaker(threshold=2)
    b.record_failure("two_factor")
    b.record_failure("two_factor")
    assert b.is_open("two_factor") is True
    assert b.is_open("email_input") is False


def test_breaker_success_resets_counter():
    b = ScreenStateCircuitBreaker(threshold=3)
    b.record_failure("x")
    b.record_failure("x")
    b.record_success("x")
    b.record_failure("x")
    b.record_failure("x")
    # 3회 후 reset 됐으니 2회만 누적 — 열림 X
    assert b.is_open("x") is False


def test_breaker_cooldown_expires():
    b = ScreenStateCircuitBreaker(threshold=2, window_sec=60.0, cooldown_sec=0.05)
    b.record_failure("z")
    b.record_failure("z")
    assert b.is_open("z") is True
    time.sleep(0.1)
    assert b.is_open("z") is False


def test_breaker_status_diagnostic():
    b = ScreenStateCircuitBreaker(threshold=5)
    b.record_failure("k")
    s = b.status("k")
    assert s["screen_state"] == "k"
    assert s["recent_failures"] == 1
    assert s["is_open"] is False
