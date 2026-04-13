"""System settings API — key-value store backed by system_config table."""

import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from hydra.core.config import settings as app_settings
from hydra.db.session import get_db
from hydra.db.models import SystemConfig

router = APIRouter()


@router.get("/api/all")
def get_all_settings(db: Session = Depends(get_db)):
    """Return all settings as flat dict."""
    rows = db.query(SystemConfig).all()
    return {r.key: r.value for r in rows}


@router.post("/api/save")
def save_settings(data: dict, db: Session = Depends(get_db)):
    """Save multiple settings at once."""
    for key, value in data.items():
        existing = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if existing:
            existing.value = str(value)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(SystemConfig(key=key, value=str(value)))
    db.commit()
    return {"ok": True, "saved": len(data)}


@router.post("/api/backup")
def trigger_backup():
    """Manual backup of DB + config."""
    db_path = Path(app_settings.data_dir) / "hydra.db"
    backup_dir = Path(app_settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    if db_path.exists():
        shutil.copy2(db_path, backup_dir / f"hydra_{ts}.db")

    return {"ok": True, "backup": f"hydra_{ts}.db"}
