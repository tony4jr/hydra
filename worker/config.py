"""Worker 설정 (Task 33).

우선순위:
  1. secrets.load_secrets() (Windows DPAPI 또는 .env) — SERVER_URL / WORKER_TOKEN / DB_CRYPTO_KEY
  2. 레거시 HYDRA_* 환경변수 (HYDRA_SERVER_URL 등) — Phase 1d 전환 중 호환
  3. 하드코딩 기본값 (localhost:8000) — dev fallback

worker_version 은 git HEAD short hash 자동 감지, git 없으면 "0.1.0" 기본.
기존 `from worker.config import config, WorkerConfig` 사용처 호환 유지.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional


DEFAULT_SERVER_URL = "http://localhost:8000"
DEFAULT_VERSION = "0.1.0"


def _git_short_hash() -> Optional[str]:
    """현재 체크아웃 커밋 short hash. 실패 시 None."""
    try:
        repo_root = Path(__file__).resolve().parent.parent
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=5,
        )
        return out.decode().strip() or None
    except Exception:
        return None


def _load_secrets_safely() -> dict:
    """worker.secrets.load_secrets() 호출. 실패(소스 없음) 시 빈 dict."""
    try:
        from worker.secrets import load_secrets
        return load_secrets()
    except Exception:
        return {}


class WorkerConfig:
    """워커 런타임 설정. 모듈 로드 시 auto 생성 (기존 호환)."""

    def __init__(self) -> None:
        secrets = _load_secrets_safely()

        self.server_url = (
            secrets.get("SERVER_URL")
            or os.getenv("HYDRA_SERVER_URL")
            or DEFAULT_SERVER_URL
        )
        self.worker_token = (
            secrets.get("WORKER_TOKEN")
            or os.getenv("HYDRA_WORKER_TOKEN", "")
        )
        self.db_crypto_key = (
            secrets.get("DB_CRYPTO_KEY")
            or os.getenv("DB_CRYPTO_KEY", "")
        )

        # 기존 필드명 유지 (Phase 1d 전환 중 호환) — Task 34 에서 heartbeat/v2 응답의
        # worker_config 에 맞춰 재조정 예정.
        self.heartbeat_interval = int(os.getenv("HYDRA_HEARTBEAT_INTERVAL", "30"))
        self.task_fetch_interval = int(os.getenv("HYDRA_TASK_FETCH_INTERVAL", "5"))
        self.max_concurrent_tasks = int(os.getenv("HYDRA_MAX_CONCURRENT", "3"))
        self.adb_device_id = os.getenv("HYDRA_ADB_DEVICE_ID", "")
        self.adspower_api_url = os.getenv(
            "ADSPOWER_API_URL", "http://127.0.0.1:50325",
        )
        self.worker_version = _git_short_hash() or DEFAULT_VERSION
        self.config_path = Path.home() / ".hydra-worker" / "config.json"

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "server_url": self.server_url,
            "worker_token": self.worker_token,
            "adspower_api_url": self.adspower_api_url,
            "adb_device_id": self.adb_device_id,
        }
        self.config_path.write_text(json.dumps(data, indent=2))

    def load(self) -> None:
        if self.config_path.exists():
            data = json.loads(self.config_path.read_text())
            self.server_url = data.get("server_url", self.server_url)
            self.worker_token = data.get("worker_token", self.worker_token)
            self.adspower_api_url = data.get("adspower_api_url", self.adspower_api_url)
            self.adb_device_id = data.get("adb_device_id", self.adb_device_id)


def build_config(secrets: dict) -> WorkerConfig:
    """secrets dict 로 Config 조립 (테스트용).

    Raises:
        KeyError: SERVER_URL / WORKER_TOKEN 누락 시.
    """
    if "SERVER_URL" not in secrets:
        raise KeyError("SERVER_URL")
    if "WORKER_TOKEN" not in secrets:
        raise KeyError("WORKER_TOKEN")

    # secrets 를 환경변수처럼 주입하고 WorkerConfig 재생성 — 단일 경로 유지
    # (테스트 격리 위해 os.environ 건드리지 않음 — 직접 인스턴스 조립)
    cfg = WorkerConfig.__new__(WorkerConfig)  # __init__ 우회
    cfg.server_url = secrets["SERVER_URL"]
    cfg.worker_token = secrets["WORKER_TOKEN"]
    cfg.db_crypto_key = secrets.get("DB_CRYPTO_KEY", "")
    cfg.heartbeat_interval = 30
    cfg.task_fetch_interval = 5
    cfg.max_concurrent_tasks = 3
    cfg.adb_device_id = ""
    cfg.adspower_api_url = "http://127.0.0.1:50325"
    cfg.worker_version = _git_short_hash() or DEFAULT_VERSION
    cfg.config_path = Path.home() / ".hydra-worker" / "config.json"
    return cfg


config = WorkerConfig()
