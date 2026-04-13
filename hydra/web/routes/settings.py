"""System settings API — key-value store backed by system_config table."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
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


# --- Scenario Editor (#3) ---

PROXY_CONFIG_KEY = "ip_provider"


class ProxyConfigInput(BaseModel):
    provider_type: str  # adb | proxy_api | static_proxy
    device_id: str | None = None
    proxy_url: str | None = None
    username: str | None = None
    password: str | None = None
    proxies: list[str] | None = None
    randomize: bool = True


@router.get("/api/proxy")
def get_proxy_config(db: Session = Depends(get_db)):
    """Get current proxy/IP provider config."""
    from hydra.infra.ip_provider import get_provider
    row = db.query(SystemConfig).filter(SystemConfig.key == PROXY_CONFIG_KEY).first()
    provider = get_provider()
    return {
        "config": json.loads(row.value) if row else None,
        "active_provider": provider.name if provider else "none (ADB fallback)",
    }


@router.post("/api/proxy")
def set_proxy_config(data: ProxyConfigInput, db: Session = Depends(get_db)):
    """Set and activate proxy/IP provider."""
    from hydra.infra.ip_provider import create_provider, set_provider

    config = data.model_dump(exclude_none=True)

    # Save to DB
    row = db.query(SystemConfig).filter(SystemConfig.key == PROXY_CONFIG_KEY).first()
    value = json.dumps(config, ensure_ascii=False)
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(SystemConfig(key=PROXY_CONFIG_KEY, value=value))
    db.commit()

    # Activate provider
    provider = create_provider(**config)
    set_provider(provider)

    return {"ok": True, "provider": provider.name}


SCENARIO_CONFIG_KEY = "custom_scenarios"


class ScenarioStepInput(BaseModel):
    role: str
    type: str  # comment | reply
    delay_min: int
    delay_max: int
    parent_step: int | None = None


class ScenarioInput(BaseModel):
    id: str  # A~J
    name: str
    description: str
    steps: list[ScenarioStepInput]
    like_target_step: int = 0
    total_likes_min: int = 3
    total_likes_max: int = 10


@router.get("/api/scenarios")
def list_scenarios(db: Session = Depends(get_db)):
    """List all scenarios (defaults + custom overrides)."""
    from hydra.core.scenarios import TEMPLATES

    # Load custom overrides from DB
    custom = _load_custom_scenarios(db)

    result = []
    for scenario_id, tmpl in TEMPLATES.items():
        entry = {
            "id": scenario_id.value,
            "name": tmpl.name,
            "description": tmpl.description,
            "like_target_step": tmpl.like_target_step,
            "total_likes": list(tmpl.total_likes),
            "is_custom": scenario_id.value in custom,
            "steps": [
                {
                    "role": s.role.value,
                    "type": s.type,
                    "delay_min": s.delay_range[0],
                    "delay_max": s.delay_range[1],
                    "parent_step": s.parent_step,
                }
                for s in tmpl.steps
            ],
        }
        # Override with custom if exists
        if scenario_id.value in custom:
            entry.update(custom[scenario_id.value])
            entry["is_custom"] = True

        result.append(entry)

    return result


@router.post("/api/scenarios/save")
def save_scenario(data: ScenarioInput, db: Session = Depends(get_db)):
    """Save a custom scenario override."""
    custom = _load_custom_scenarios(db)

    custom[data.id] = {
        "id": data.id,
        "name": data.name,
        "description": data.description,
        "like_target_step": data.like_target_step,
        "total_likes": [data.total_likes_min, data.total_likes_max],
        "steps": [s.model_dump() for s in data.steps],
    }

    _save_custom_scenarios(db, custom)

    # Apply to runtime
    _apply_custom_scenario(data)

    return {"ok": True, "scenario": data.id}


@router.post("/api/scenarios/{scenario_id}/reset")
def reset_scenario(scenario_id: str, db: Session = Depends(get_db)):
    """Reset a scenario to defaults (remove custom override)."""
    custom = _load_custom_scenarios(db)
    if scenario_id in custom:
        del custom[scenario_id]
        _save_custom_scenarios(db, custom)
    return {"ok": True}


def _load_custom_scenarios(db: Session) -> dict:
    row = db.query(SystemConfig).filter(SystemConfig.key == SCENARIO_CONFIG_KEY).first()
    if row:
        return json.loads(row.value)
    return {}


def _save_custom_scenarios(db: Session, data: dict):
    row = db.query(SystemConfig).filter(SystemConfig.key == SCENARIO_CONFIG_KEY).first()
    value = json.dumps(data, ensure_ascii=False)
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(SystemConfig(key=SCENARIO_CONFIG_KEY, value=value))
    db.commit()


def _apply_custom_scenario(data: ScenarioInput):
    """Apply custom scenario to runtime TEMPLATES dict."""
    from hydra.core.scenarios import TEMPLATES, ScenarioTemplate, ScenarioStep
    from hydra.core.enums import Scenario, AccountRole

    try:
        scenario = Scenario(data.id)
    except ValueError:
        return

    steps = [
        ScenarioStep(
            role=AccountRole(s.role),
            type=s.type,
            delay_range=(s.delay_min, s.delay_max),
            parent_step=s.parent_step,
        )
        for s in data.steps
    ]

    TEMPLATES[scenario] = ScenarioTemplate(
        id=scenario,
        name=data.name,
        description=data.description,
        steps=steps,
        like_target_step=data.like_target_step,
        total_likes=(data.total_likes_min, data.total_likes_max),
    )
