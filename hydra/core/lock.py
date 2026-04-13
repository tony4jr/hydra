"""Process-safe account locking using DB.

Uses SQLite BEGIN IMMEDIATE for atomic read-modify-write.
Prevents scheduler and session runner from using the same account.
"""

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from hydra.db.models import SystemConfig

LOCK_KEY = "locks.running_accounts"
LOCK_TTL_MINUTES = 30


def _get_locks(db: Session) -> dict[int, str]:
    row = db.query(SystemConfig).filter(SystemConfig.key == LOCK_KEY).first()
    if not row:
        return {}
    try:
        locks = json.loads(row.value)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOCK_TTL_MINUTES)
        return {
            int(k): v for k, v in locks.items()
            if datetime.fromisoformat(v) > cutoff
        }
    except Exception:
        return {}


def _atomic_update(db: Session, fn):
    """Execute fn(locks) -> locks atomically using BEGIN IMMEDIATE."""
    conn = db.connection()
    conn.execute(text("BEGIN IMMEDIATE"))
    try:
        row = db.query(SystemConfig).filter(SystemConfig.key == LOCK_KEY).first()
        if row:
            try:
                locks = json.loads(row.value)
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOCK_TTL_MINUTES)
                locks = {int(k): v for k, v in locks.items() if datetime.fromisoformat(v) > cutoff}
            except Exception:
                locks = {}
        else:
            locks = {}

        result = fn(locks)

        value = json.dumps(locks)
        if row:
            row.value = value
            row.updated_at = datetime.now(timezone.utc)
        else:
            db.add(SystemConfig(key=LOCK_KEY, value=value))

        db.flush()
        conn.execute(text("COMMIT"))
        return result
    except Exception:
        conn.execute(text("ROLLBACK"))
        raise


def acquire_lock(db: Session, account_id: int) -> bool:
    def _acquire(locks):
        if account_id in locks:
            return False
        locks[account_id] = datetime.now(timezone.utc).isoformat()
        return True
    return _atomic_update(db, _acquire)


def release_lock(db: Session, account_id: int):
    def _release(locks):
        locks.pop(account_id, None)
    _atomic_update(db, _release)


def is_locked(db: Session, account_id: int) -> bool:
    return account_id in _get_locks(db)


def release_all(db: Session):
    def _clear(locks):
        locks.clear()
    _atomic_update(db, _clear)
