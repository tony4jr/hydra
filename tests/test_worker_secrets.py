"""Task 32 — worker.secrets 로딩 모듈 (DPAPI + .env fallback)."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from worker.secrets import (
    _load_dotenv,
    _parse_env_text,
    load_secrets,
)


# ── _parse_env_text ──

def test_parse_basic():
    text = "SERVER_URL=https://api.test\nWORKER_TOKEN=abc123"
    parsed = _parse_env_text(text)
    assert parsed == {"SERVER_URL": "https://api.test", "WORKER_TOKEN": "abc123"}


def test_parse_ignores_comments_and_blanks():
    text = "# comment\n\nKEY1=val1\n  \nKEY2=val2"
    assert _parse_env_text(text) == {"KEY1": "val1", "KEY2": "val2"}


def test_parse_values_with_equals_sign():
    """값 안의 '=' 는 보존 (partition 으로 첫 번째 = 만 분할)."""
    assert _parse_env_text("JWT_SECRET=abc=def=ghi")["JWT_SECRET"] == "abc=def=ghi"


def test_parse_skips_lines_without_equals():
    assert _parse_env_text("NOEQUAL\nVALID=1") == {"VALID": "1"}


# ── _load_dotenv ──

def test_load_dotenv_from_file(tmp_path):
    p = tmp_path / ".env"
    p.write_text("SERVER_URL=http://localhost:8000\nWORKER_TOKEN=dev\n")
    assert _load_dotenv(p) == {
        "SERVER_URL": "http://localhost:8000", "WORKER_TOKEN": "dev",
    }


def test_load_dotenv_missing_file_returns_empty(tmp_path):
    assert _load_dotenv(tmp_path / "nothing.env") == {}


# ── load_secrets ──

def test_load_secrets_from_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SERVER_URL=https://x.y\nWORKER_TOKEN=tok123\n")
    monkeypatch.setattr("worker.secrets._dotenv_path", lambda: env)
    # 실제 Windows 경로는 존재 안 함 → DPAPI 분기 자연 skip
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    result = load_secrets()
    assert result["SERVER_URL"] == "https://x.y"
    assert result["WORKER_TOKEN"] == "tok123"


def test_os_environ_overrides_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SERVER_URL=https://from-file\nWORKER_TOKEN=file-token\n")
    monkeypatch.setattr("worker.secrets._dotenv_path", lambda: env)
    monkeypatch.setenv("WORKER_TOKEN", "overridden")
    result = load_secrets()
    assert result["WORKER_TOKEN"] == "overridden"
    # file 기반도 유지
    assert result["SERVER_URL"] == "https://from-file"


def test_missing_all_sources_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "worker.secrets._dotenv_path", lambda: tmp_path / "nothing.env",
    )
    monkeypatch.setattr(
        "worker.secrets._secrets_enc_path", lambda: tmp_path / "nothing.enc",
    )
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="no secrets source"):
        load_secrets()


def test_missing_required_key_raises(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SERVER_URL=https://x.y\n")  # WORKER_TOKEN 누락
    monkeypatch.setattr("worker.secrets._dotenv_path", lambda: env)
    monkeypatch.delenv("WORKER_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="WORKER_TOKEN"):
        load_secrets()
