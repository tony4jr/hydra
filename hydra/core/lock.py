"""Process-safe account locking using DB.

Prevents scheduler and session runner from using the same account.
Uses system_config table as a lightweight lock store.
"""

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from hydra.db.models import SystemConfig

LOCK_KEY = "locks.running_accounts"
LOCK_TTL_MINUTES = 30  # Auto-expire stale locks


def _get_locks(db: Session) -> dict[int, str]:
    """Get current locks: {account_id: timestamp_iso}."""
    row = db.query(SystemConfig).filter(SystemConfig.key == LOCK_KEY).first()
    if not row:
        return {}
    try:
        locks = json.loads(row.value)
        # Expire stale locks
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOCK_TTL_MINUTES)
        return {
            int(k): v for k, v in locks.items()
            if datetime.fromisoformat(v) > cutoff
        }
    except Exception:
        return {}


def _save_locks(db: Session, locks: dict[int, str]):
    row = db.query(SystemConfig).filter(SystemConfig.key == LOCK_KEY).first()
    value = json.dumps(locks)
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(SystemConfig(key=LOCK_KEY, value=value))
    db.commit()


def acquire_lock(db: Session, account_id: int) -> bool:
    """Try to lock an account. Returns True if acquired."""
    locks = _get_locks(db)
    if account_id in locks:
        return False  # Already locked
    locks[account_id] = datetime.now(timezone.utc).isoformat()
    _save_locks(db, locks)
    return True


def release_lock(db: Session, account_id: int):
    """Release an account lock."""
    locks = _get_locks(db)
    locks.pop(account_id, None)
    _save_locks(db, locks)


def is_locked(db: Session, account_id: int) -> bool:
    """Check if an account is currently locked."""
    return account_id in _get_locks(db)


def release_all(db: Session):
    """Release all locks (emergency stop)."""
    _save_locks(db, {})
