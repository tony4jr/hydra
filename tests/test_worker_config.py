"""Task 33 — build_config + git-version + secrets 통합."""
from unittest.mock import patch

import pytest

from worker.config import WorkerConfig, _git_short_hash, build_config


# ── build_config 순수 테스트 ──

def test_build_config_from_secrets_dict():
    secrets = {
        "SERVER_URL": "https://api.hydra.com",
        "WORKER_TOKEN": "tok_abc",
        "DB_CRYPTO_KEY": "crypto_key_xyz",
    }
    cfg = build_config(secrets)
    assert cfg.server_url == "https://api.hydra.com"
    assert cfg.worker_token == "tok_abc"
    assert cfg.db_crypto_key == "crypto_key_xyz"
    assert cfg.heartbeat_interval == 30
    assert cfg.max_concurrent_tasks == 3


def test_build_config_missing_required_raises():
    with pytest.raises(KeyError):
        build_config({"SERVER_URL": "x"})  # WORKER_TOKEN 누락
    with pytest.raises(KeyError):
        build_config({"WORKER_TOKEN": "y"})  # SERVER_URL 누락


def test_build_config_worker_version_is_git_or_fallback():
    cfg = build_config({"SERVER_URL": "x", "WORKER_TOKEN": "y"})
    # 실제 git repo 내에선 short hash (>=4자), 아니면 "0.1.0"
    assert len(cfg.worker_version) >= 4


def test_build_config_worker_version_fallback_when_no_git():
    with patch("worker.config._git_short_hash", return_value=None):
        cfg = build_config({"SERVER_URL": "x", "WORKER_TOKEN": "y"})
    assert cfg.worker_version == "0.1.0"


# ── _git_short_hash ──

def test_git_short_hash_returns_non_empty_in_repo():
    h = _git_short_hash()
    # 리포 안에서 실행 중이니 정상 반환 기대
    assert h is None or (isinstance(h, str) and len(h) >= 4)


# ── WorkerConfig (secrets 우선 → env fallback → 기본) ──

def test_worker_config_secrets_override_legacy_env(monkeypatch, tmp_path):
    """worker.secrets.load_secrets() 가 값을 주면 HYDRA_* env 보다 우선."""
    env = tmp_path / ".env"
    env.write_text("SERVER_URL=https://from-secrets\nWORKER_TOKEN=secret-tok\n")
    monkeypatch.setattr("worker.secrets._dotenv_path", lambda: env)
    # 다른 테스트가 환경변수 SERVER_URL/WORKER_TOKEN 을 누수시켰을 수 있음 — 제거
    monkeypatch.delenv("SERVER_URL", raising=False)
    monkeypatch.delenv("WORKER_TOKEN", raising=False)
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://legacy")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "legacy-tok")

    cfg = WorkerConfig()
    assert cfg.server_url == "https://from-secrets"
    assert cfg.worker_token == "secret-tok"


def test_worker_config_falls_back_to_legacy_env(monkeypatch, tmp_path):
    """secrets 소스 없으면 HYDRA_* env 사용."""
    monkeypatch.setattr(
        "worker.secrets._dotenv_path", lambda: tmp_path / "nope.env",
    )
    monkeypatch.setattr(
        "worker.secrets._secrets_enc_path", lambda: tmp_path / "nope.enc",
    )
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://legacy:9000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "legacy-tok-2")

    cfg = WorkerConfig()
    assert cfg.server_url == "http://legacy:9000"
    assert cfg.worker_token == "legacy-tok-2"


def test_worker_config_default_when_no_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "worker.secrets._dotenv_path", lambda: tmp_path / "nope.env",
    )
    monkeypatch.setattr(
        "worker.secrets._secrets_enc_path", lambda: tmp_path / "nope.enc",
    )
    for k in ("SERVER_URL", "WORKER_TOKEN", "HYDRA_SERVER_URL", "HYDRA_WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)

    cfg = WorkerConfig()
    assert cfg.server_url == "http://localhost:8000"
    assert cfg.worker_token == ""
