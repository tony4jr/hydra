#!/usr/bin/env python3
"""SystemConfig 의 server_config.current_version 을 갱신.

사용: python scripts/bump_version.py <version>
보통 deploy.sh 마지막에 `python scripts/bump_version.py $(git rev-parse --short HEAD)`
형태로 호출된다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: bump_version.py <version>", file=sys.stderr)
        return 2
    version = sys.argv[1].strip()
    if not version:
        print("ERROR: empty version", file=sys.stderr)
        return 2

    from hydra.core.server_config import set_current_version
    set_current_version(version)
    print(f"server_config.current_version = {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
