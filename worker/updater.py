"""Worker 자동 업데이트 (Task 34).

Phase 1d:
- heartbeat/v2 응답의 current_version 이 local 과 다르면 drain 후 git pull + exit
- Windows Task Scheduler 가 exit 후 재시작 → 새 버전 가동
- pip 실패 시 이전 커밋으로 rollback

Legacy UpdateChecker (HTTP polling) 는 일시 호환용 유지 — Task 34 전환 완료 후 제거.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx

from hydra.core.logger import get_logger
from worker.config import config

log = get_logger("worker.updater")


class UpdateChecker:
    """Legacy (삭제 예정) — `/api/version/worker-latest` 폴링. heartbeat 기반으로 대체됨."""

    def __init__(self):
        self.base_url = config.server_url.rstrip("/")

    def check(self) -> dict | None:
        try:
            resp = httpx.get(f"{self.base_url}/api/version/worker-latest", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            latest = data.get("version", "")
            if latest and latest != config.worker_version:
                return {
                    "current": config.worker_version,
                    "latest": latest,
                    "download_url": data.get("download_url"),
                }
        except Exception:
            pass
        return None


# ─── Task 34: heartbeat 응답 기반 자가 업데이트 ───

_SAFE_LOCAL_VERSIONS = frozenset({"unknown", "dev", "0.1.0", ""})


def should_update(server_version: str, local_version: str) -> bool:
    """업데이트 필요 여부. dev/unknown 등 안전 기본값은 강제 업데이트 막음."""
    if not server_version or not local_version:
        return False
    if local_version in _SAFE_LOCAL_VERSIONS:
        return False
    return server_version != local_version


def perform_update(repo_dir: str = r"C:\hydra") -> None:
    """git fetch+reset → pip install -e . → sys.exit. 실패 시 rollback 후 exit(1).

    성공 exit(0) 시 Task Scheduler 가 워커를 재시작한다.
    """
    log.info("updater: pulling latest in %s", repo_dir)
    prev: str | None = None
    try:
        subprocess.check_call(
            ["git", "-C", repo_dir, "fetch", "origin", "main"],
            timeout=60,
        )
        prev = subprocess.check_output(
            ["git", "-C", repo_dir, "rev-parse", "HEAD"],
            timeout=10,
        ).decode().strip()

        subprocess.check_call(
            ["git", "-C", repo_dir, "reset", "--hard", "origin/main"],
            timeout=30,
        )
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-e",
             str(Path(repo_dir)), "--quiet"],
            timeout=300,
        )
        log.info("updater: success, exiting for Task Scheduler restart")
    except subprocess.CalledProcessError as e:
        log.error("updater: step failed (%s) — rolling back", e.cmd)
        if prev:
            try:
                subprocess.call(
                    ["git", "-C", repo_dir, "reset", "--hard", prev],
                    timeout=30,
                )
            except Exception:
                log.error("updater: rollback also failed — manual intervention needed")
        sys.exit(1)
    except Exception as e:
        log.error("updater: unexpected error: %s", e)
        sys.exit(1)

    sys.exit(0)


def maybe_update(
    server_version: str,
    local_version: str,
    repo_dir: str = r"C:\hydra",
    is_idle: bool = True,
) -> bool:
    """버전 불일치 + idle 시에만 perform_update 호출.

    Returns:
        False: 업데이트 안 함 (다음 heartbeat 에서 재체크)
        (True 는 실제론 반환되지 않음 — perform_update 가 sys.exit)
    """
    if not should_update(server_version, local_version):
        return False
    if not is_idle:
        log.info("updater: version mismatch but task in progress — drain mode")
        return False
    perform_update(repo_dir)
    return True  # unreachable
