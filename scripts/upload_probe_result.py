#!/usr/bin/env python3
"""저장된 probe 결과 파일을 서버로 재업로드. DNS 일시 실패 복구용.

사용: cd C:\\hydra && .\\.venv\\Scripts\\python.exe scripts\\upload_probe_result.py
"""
import glob
import json
import os
import sys
import time

import httpx


def main() -> int:
    files = sorted(glob.glob("adspower_probe_*.json"))
    if not files:
        print("no adspower_probe_*.json found")
        return 1
    latest = files[-1]
    print(f"using {latest}")
    with open(latest, "r", encoding="utf-8") as f:
        data = json.load(f)

    from worker.config import config as _cfg
    base = _cfg.server_url.rstrip("/")
    tok = _cfg.worker_token

    # 재시도 5회
    for attempt in range(1, 6):
        try:
            with httpx.Client(timeout=30) as c:
                r = c.post(
                    f"{base}/api/workers/report-error",
                    headers={"X-Worker-Token": tok},
                    json={
                        "kind": "diagnostic",
                        "message": f"adspower api probe (uploaded from {latest})",
                        "context": data,
                    },
                )
                print(f"attempt {attempt}: http {r.status_code} {r.text[:100]}")
                if r.status_code == 200:
                    return 0
        except Exception as e:
            print(f"attempt {attempt}: {type(e).__name__}: {e}")
        time.sleep(5)
    return 2


if __name__ == "__main__":
    sys.exit(main())
