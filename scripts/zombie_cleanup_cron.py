#!/usr/bin/env python3
"""Crontab 에서 5분마다 실행되는 좀비 태스크 복구 엔트리포인트.

크론 라인 예 (VPS /etc/cron.d/hydra-zombie):
  SHELL=/bin/bash
  */5 * * * * deployer cd /opt/hydra && set -a && . ./.env && set +a && \
      flock -n /tmp/hydra_zombie.lock \
      .venv/bin/python scripts/zombie_cleanup_cron.py >> /var/log/hydra/zombie.log 2>&1
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> int:
    from hydra.core.zombie_cleanup import find_and_reset_zombies
    count = find_and_reset_zombies(stale_minutes=30)
    print(f"reset {count} zombie tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
