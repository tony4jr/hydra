"""Profile pool management API."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import ProfilePool

router = APIRouter()


class PoolCreate(BaseModel):
    pool_type: str
    content: str


@router.get("/api/list")
def list_pools(pool_type: str | None = None, type: str | None = None, db: Session = Depends(get_db)):
    pool_type = pool_type or type  # Support both ?pool_type= and ?type=
    query = db.query(ProfilePool)
    if pool_type:
        query = query.filter(ProfilePool.pool_type == pool_type)
    pools = query.order_by(ProfilePool.pool_type, ProfilePool.id).all()
    return [
        {
            "id": p.id, "pool_type": p.pool_type, "content": p.content,
            "used_count": p.used_count, "disabled": p.disabled,
        }
        for p in pools
    ]


@router.post("/api/create")
def create_pool(data: PoolCreate, db: Session = Depends(get_db)):
    pool = ProfilePool(pool_type=data.pool_type, content=data.content)
    db.add(pool)
    db.commit()
    return {"id": pool.id}


@router.get("/api/stats")
def pool_stats(db: Session = Depends(get_db)):
    """Available/used/total counts per pool type."""
    from hydra.accounts.profile_randomizer import get_pool_stats
    return get_pool_stats(db)


@router.post("/api/generate")
def generate_pool(count: int = 200, db: Session = Depends(get_db)):
    """Bulk generate pool items (names, descriptions, avatars, etc.)."""
    from hydra.accounts.pool_generator import generate_all
    try:
        stats = generate_all(db, count=count)
        return {"ok": True, **stats}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/generate-ai-avatars")
async def generate_ai_avatars_api(count: int = 50, db: Session = Depends(get_db)):
    """Download AI-generated face images from thispersondoesnotexist.com."""
    from pathlib import Path
    from hydra.accounts.pool_generator import generate_ai_avatars
    from hydra.core.config import settings

    output_dir = Path(settings.data_dir) / "pool_assets" / "ai_avatars"
    try:
        paths = await generate_ai_avatars(count, output_dir)
        # Add to pool
        for path in paths:
            db.add(ProfilePool(pool_type="avatar", content=path))
        db.commit()
        return {"ok": True, "generated": len(paths)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/{pool_id}/toggle")
def toggle_pool(pool_id: int, db: Session = Depends(get_db)):
    pool = db.query(ProfilePool).get(pool_id)
    if not pool:
        return {"error": "not found"}
    pool.disabled = not pool.disabled
    db.commit()
    return {"ok": True, "disabled": pool.disabled}
