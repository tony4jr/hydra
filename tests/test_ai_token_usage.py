"""Phase 0 — ai_token_usage 적재 검증."""
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from hydra.ai.harness import _log_token_usage, call_claude
from hydra.db.models import AITokenUsage


class _FakeUsage(SimpleNamespace):
    pass


def _make_resp(text: str, in_t: int = 100, out_t: int = 30,
               cache_read: int = 0, cache_write: int = 0):
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=_FakeUsage(
            input_tokens=in_t,
            output_tokens=out_t,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
    )


def test_log_token_usage_inserts_row(db_session, monkeypatch):
    """_log_token_usage 호출 시 ai_token_usage row 1건 생성."""
    monkeypatch.setattr(
        "hydra.db.session.SessionLocal", lambda: db_session,
    )
    usage = _FakeUsage(
        input_tokens=120, output_tokens=45,
        cache_read_input_tokens=10, cache_creation_input_tokens=5,
    )

    _log_token_usage(
        agent_name="comment", model="claude-haiku-4-5-20251001",
        usage=usage, task_id=None, account_id=None,
    )

    rows = db_session.query(AITokenUsage).all()
    assert len(rows) == 1
    r = rows[0]
    assert r.agent_name == "comment"
    assert r.model == "claude-haiku-4-5-20251001"
    assert r.input_tokens == 120
    assert r.output_tokens == 45
    assert r.cache_read_tokens == 10
    assert r.cache_write_tokens == 5


def test_call_claude_logs_usage(db_session, monkeypatch):
    """call_claude 정상 호출 시 자동으로 usage 적재."""
    monkeypatch.setattr(
        "hydra.db.session.SessionLocal", lambda: db_session,
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_resp(
        "hi", in_t=200, out_t=50,
    )
    monkeypatch.setattr("hydra.ai.harness.get_client", lambda: fake_client)

    result = call_claude(
        model="claude-haiku-4-5-20251001",
        system="sys", user_message="msg",
        agent_name="comment", task_id=42, account_id=7,
    )
    assert result == "hi"

    rows = db_session.query(AITokenUsage).all()
    assert len(rows) == 1
    assert rows[0].agent_name == "comment"
    assert rows[0].task_id == 42
    assert rows[0].account_id == 7
    assert rows[0].input_tokens == 200
    assert rows[0].output_tokens == 50


def test_logging_failure_does_not_break_call(monkeypatch):
    """ai_token_usage 적재 실패해도 call_claude 결과 정상 반환."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_resp("ok")
    monkeypatch.setattr("hydra.ai.harness.get_client", lambda: fake_client)

    def _broken_session():
        raise RuntimeError("DB down")
    monkeypatch.setattr("hydra.db.session.SessionLocal", _broken_session)

    result = call_claude(
        model="claude-haiku-4-5-20251001",
        system="s", user_message="u", agent_name="comment",
    )
    assert result == "ok"


def test_agent_models_mapping():
    """comment/reply 는 Haiku, persona/keyword 는 Sonnet 매핑 확인."""
    from hydra.ai.base import AGENT_MODELS, MODEL_HAIKU, MODEL_SONNET
    assert AGENT_MODELS["comment"] == MODEL_HAIKU
    assert AGENT_MODELS["reply"] == MODEL_HAIKU
    assert AGENT_MODELS["casual"] == MODEL_HAIKU
    assert AGENT_MODELS["slot"] == MODEL_HAIKU
    assert AGENT_MODELS["persona"] == MODEL_SONNET
    assert AGENT_MODELS["keyword"] == MODEL_SONNET
    assert MODEL_SONNET == "claude-sonnet-4-6"
    assert MODEL_HAIKU == "claude-haiku-4-5-20251001"
