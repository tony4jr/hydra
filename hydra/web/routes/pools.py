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
def list_pools(pool_type: str | None = None, db: Session = Depends(get_db)):
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


@router.post("/api/{pool_id}/toggle")
def toggle_pool(pool_id: int, db: Session = Depends(get_db)):
    pool = db.query(ProfilePool).get(pool_id)
    if not pool:
        return {"error": "not found"}
    pool.disabled = not pool.disabled
    db.commit()
    return {"ok": True, "disabled": pool.disabled}
