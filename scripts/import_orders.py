"""Import purchased accounts from pipe-delimited order files.

Format: username|password|recovery_email|channel_url|year
Output:
  - data/accounts_import.csv (for audit/review)
  - accounts table rows (gmail, password, recovery_email, youtube_channel_id, notes)
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hydra.db.session import SessionLocal
from hydra.db.models import Account
from hydra.core import crypto
from hydra.core.enums import AccountStatus, WarmupGroup
import random

ORDER_FILES = [
    Path.home() / "Downloads" / "order_P106540.txt",
    Path.home() / "Downloads" / "order_P106541.txt",
]
CSV_OUT = Path(__file__).resolve().parents[1] / "data" / "accounts_import.csv"


def parse_orders():
    rows = []
    for f in ORDER_FILES:
        if not f.exists():
            print(f"WARN: missing {f}")
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 5:
                print(f"WARN: bad line: {line}")
                continue
            username, password, recovery, channel_url, year = parts[:5]
            channel_id = channel_url.rstrip("/").split("/")[-1]
            rows.append({
                "gmail": f"{username}@gmail.com",
                "password": password,
                "recovery_email": recovery,
                "youtube_channel_id": channel_id,
                "notes": f"purchased, created_year={year}, source={f.name}",
            })
    return rows


def write_csv(rows):
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["gmail", "password", "recovery_email", "youtube_channel_id", "notes"])
        w.writeheader()
        w.writerows(rows)
    print(f"CSV: {CSV_OUT} ({len(rows)} rows)")


def import_db(rows):
    db = SessionLocal()
    added = skipped = 0
    try:
        for r in rows:
            if db.query(Account).filter(Account.gmail == r["gmail"]).first():
                skipped += 1
                continue
            db.add(Account(
                gmail=r["gmail"],
                password=crypto.encrypt(r["password"]),
                recovery_email=r["recovery_email"],
                youtube_channel_id=r["youtube_channel_id"],
                notes=r["notes"],
                warmup_group=random.choice(list(WarmupGroup)),
                status=AccountStatus.REGISTERED,
            ))
            added += 1
        db.commit()
    finally:
        db.close()
    print(f"DB: added={added} skipped={skipped}")


if __name__ == "__main__":
    rows = parse_orders()
    print(f"parsed {len(rows)} rows")
    write_csv(rows)
    import_db(rows)
