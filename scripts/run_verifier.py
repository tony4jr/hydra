#!/usr/bin/env python3
"""온보딩 verifier CLI.

사용 예:
  .venv/bin/python scripts/run_verifier.py 18
  .venv/bin/python scripts/run_verifier.py 18 19 20
  .venv/bin/python scripts/run_verifier.py --range 20 30
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from onboarding import verify_account

LOG_PATH = Path("/tmp/hydra_onboarding.log")
INTER_ACCOUNT_GAP = 15  # seconds


def log(msg: str):
    from datetime import datetime, UTC
    line = f"[{datetime.now(UTC).isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


async def run_all(account_ids: list[int]):
    LOG_PATH.write_text("")
    log(f"=== onboarding verifier start — targets: {account_ids} ===")
    total = {"ok": 0, "partial": 0, "skipped": 0, "error": 0}
    for i, aid in enumerate(account_ids):
        log(f"")
        log(f"--- account #{aid} ({i+1}/{len(account_ids)}) ---")
        try:
            report = await verify_account(aid)
        except Exception as e:
            log(f"  FATAL: {e!r}")
            total["error"] += 1
            continue
        entries = report.as_dict()["entries"]
        log(f"  entries: {json.dumps(entries, ensure_ascii=False)}")
        if report.overall_ok():
            total["ok"] += 1
        elif any(e["status"] == "skipped" and (e.get("reason") or "").startswith("status=") for e in entries):
            total["skipped"] += 1
        elif entries:
            total["partial"] += 1
        else:
            total["error"] += 1
        if i < len(account_ids) - 1:
            time.sleep(INTER_ACCOUNT_GAP)
    log(f"")
    log(f"=== done ===")
    log(f"summary: {total}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", type=int, help="account ids")
    ap.add_argument("--range", nargs=2, type=int, metavar=("FROM", "TO"))
    args = ap.parse_args()

    if args.range:
        acct_ids = list(range(args.range[0], args.range[1] + 1))
    elif args.ids:
        acct_ids = args.ids
    else:
        ap.error("provide ids or --range FROM TO")

    asyncio.run(run_all(acct_ids))


if __name__ == "__main__":
    main()
