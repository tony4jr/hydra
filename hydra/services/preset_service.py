import json
from sqlalchemy.orm import Session
from hydra.db.models import Preset

def list_presets(db: Session, include_system: bool = True) -> list[Preset]:
    query = db.query(Preset)
    if not include_system:
        query = query.filter(Preset.is_system == False)
    return query.order_by(Preset.code).all()

def get_preset(db: Session, preset_id: int) -> Preset | None:
    return db.get(Preset, preset_id)

def get_preset_by_code(db: Session, code: str) -> Preset | None:
    return db.query(Preset).filter(Preset.code == code).first()

def create_preset(db: Session, name: str, code: str, description: str, steps: list[dict]) -> Preset:
    preset = Preset(
        name=name, code=code, is_system=False,
        description=description,
        steps=json.dumps(steps, ensure_ascii=False),
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return preset

def update_preset(db: Session, preset_id: int, data: dict) -> Preset | None:
    """Update preset. Returns None if not found. Raises ValueError if system preset."""
    preset = db.get(Preset, preset_id)
    if not preset:
        return None
    if preset.is_system:
        raise ValueError("system_preset_readonly")
    if "name" in data:
        preset.name = data["name"]
    if "description" in data:
        preset.description = data["description"]
    if "steps" in data:
        preset.steps = json.dumps(data["steps"], ensure_ascii=False)
    db.commit()
    db.refresh(preset)
    return preset

def delete_preset(db: Session, preset_id: int) -> bool:
    preset = db.get(Preset, preset_id)
    if not preset or preset.is_system:
        return False
    db.delete(preset)
    db.commit()
    return True


def clone_preset(db: Session, preset_id: int, new_name: str | None = None) -> Preset | None:
    """Duplicate a preset as a non-system (editable) copy. Returns None if source missing."""
    src = db.get(Preset, preset_id)
    if not src:
        return None

    base_code = f"{src.code}_copy"
    code = base_code
    idx = 1
    while db.query(Preset).filter(Preset.code == code).first() is not None:
        idx += 1
        code = f"{base_code}{idx}"

    clone = Preset(
        name=new_name or f"{src.name} (복사본)",
        code=code,
        is_system=False,
        description=src.description,
        steps=src.steps,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone
