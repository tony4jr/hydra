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
    preset = db.get(Preset, preset_id)
    if not preset:
        return None
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
