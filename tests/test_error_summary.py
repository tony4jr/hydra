"""Phase 4.1 — error_summary agent 검증.

실제 Anthropic 호출 mock — 입력 압축 + agent_name 정확성 + 실패 내성.
"""
from unittest.mock import MagicMock, patch
import pytest


def test_summarize_empty_returns_no_errors():
    from hydra.ai.agents.error_summary_agent import summarize_errors
    assert summarize_errors([]) == "에러 없음"


def test_summarize_calls_haiku_with_compressed_input():
    from hydra.ai.agents.error_summary_agent import summarize_errors
    rows = [
        {"kind": "task_fail", "message": "login fail",
         "screen_state": "post_password_unknown", "failure_taxonomy": "page_variant"},
        {"kind": "task_fail", "message": "login fail2",
         "screen_state": "post_password_unknown", "failure_taxonomy": "page_variant"},
        {"kind": "unknown_screen", "message": "trust device",
         "screen_state": "trust_device_prompt", "failure_taxonomy": "page_variant"},
    ]
    with patch("hydra.ai.agents.error_summary_agent.call_claude") as mock:
        mock.return_value = "3건 — login 2건 unknown 1건"
        result = summarize_errors(rows, window_hint="최근 1시간")
        assert result == "3건 — login 2건 unknown 1건"
        kwargs = mock.call_args.kwargs
        # agent_name 정확
        assert kwargs["agent_name"] == "error_summary"
        # user_message 에 카운트 압축 포함
        msg = kwargs["user_message"]
        assert "post_password_unknown" in msg
        assert "page_variant" in msg
        # 모델은 Haiku
        assert "haiku" in kwargs["model"].lower()


def test_summarize_handles_call_failure():
    from hydra.ai.agents.error_summary_agent import summarize_errors
    rows = [{"kind": "x", "message": "y"}]
    with patch("hydra.ai.agents.error_summary_agent.call_claude",
               side_effect=RuntimeError("network down")):
        result = summarize_errors(rows)
        assert "요약 실패" in result
        assert "network down" in result


def test_summarize_caps_at_50_rows_in_prompt():
    """100건 입력 → 카운트는 정확, sample_messages 는 5개로 제한."""
    from hydra.ai.agents.error_summary_agent import summarize_errors
    rows = [{"kind": "task_fail", "message": f"msg{i}"} for i in range(100)]
    with patch("hydra.ai.agents.error_summary_agent.call_claude") as mock:
        mock.return_value = "ok"
        summarize_errors(rows)
        msg = mock.call_args.kwargs["user_message"]
        # total은 100 (전체 카운트)
        assert '"total": 100' in msg
        # sample_messages는 5개 이하
        sample_count = msg.count('"msg')
        assert sample_count <= 5


def test_agent_models_includes_error_summary():
    """AGENT_MODELS dict에 error_summary 매핑 확인."""
    from hydra.ai.base import AGENT_MODELS, MODEL_HAIKU
    assert AGENT_MODELS.get("error_summary") == MODEL_HAIKU
