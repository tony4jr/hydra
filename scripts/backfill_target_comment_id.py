#!/usr/bin/env python3
"""pending reply/like_boost 의 target_comment_id 보정.

기본은 dry-run. 실제 반영은 --apply 필요.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hydra.core.orchestrator import (  # noqa: E402
    _extract_comment_id,
    _json_dict,
    enrich_child_payloads_for_parent,
)
from hydra.db.models import Task  # noqa: E402
from hydra.db.session import SessionLocal  # noqa: E402


def _missing_target(task: Task) -> bool:
    payload = _json_dict(task.payload)
    return not str(payload.get("target_comment_id") or "").strip()


def run(*, apply: bool) -> dict:
    db = SessionLocal()
    try:
        children = (
            db.query(Task)
            .filter(
                Task.status == "pending",
                Task.task_type.in_(("reply", "like_boost")),
                Task.parent_task_id.isnot(None),
            )
            .all()
        )
        parent_ids: set[int] = set()
        dry_missing = 0
        dry_failed = 0
        for child in children:
            if not _missing_target(child):
                continue
            parent = db.get(Task, child.parent_task_id)
            if parent is None or parent.status != "done":
                continue
            parent_ids.add(parent.id)
            dry_missing += 1
            if not _extract_comment_id(parent.result):
                dry_failed += 1

        stats = {
            "mode": "apply" if apply else "dry-run",
            "parents": len(parent_ids),
            "candidate_children": dry_missing,
            "would_fail": dry_failed,
            "enriched": 0,
            "failed": 0,
        }

        if apply:
            for parent_id in sorted(parent_ids):
                res = enrich_child_payloads_for_parent(parent_id, db)
                stats["enriched"] += res["enriched"]
                stats["failed"] += res["failed"]
            db.commit()
        else:
            db.rollback()

        return stats
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="DB에 실제 반영")
    args = parser.parse_args()
    print(json.dumps(run(apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
