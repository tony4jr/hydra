from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from hydra.db.session import get_db
from hydra.services import preset_service
import json

router = APIRouter(prefix="/api/presets", tags=["presets"])

class PresetCreate(BaseModel):
    name: str
    code: str
    description: str = ""
    steps: list[dict]

class PresetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict] | None = None

@router.get("/")
def list_presets(db: Session = Depends(get_db)):
    presets = preset_service.list_presets(db)
    return [
        {"id": p.id, "name": p.name, "code": p.code, "is_system": p.is_system,
         "description": p.description, "steps": json.loads(p.steps),
         "step_count": len(json.loads(p.steps))}
        for p in presets
    ]

@router.get("/{preset_id}")
def get_preset(preset_id: int, db: Session = Depends(get_db)):
    preset = preset_service.get_preset(db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"id": preset.id, "name": preset.name, "code": preset.code,
            "is_system": preset.is_system, "description": preset.description,
            "steps": json.loads(preset.steps)}

@router.post("/")
def create_preset(body: PresetCreate, db: Session = Depends(get_db)):
    existing = preset_service.get_preset_by_code(db, body.code)
    if existing:
        raise HTTPException(status_code=409, detail=f"Code '{body.code}' already exists")
    preset = preset_service.create_preset(db, body.name, body.code, body.description, body.steps)
    return {"id": preset.id, "name": preset.name, "code": preset.code}

@router.put("/{preset_id}")
def update_preset(preset_id: int, body: PresetUpdate, db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    preset = preset_service.update_preset(db, preset_id, data)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"id": preset.id, "name": preset.name}

@router.delete("/{preset_id}")
def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    if not preset_service.delete_preset(db, preset_id):
        raise HTTPException(status_code=400, detail="Cannot delete (not found or system preset)")
    return {"ok": True}
