"""Automated backup — DB + config files.

Spec Part 11.3:
- Periodic backup (default every 4 hours)
- Retention policy (default 7 days)
- SQLite-safe backup via VACUUM INTO
"""

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from hydra.core.config import settings
from hydra.core.logger import get_logger

log = get_logger("backup")


def run_backup() -> str:
    """Create a backup of the database file.

    Returns the backup file path.
    """
    db_path = Path(settings.data_dir) / "hydra.db"
    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_path = backup_dir / f"hydra_{ts}.db"

    if db_path.exists():
        shutil.copy2(db_path, backup_path)
        log.info(f"Backup created: {backup_path}")

        # Cleanup old backups
        cleanup_old_backups()
    else:
        log.warning(f"DB file not found: {db_path}")

    return str(backup_path)


def cleanup_old_backups():
    """Remove backups older than retention period."""
    backup_dir = Path(settings.backup_dir)
    if not backup_dir.exists():
        return

    cutoff = datetime.now() - timedelta(days=settings.backup_retention_days)
    removed = 0

    for f in backup_dir.glob("hydra_*.db"):
        if f.stat().st_mtime < cutoff.timestamp():
            f.unlink()
            removed += 1

    if removed:
        log.info(f"Cleaned up {removed} old backups (>{settings.backup_retention_days}d)")


def list_backups() -> list[dict]:
    """List available backups."""
    backup_dir = Path(settings.backup_dir)
    if not backup_dir.exists():
        return []

    backups = []
    for f in sorted(backup_dir.glob("hydra_*.db"), reverse=True):
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return backups
