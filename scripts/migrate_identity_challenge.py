"""본인 인증 챌린지 컬럼 추가 + 계정 #7 즉시 마킹.

SQLite 는 ALTER TABLE ADD COLUMN 지원. idempotent 하게 ensure.
"""
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path
from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hydra.db.session import SessionLocal, engine
from hydra.db.models import Account


def ensure_columns():
    inspector = inspect(engine)
    existing = {col["name"] for col in inspector.get_columns("accounts")}
    stmts = []
    if "identity_challenge_until" not in existing:
        stmts.append("ALTER TABLE accounts ADD COLUMN identity_challenge_until DATETIME")
    if "identity_challenge_count" not in existing:
        stmts.append("ALTER TABLE accounts ADD COLUMN identity_challenge_count INTEGER DEFAULT 0")
    with engine.begin() as conn:
        for s in stmts:
            print(f"  {s}")
            conn.execute(text(s))
    print(f"ensured ({len(stmts)} new columns)")


def mark_account(account_id: int, days: int = 7):
    db = SessionLocal()
    try:
        acc = db.get(Account, account_id)
        if not acc:
            print(f"account {account_id} not found")
            return
        acc.status = "identity_challenge"
        acc.identity_challenge_until = datetime.now(UTC) + timedelta(days=days)
        acc.identity_challenge_count = (acc.identity_challenge_count or 0) + 1
        db.commit()
        print(
            f"#{acc.id} {acc.gmail} → status=identity_challenge, "
            f"until={acc.identity_challenge_until.isoformat()}, "
            f"count={acc.identity_challenge_count}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    ensure_columns()
    mark_account(7, days=7)
